import math

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Avg, Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.gzip import gzip_page

from .forms import (
    ContactForm,
    DimensionForm,
    NouvelAgentForm,
    ProfileForm,
    QuestionBackofficeForm,
    appliquer_options,
    build_reponses_form,
    enregistrer_reponses,
)
from .models import (
    Administration,
    Agent,
    Dimension,
    Evaluation,
    Formulaire,
    Question,
    Reponse,
    TypeChamp,
    Utilisateur,
    VersionFormulaire,
)
from .permissions import ROLE_HOME_URLS, role_required
from .scoring import (
    classifier_niveau_agent,
    reponses_par_code,
    resultat_administration,
)
from .versioning import dupliquer_version, version_a_des_reponses


# Étiquettes de contenu (vitrine) associées à chaque dimension du référentiel.
DIMENSION_TAGS = {
    "infra": [
        "Postes de travail", "Connexion internet", "Réseau local",
        "Alimentation électrique", "Maintenance",
    ],
    "services": [
        "Site web officiel", "Démarches en ligne", "Paiement mobile money",
        "Canaux numériques", "Suivi des demandes",
    ],
    "competences": [
        "Bureautique", "Messagerie", "Outils métiers",
        "Recherche d'information", "Sécurité de base",
    ],
    "juridique": [
        "Loi n°2019-014", "Textes d'organisation", "Charte des données",
        "Archivage", "Habilitations",
    ],
    "engagement": [
        "Stratégie numérique", "Budget dédié", "Référent numérique",
        "Formation continue", "Suivi des projets",
    ],
}


def _dimensions_contenu():
    """Dimensions actives enrichies de leurs étiquettes de contenu.

    Identique pour tous les visiteurs et modifiable seulement en back-office :
    on mémorise le résultat 5 min pour éviter la requête à chaque affichage
    des pages vitrine (accueil, « Les 5 dimensions »).
    """
    def _build():
        return [
            {"obj": dim, "tags": DIMENSION_TAGS.get(dim.code, [])}
            for dim in Dimension.objects.filter(actif=True).order_by("ordre")
        ]

    return cache.get_or_set("public:dimensions_contenu", _build, 300)


def _accueil_chiffres():
    """Chiffres clés de la page d'accueil, mémorisés 5 min (identiques pour tous)."""
    def _build():
        score_moyen = (
            Evaluation.objects.filter(statut="terminee")
            .aggregate(moy=Avg("score_global"))
            .get("moy")
        )
        return {
            "nb_administrations": Administration.objects.count(),
            "score_moyen": score_moyen,
        }

    return cache.get_or_set("public:accueil_chiffres", _build, 300)


def _purger_cache_public():
    """Vide le cache des pages vitrine (à appeler après une édition en back-office)."""
    cache.delete_many(["public:dimensions_contenu", "public:accueil_chiffres"])


def get_role_home_url(user):
    """Page d'atterrissage d'un compte connecté, selon son rôle métier.
    Un superuser sans rôle métier (compte de support) atterrit sur le
    tableau de bord — la barre latérale lui donne ensuite accès à tout."""
    if not user or not user.is_authenticated:
        return None

    try:
        profil = user.profil
    except Utilisateur.DoesNotExist:
        profil = None

    home = ROLE_HOME_URLS.get(profil.role) if profil else None
    if home is None and user.is_superuser:
        return "dashboard"
    return home


@gzip_page
def home(request):
    """Page d'accueil du site vitrine (redirige les comptes connectés)."""
    if request.user.is_authenticated:
        role_home = get_role_home_url(request.user)
        if role_home:
            return redirect(role_home)

    chiffres = _accueil_chiffres()
    context = {
        "nb_administrations": chiffres["nb_administrations"],
        "score_moyen": chiffres["score_moyen"],
        "dimensions": _dimensions_contenu(),
    }
    return render(request, "public/accueil.html", context)


@gzip_page
def demarche(request):
    return render(request, "public/demarche.html")


@gzip_page
def dimensions_publiques(request):
    return render(request, "public/dimensions.html", {"dimensions": _dimensions_contenu()})


@gzip_page
def acces_par_role(request):
    return render(request, "public/acces_role.html")


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            message = form.save()
            destinataire = getattr(settings, "CONTACT_EMAIL", "contact@maturite-numerique.tg")
            send_mail(
                subject=f"[Contact] {message.get_sujet_display()} {message.nom}",
                message=render_to_string("email/contact.txt", {"message": message}),
                from_email=None,
                recipient_list=[destinataire],
                fail_silently=True,
            )
            messages.success(request, "Message envoyé. Réponse sous 48 h ouvrées.")
            return redirect("contact")
    else:
        form = ContactForm()
    return render(request, "public/contact.html", {"form": form})


@gzip_page
def confidentialite(request):
    return render(request, "public/confidentialite.html")


@gzip_page
def conditions(request):
    return render(request, "public/conditions.html")


@never_cache
def login_view(request):
    """Page de connexion basique pour les utilisateurs Django.

    ``never_cache`` empêche le navigateur (ou un proxy) de réutiliser une
    ancienne page contenant un jeton CSRF périmé, ce qui provoquerait un 403
    à la soumission du formulaire.
    """
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = authenticate(request, username=form.cleaned_data["username"], password=form.cleaned_data["password"])
            if user is not None:
                login(request, user)
                messages.success(request, "Connexion réussie.")
                role_home = get_role_home_url(user)
                if role_home:
                    return redirect(role_home)
                return redirect("home")
    else:
        form = AuthenticationForm()

    return render(request, "core/connexion.html", {"form": form})


@never_cache
def logout_view(request):
    logout(request)
    messages.info(request, "Déconnexion réussie.")
    return redirect("home")


@login_required
@role_required("dsi_decideur")
def dashboard(request):
    """Tableau de bord du DSI / décideur."""
    evals_terminees = Evaluation.objects.filter(statut="terminee")
    dimensions = list(Dimension.objects.filter(actif=True).order_by("ordre"))

    sommes, comptes = {}, {}
    for evaluation in evals_terminees:
        for code, valeur in (evaluation.score_par_dimension or {}).items():
            if valeur is None:
                continue
            sommes[code] = sommes.get(code, 0.0) + float(valeur)
            comptes[code] = comptes.get(code, 0) + 1

    radar_series = []
    dimension_risque = None
    for dimension in dimensions:
        key = str(dimension.pk)
        moyenne = round(sommes[key] / comptes[key], 2) if comptes.get(key) else 0.0
        radar_series.append({"dimension": dimension, "score": moyenne})
        if dimension_risque is None or moyenne < dimension_risque["score"]:
            dimension_risque = {"dimension": dimension, "score": moyenne}

    radar_data = {
        "labels": [d.nom for d in dimensions],
        "series": [{
            "nom": "Profil moyen",
            "valeurs": [s["score"] for s in radar_series],
            "couleur": "#ffffff",
        }],
        "dark": True,
    }

    score_moyen = evals_terminees.aggregate(m=Avg("score_global")).get("m")
    recentes = []
    for administration in Administration.objects.order_by("-id")[:5]:
        res = resultat_administration(administration)
        recentes.append({
            "administration": administration,
            "score": res.score_global,
            "badge": res.badge,
            "apercu": res.est_apercu,
        })

    return render(request, "app/dsi/dashboard.html", {
        "nb_administrations": Administration.objects.count(),
        "nb_eval_en_cours": Evaluation.objects.filter(statut="en_cours").count(),
        "nb_eval_terminees": evals_terminees.count(),
        "nb_agents": Agent.objects.filter(statut="terminee").count(),
        "score_moyen": round(score_moyen, 1) if score_moyen else None,
        "radar_data": radar_data,
        "radar_series": radar_series,
        "recentes": recentes,
        "dimension_risque": dimension_risque,
    })


@login_required
@role_required("dsi_decideur")
def administrations_liste(request):
    """Liste des administrations suivies avec leur niveau."""
    recherche = request.GET.get("q", "").strip()
    administrations = Administration.objects.order_by("nom")
    if recherche:
        administrations = administrations.filter(nom__icontains=recherche)
    lignes = []
    for administration in administrations:
        res = resultat_administration(administration)
        lignes.append({
            "administration": administration,
            "score": res.score_global,
            "niveau": res.niveau,
            "badge": res.badge,
            "apercu": res.est_apercu,
        })
    return render(request, "app/dsi/administrations.html", {
        "lignes": lignes, "recherche": recherche,
    })


def _version_active(code):
    return VersionFormulaire.objects.filter(
        formulaire__code=code, est_active=True
    ).first()


@login_required
@role_required("admin_contenu")
def backoffice(request):
    """Back-office — liste des dimensions du questionnaire."""
    version_a = _version_active("A")
    version_b = _version_active("B")
    dimensions = []
    for dimension in Dimension.objects.order_by("ordre", "nom"):
        nb_a = Question.objects.filter(
            dimension=dimension, actif=True, version_formulaire=version_a,
        ).count() if version_a else 0
        nb_b = Question.objects.filter(
            dimension=dimension, actif=True, version_formulaire=version_b,
        ).count() if version_b else 0
        dimensions.append({
            "obj": dimension, "nb_questions": nb_a + nb_b,
            "nb_a": nb_a, "nb_b": nb_b,
        })
    return render(request, "app/backoffice/dimensions.html", {
        "dimensions": dimensions,
        "version_a": version_a,
        "version_b": version_b,
    })


@login_required
@role_required("admin_contenu")
def bo_dimension_form(request, dimension_id=None):
    """Création ou édition d'une dimension."""
    dimension = get_object_or_404(Dimension, pk=dimension_id) if dimension_id else None
    if request.method == "POST":
        form = DimensionForm(request.POST, instance=dimension)
        if form.is_valid():
            obj = form.save(commit=False)
            if dimension is None:
                obj.ordre = (Dimension.objects.aggregate(m=Max("ordre"))["m"] or 0) + 1
            obj.save()
            _purger_cache_public()
            messages.success(request, "Dimension enregistrée.")
            return redirect("backoffice")
    else:
        form = DimensionForm(instance=dimension)
    return render(request, "app/backoffice/dimension_form.html", {
        "form": form, "dimension": dimension,
    })


@login_required
@role_required("admin_contenu")
def bo_dimension_ordre(request, dimension_id, sens):
    """Monte ou descend une dimension dans l'ordre d'affichage."""
    dimension = get_object_or_404(Dimension, pk=dimension_id)
    voisines = list(Dimension.objects.order_by("ordre", "nom"))
    i = voisines.index(dimension)
    j = i - 1 if sens == "haut" else i + 1
    if 0 <= j < len(voisines):
        autre = voisines[j]
        dimension.ordre, autre.ordre = autre.ordre, dimension.ordre
        dimension.save(update_fields=["ordre"])
        autre.save(update_fields=["ordre"])
        _purger_cache_public()
    return redirect("backoffice")


@login_required
@role_required("admin_contenu")
def bo_questions_index(request):
    """Point d'entrée « Questions » : choix de la dimension."""
    version_a = _version_active("A")
    version_b = _version_active("B")
    lignes = []
    for dimension in Dimension.objects.order_by("ordre", "nom"):
        nb = Question.objects.filter(
            dimension=dimension,
            version_formulaire__in=[v for v in (version_a, version_b) if v],
        ).count()
        lignes.append({"obj": dimension, "nb": nb})
    return render(request, "app/backoffice/questions_index.html", {"lignes": lignes})


def _version_pour_dimension(dimension):
    """Version active du formulaire qui porte les questions de cette dimension."""
    code = "B" if dimension.code == "competences" else "A"
    return _version_active(code)


@login_required
@role_required("admin_contenu")
def bo_questions(request, dimension_id):
    """Questions d'une dimension pour la version active."""
    dimension = get_object_or_404(Dimension, pk=dimension_id)
    version = _version_pour_dimension(dimension)
    questions = (
        Question.objects.filter(dimension=dimension, version_formulaire=version)
        .select_related("type_champ")
        .order_by("ordre")
        if version else []
    )
    return render(request, "app/backoffice/questions.html", {
        "dimension": dimension, "version": version, "questions": questions,
    })


@login_required
@role_required("admin_contenu")
def bo_question_ordre(request, question_id, sens):
    question = get_object_or_404(Question, pk=question_id)
    voisines = list(
        Question.objects.filter(
            dimension=question.dimension, version_formulaire=question.version_formulaire
        ).order_by("ordre")
    )
    i = voisines.index(question)
    j = i - 1 if sens == "haut" else i + 1
    if 0 <= j < len(voisines):
        autre = voisines[j]
        question.ordre, autre.ordre = autre.ordre, question.ordre
        question.save(update_fields=["ordre"])
        autre.save(update_fields=["ordre"])
    return redirect("bo_questions", dimension_id=question.dimension_id)


@login_required
@role_required("admin_contenu")
def bo_question_form(request, question_id=None, dimension_id=None):
    """
    Création ou édition d'une question. Si la version active a déjà des
    réponses, une modification crée automatiquement la version suivante.
    """
    if question_id:
        question = get_object_or_404(Question, pk=question_id)
        dimension = question.dimension
    else:
        question = None
        dimension = get_object_or_404(Dimension, pk=dimension_id)
    version = _version_pour_dimension(dimension)
    reponses_existantes = version and version_a_des_reponses(version)

    if request.method == "POST":
        form = QuestionBackofficeForm(request.POST, instance=question)
        if form.is_valid():
            if question and reponses_existantes:
                nouvelle_version = dupliquer_version(version)
                cible = nouvelle_version.questions.get(code=question.code)
                form = QuestionBackofficeForm(request.POST, instance=cible)
                form.is_valid()
                obj = form.save(commit=False)
                obj.version_formulaire = nouvelle_version
                obj.dimension = dimension
                obj.save()
                appliquer_options(obj, form.options_parsees())
                messages.success(
                    request,
                    f"Question modifiée version v{nouvelle_version.numero_version} créée "
                    "(les données précédentes sont conservées).",
                )
            else:
                obj = form.save(commit=False)
                obj.version_formulaire = version
                obj.dimension = dimension
                obj.save()
                appliquer_options(obj, form.options_parsees())
                messages.success(request, "Question enregistrée.")
            return redirect("bo_questions", dimension_id=dimension.pk)
    else:
        form = QuestionBackofficeForm(instance=question)

    return render(request, "app/backoffice/question_form.html", {
        "form": form,
        "question": question,
        "dimension": dimension,
        "version": version,
        "reponses_existantes": reponses_existantes,
        "prochaine_version": (version.numero_version + 1) if version else 2,
        "types_map": {str(t.pk): t.code for t in TypeChamp.objects.all()},
    })


@login_required
@role_required("admin_contenu")
def bo_versions(request):
    """Historique des versions de chaque formulaire."""
    formulaires = []
    for formulaire in Formulaire.objects.order_by("code"):
        versions = []
        for version in formulaire.versions.order_by("-numero_version"):
            versions.append({
                "obj": version,
                "nb_questions": version.questions.count(),
                "figee": version_a_des_reponses(version),
            })
        formulaires.append({"obj": formulaire, "versions": versions})
    return render(request, "app/backoffice/versions.html", {"formulaires": formulaires})


def _administrations_enqueteur(user):
    """Administrations où l'enquêteur connecté est affecté."""
    return Administration.objects.filter(enqueteurs=user).order_by("nom")


def _agent_de_l_enqueteur(request, agent_id):
    """Agent d'une administration où l'enquêteur connecté est affecté, ou 404."""
    profil = get_object_or_404(Utilisateur, user=request.user)
    return get_object_or_404(
        Agent, pk=agent_id, administration__enqueteurs=request.user
    ), profil


def _questions_agent_ordonnees(agent):
    """Liste à plat des questions visibles pour un agent (sections + conditions)."""
    version_b = _version_b()
    reponses = reponses_par_code(agent)
    questions = []
    for section in _sections_agent(agent):
        questions.extend(_questions_section(version_b, section, reponses))
    return questions


@login_required
@role_required("enqueteur")
def enqueteur_home(request):
    """Liste des agents à enquêter, sur toutes les administrations affectées."""
    administrations = list(_administrations_enqueteur(request.user))
    plusieurs_admins = len(administrations) > 1
    administration = administrations[0] if len(administrations) == 1 else None
    tous = (
        Agent.objects.filter(administration__in=administrations)
        .select_related("administration")
        .order_by("administration__nom", "numero", "poste")
        if administrations else Agent.objects.none()
    )

    compteurs = {
        "tous": tous.count(),
        "a_faire": tous.filter(statut="a_faire").count(),
        "en_cours": tous.filter(statut="en_cours").count(),
        "terminee": tous.filter(statut="terminee").count(),
    }
    termines = compteurs["terminee"]

    statut = request.GET.get("statut", "tous")
    recherche = request.GET.get("q", "").strip()
    agents = tous
    if statut in ("a_faire", "en_cours", "terminee"):
        agents = agents.filter(statut=statut)
    if recherche:
        agents = agents.filter(poste__icontains=recherche) | agents.filter(
            service__icontains=recherche
        )

    en_cours = tous.filter(statut="en_cours").first()
    total_questions = len(_questions_agent_ordonnees(en_cours)) if en_cours else 0

    filtres = [
        ("tous", f"Tous {compteurs['tous']}"),
        ("a_faire", f"À faire {compteurs['a_faire']}"),
        ("en_cours", f"En cours {compteurs['en_cours']}"),
        ("terminee", f"Terminées {compteurs['terminee']}"),
    ]

    return render(request, "app/enqueteur/liste_agents.html", {
        "administration": administration,
        "administrations": administrations,
        "plusieurs_admins": plusieurs_admins,
        "agents": agents,
        "compteurs": compteurs,
        "termines": termines,
        "statut_actif": statut,
        "recherche": recherche,
        "en_cours": en_cours,
        "en_cours_total": total_questions,
        "filters": filtres,
    })


@login_required
@role_required("enqueteur")
def enqueteur_nouvel_agent(request):
    """Ajout d'un agent à la liste d'enquête (dans une des administrations affectées)."""
    administrations = _administrations_enqueteur(request.user)
    if not administrations.exists():
        messages.warning(request, "Aucune administration ne vous est assignée.")
        return redirect("enqueteur_home")

    form = NouvelAgentForm(request.POST or None, administrations=administrations)
    if request.method == "POST" and form.is_valid():
        agent = form.save(commit=False)
        agent.administration = form.cleaned_data["administration"]
        agent.mode_saisie = "assiste"
        agent.enqueteur = request.user
        evaluation, _ = _evaluation_en_cours(agent.administration, request.user)
        agent.evaluation = evaluation
        dernier = (
            Agent.objects.filter(evaluation=evaluation, numero__isnull=False)
            .aggregate(m=Max("numero"))["m"] or 0
        )
        agent.numero = dernier + 1
        agent.save()
        messages.success(request, f"Agent {agent.numero:03d} ajouté à la liste.")
        return redirect("formulaire_b_assiste", agent_id=agent.pk, index=0)
    return render(request, "app/enqueteur/agent_form.html", {
        "form": form, "plusieurs_admins": administrations.count() > 1,
    })


@login_required
@role_required("enqueteur")
def formulaire_b_assiste(request, agent_id, index):
    """Formulaire B en mode assisté : une question à la fois."""
    agent, _ = _agent_de_l_enqueteur(request, agent_id)
    if agent.enqueteur_id is None:
        agent.enqueteur = request.user
        agent.save(update_fields=["enqueteur"])

    questions = _questions_agent_ordonnees(agent)
    total = len(questions)
    if total == 0:
        messages.error(request, "Le Formulaire B ne comporte pas encore de questions.")
        return redirect("enqueteur_home")
    if index < 0 or index >= total:
        return redirect("formulaire_b_assiste", agent_id=agent.pk, index=0)

    question = questions[index]
    reponse = Reponse.objects.filter(agent=agent, question=question).first()
    form = build_reponses_form(
        [question],
        reponses={question.id: reponse.valeur} if reponse else None,
        data=request.POST or None,
        partiel="precedent" in request.POST,
    )

    if request.method == "POST" and form.is_valid():
        enregistrer_reponses(
            form, [question], agent=agent, administration=agent.administration
        )
        if agent.statut == "a_faire":
            agent.statut = "en_cours"
        agent.progression = index
        agent.save(update_fields=["statut", "progression"])

        # La liste peut changer (filtre Niveau 0) : on la recalcule.
        questions = _questions_agent_ordonnees(agent)
        total = len(questions)
        if "precedent" in request.POST and index > 0:
            return redirect("formulaire_b_assiste", agent_id=agent.pk, index=index - 1)
        if index + 1 < total:
            return redirect("formulaire_b_assiste", agent_id=agent.pk, index=index + 1)
        try:
            _finaliser_enquete(agent)
        except Exception:
            messages.error(request, "La finalisation a échoué. Les réponses sont conservées.")
            return redirect("formulaire_b_assiste", agent_id=agent.pk, index=index)
        numero = agent.numero or agent.pk
        messages.success(request, f"Enquête de l'agent {numero:03d} terminée.")
        return redirect("enqueteur_home")

    return render(request, "app/enqueteur/formulaire_b_assiste.html", {
        "agent": agent,
        "question": question,
        "bf": form[f"q_{question.id}"],
        "index": index,
        "numero_question": index + 1,
        "total": total,
    })


@login_required
@role_required("enqueteur")
def enqueteur_agent_voir(request, agent_id):
    """Récapitulatif en lecture seule d'une enquête agent."""
    agent, _ = _agent_de_l_enqueteur(request, agent_id)
    lignes = [
        {"question": r.question, "valeur": r.valeur}
        for r in Reponse.objects.filter(agent=agent).select_related("question").order_by(
            "question__section", "question__ordre"
        )
    ]
    return render(request, "app/enqueteur/agent_voir.html", {"agent": agent, "lignes": lignes})


def _radar_resultat(resultat):
    """Données radar (une série) pour la page Résultats."""
    return {
        "labels": [s["dimension"].nom for s in resultat.scores_dimensions],
        "series": [{
            "nom": resultat.administration.nom,
            "valeurs": [s["score"] or 0 for s in resultat.scores_dimensions],
            "couleur": "#ffffff",
        }],
        "dark": True,
    }


@login_required
@role_required("dsi_decideur")
def administration_resultats(request, administration_id):
    """Résultats détaillés d'une administration : radar, recommandations, distribution."""
    administration = get_object_or_404(Administration, pk=administration_id)
    resultat = resultat_administration(administration)
    valeurs = resultat.distribution.values()
    return render(request, "app/dsi/resultats.html", {
        "administration": administration,
        "resultat": resultat,
        "radar_data": _radar_resultat(resultat),
        "total_agents": sum(valeurs),
        "dist_max": max(valeurs) or 1,
    })


PALETTE_COMPARAISON = ["#3e90f0", "#4fbf88", "#8b6fe0", "#f2b33d", "#e85d74", "#16202e"]


def svg_radar(labels, series, taille=240):
    """
    Géométrie d'un radar en SVG (rendu sans JavaScript, pour le rapport PDF).
    `series` : [{nom, valeurs (0-5), couleur}].
    """
    cx = cy = taille / 2
    rayon = taille / 2 - 44
    n = len(labels) or 1
    angles = [(-math.pi / 2) + i * (2 * math.pi / n) for i in range(n)]

    def point(rr, ang):
        return (round(cx + rr * math.cos(ang), 1), round(cy + rr * math.sin(ang), 1))

    anneaux = []
    for k in range(1, 6):
        pts = [point(rayon * k / 5, a) for a in angles]
        anneaux.append(" ".join(f"{x},{y}" for x, y in pts))

    def court(lbl):
        # Le rendu SVG n'ajuste pas le texte : on abrege les libelles longs.
        return lbl if len(lbl) <= 14 else lbl.split(" ")[0]

    axes = []
    for lbl, a in zip(labels, angles):
        x, y = point(rayon, a)
        lx, ly = point(rayon + 16, a)
        anchor = "middle" if abs(lx - cx) < 8 else ("start" if lx > cx else "end")
        axes.append({"x": x, "y": y, "label": court(lbl), "lx": round(lx, 1), "ly": round(ly, 1), "anchor": anchor})
    polygones = []
    for s in series:
        pts = [point(rayon * min(max(v, 0), 5) / 5, a) for v, a in zip(s["valeurs"], angles)]
        polygones.append({
            "points": " ".join(f"{x},{y}" for x, y in pts),
            "couleur": s["couleur"], "nom": s["nom"],
        })
    return {"taille": taille, "cx": cx, "cy": cy, "anneaux": anneaux, "axes": axes, "polygones": polygones}


@login_required
@role_required("dsi_decideur")
def comparaison(request):
    """Comparaison de plusieurs administrations : radar superposé + tableau."""
    ids = request.GET.getlist("admin")
    if ids:
        selection = list(Administration.objects.filter(pk__in=ids))
        selection.sort(key=lambda a: ids.index(str(a.pk)))
    else:
        selection = list(Administration.objects.order_by("id")[:3])

    dimensions = list(Dimension.objects.filter(actif=True).order_by("ordre"))
    colonnes, versions = [], set()
    for i, administration in enumerate(selection):
        res = resultat_administration(administration)
        version = (
            res.evaluation.version_formulaire_a.numero_version
            if res.evaluation and res.evaluation.version_formulaire_a_id else None
        )
        versions.add(version)
        colonnes.append({
            "administration": administration, "resultat": res,
            "couleur": PALETTE_COMPARAISON[i % len(PALETTE_COMPARAISON)], "version": version,
        })

    table = []
    for dimension in dimensions:
        cellules = []
        for col in colonnes:
            cellules.append(next(
                (s for s in col["resultat"].scores_dimensions if s["dimension"].pk == dimension.pk),
                None,
            ))
        table.append({"dimension": dimension, "cellules": cellules})

    radar_data = {
        "labels": [d.nom for d in dimensions],
        "series": [{
            "nom": col["administration"].nom,
            "valeurs": [s["score"] or 0 for s in col["resultat"].scores_dimensions],
            "couleur": col["couleur"],
        } for col in colonnes],
        "dark": False,
    }
    versions_connues = {v for v in versions if v is not None}
    versions_melangees = len(versions_connues) > 1

    ids_selection = [a.pk for a in selection]
    return render(request, "app/dsi/comparaison.html", {
        "colonnes": colonnes,
        "table": table,
        "radar_data": radar_data,
        "versions_melangees": versions_melangees,
        "ids_selection": ids_selection,
        "autres_administrations": Administration.objects.exclude(pk__in=ids_selection).order_by("nom"),
    })


@login_required
@role_required("dsi_decideur")
def rapports(request):
    """Liste des rapports disponibles par administration."""
    lignes = []
    for administration in Administration.objects.order_by("nom"):
        res = resultat_administration(administration)
        lignes.append({
            "administration": administration,
            "resultat": res,
            "date": res.evaluation.date_cloture if res.evaluation else None,
        })
    return render(request, "app/dsi/rapports.html", {"lignes": lignes})


@login_required
@role_required("dsi_decideur")
def rapport_administration(request, administration_id):
    """Rapport synthétique : page imprimable, ou PDF (WeasyPrint) si demandé."""
    administration = get_object_or_404(Administration, pk=administration_id)
    resultat = resultat_administration(administration)
    contexte = {
        "administration": administration,
        "resultat": resultat,
        "radar_svg": svg_radar(
            [s["dimension"].nom for s in resultat.scores_dimensions],
            [{
                "nom": administration.nom,
                "valeurs": [s["score"] or 0 for s in resultat.scores_dimensions],
                "couleur": "#1e6fd9",
            }],
        ),
        "total_agents": sum(resultat.distribution.values()),
        "dist_max": max(resultat.distribution.values()) or 1,
        "genere_le": timezone.now(),
    }

    if request.GET.get("format") == "pdf":
        pdf = None
        try:
            from weasyprint import HTML

            html = render(request, "app/dsi/rapport.html", contexte).content.decode("utf-8")
            pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        except Exception:
            pdf = None
        if pdf is None:
            messages.info(
                request,
                "L'export PDF n'est pas disponible ici : utilisez « Imprimer / PDF » depuis le navigateur.",
            )
            return redirect("rapport_administration", administration_id=administration_id)
        reponse = HttpResponse(pdf, content_type="application/pdf")
        reponse["Content-Disposition"] = (
            f'attachment; filename="rapport-{administration.pk}.pdf"'
        )
        return reponse

    return render(request, "app/dsi/rapport.html", contexte)


@login_required
def profile(request):
    """Profil : coordonnées éditables par l'utilisateur ; rôle métier et
    administration de rattachement en lecture seule (attribués par l'administrateur)."""
    profil, _ = Utilisateur.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil mis à jour.")
            return redirect(get_role_home_url(request.user) or "home")
    else:
        form = ProfileForm(instance=request.user)

    return render(request, "core/profile.html", {"form": form, "profil": profil})


def _evaluation_en_cours(administration, user):
    """Récupère (ou ouvre) l'évaluation en cours d'une administration."""
    version_a = VersionFormulaire.objects.filter(
        formulaire__code="A", est_active=True
    ).first()
    version_b = VersionFormulaire.objects.filter(
        formulaire__code="B", est_active=True
    ).first()
    evaluation = (
        Evaluation.objects.filter(
            administration=administration, statut__in=["brouillon", "en_cours"]
        )
        .order_by("-date_ouverture")
        .first()
    )
    if evaluation is None:
        evaluation = Evaluation.objects.create(
            administration=administration,
            version_formulaire_a=version_a,
            version_formulaire_b=version_b,
            cree_par=user,
            statut="en_cours",
        )
    else:
        maj = []
        if evaluation.version_formulaire_a_id is None and version_a:
            evaluation.version_formulaire_a = version_a
            maj.append("version_formulaire_a")
        if evaluation.version_formulaire_b_id is None and version_b:
            evaluation.version_formulaire_b = version_b
            maj.append("version_formulaire_b")
        if maj:
            evaluation.save(update_fields=maj)
    return evaluation, version_a


def _etapes_formulaire_a(version_a):
    """Étapes du Formulaire A : « Identification » puis une étape par dimension."""
    if not version_a:
        return []
    etapes = []
    if Question.objects.filter(
        version_formulaire=version_a, section="identification", actif=True
    ).exists():
        etapes.append({"nom": "Identification", "identification": True, "dimension": None})
    for dimension in (
        Dimension.objects.filter(
            actif=True, questions__version_formulaire=version_a, questions__actif=True
        )
        .distinct()
        .order_by("ordre")
    ):
        a_des_questions = (
            Question.objects.filter(
                version_formulaire=version_a, dimension=dimension, actif=True
            )
            .exclude(section="identification")
            .exists()
        )
        if a_des_questions:
            etapes.append({"nom": dimension.nom, "identification": False, "dimension": dimension})
    return etapes


@login_required
@role_required("agent_evaluateur")
def formulaire_a(request):
    """Point d'entrée : ouvre l'évaluation et redirige vers la première étape."""
    profil = get_object_or_404(Utilisateur, user=request.user)
    if not profil.administration:
        messages.warning(
            request,
            "Renseignez votre administration dans votre profil pour démarrer le Formulaire A.",
        )
        return redirect("profile")

    _, version_a = _evaluation_en_cours(profil.administration, request.user)
    if not _etapes_formulaire_a(version_a):
        messages.error(request, "Le Formulaire A ne comporte pas encore de questions.")
        return redirect("home")
    return redirect("formulaire_a_etape", numero=1)


@login_required
@role_required("agent_evaluateur")
def formulaire_a_etape(request, numero):
    """Une étape du Formulaire A (les questions d'une dimension)."""
    profil = get_object_or_404(Utilisateur, user=request.user)
    if not profil.administration:
        return redirect("formulaire_a")

    evaluation, version_a = _evaluation_en_cours(profil.administration, request.user)
    etapes = _etapes_formulaire_a(version_a)
    if numero < 1 or numero > len(etapes):
        return redirect("formulaire_a_etape", numero=1)

    etape = etapes[numero - 1]
    base_qs = Question.objects.filter(
        version_formulaire=version_a, actif=True
    ).select_related("type_champ").prefetch_related("options").order_by("ordre")
    if etape["identification"]:
        questions = list(base_qs.filter(section="identification"))
        titre_etape = "Identification"
    else:
        questions = list(
            base_qs.filter(dimension=etape["dimension"]).exclude(section="identification")
        )
        titre_etape = etape["dimension"].nom
    reponses_existantes = {
        r.question_id: r.valeur
        for r in Reponse.objects.filter(evaluation=evaluation, question__in=questions)
    }

    if request.method == "POST":
        autosave = request.POST.get("autosave") == "1"
        form = build_reponses_form(questions, data=request.POST, partiel=autosave)
        if form.is_valid():
            enregistrer_reponses(
                form, questions, evaluation=evaluation,
                administration=profil.administration, utilisateur=request.user,
            )
            if autosave:
                return HttpResponse(status=204)
            if "precedent" in request.POST and numero > 1:
                return redirect("formulaire_a_etape", numero=numero - 1)
            if numero < len(etapes):
                return redirect("formulaire_a_etape", numero=numero + 1)
            return redirect("formulaire_a_fin")
        if autosave:
            return HttpResponse(status=204)
    else:
        form = build_reponses_form(questions, reponses=reponses_existantes)

    champs = [{"q": question, "bf": form[f"q_{question.id}"]} for question in questions]
    return render(request, "app/formulaire_a/etape.html", {
        "evaluation": evaluation,
        "titre_etape": titre_etape,
        "champs": champs,
        "form": form,
        "numero": numero,
        "etapes": etapes,
        "total": len(etapes),
        "progression": round(numero / len(etapes) * 100),
    })


@login_required
@role_required("agent_evaluateur")
def formulaire_a_fin(request):
    """Écran de fin du Formulaire A."""
    profil = get_object_or_404(Utilisateur, user=request.user)
    if not profil.administration:
        return redirect("formulaire_a")
    evaluation, _ = _evaluation_en_cours(profil.administration, request.user)
    nb_reponses = Reponse.objects.filter(evaluation=evaluation).count()
    return render(request, "app/formulaire_a/fin.html", {
        "evaluation": evaluation, "nb_reponses": nb_reponses,
    })


@login_required
@role_required("enqueteur")
def formulaire_b(request):
    """Ancienne route : renvoie vers la liste des enquêtes."""
    return redirect("enqueteur_home")


# ----------------------------- Formulaire B public -----------------------------

SECTIONS_FORMULAIRE_B = ["profil", "bases", "bases_suite", "usage", "freins"]
LIBELLES_SECTIONS_B = {
    "profil": "Profil", "bases": "Bases", "bases_suite": "Bases (suite)",
    "usage": "Usage", "freins": "Freins",
}
# Report des réponses du profil vers les champs structurés de l'agent.
MAPPING_PROFIL_B = {
    "B1.0": "nom", "B1.1": "poste", "B1.2": "service", "B1.3": "tranche_age",
    "B1.4": "anciennete", "B1.5": "niveau_etudes", "B1.6": "mode_saisie",
}


def _version_b():
    return VersionFormulaire.objects.filter(
        formulaire__code="B", est_active=True
    ).first()


def _sections_agent(agent):
    """
    Parcours conditionnel du Formulaire B :
    - « bases (suite) » n'apparaît que si l'agent a déjà utilisé un ordinateur (B2.1 = Oui) ;
    - « usage » n'apparaît que s'il sait allumer un ordinateur ET utiliser souris/clavier
      (B3.1 = Oui et B3.2 = Oui).
    """
    rep = reponses_par_code(agent)

    def oui(code):
        return (rep.get(code) or "").strip().lower() == "oui"

    sections = ["profil", "bases"]
    if oui("B2.1"):
        sections.append("bases_suite")
        if oui("B3.1") and oui("B3.2"):
            sections.append("usage")
    sections.append("freins")
    return sections


def _questions_section(version_b, section, reponses):
    """Questions actives d'une section, filtrées par leur condition d'affichage."""
    visibles = []
    questions = (
        Question.objects.filter(version_formulaire=version_b, section=section, actif=True)
        .select_related("type_champ", "question_condition")
        .prefetch_related("options")
        .order_by("ordre")
    )
    for question in questions:
        condition = question.question_condition
        if condition and question.valeur_condition:
            if reponses.get(condition.code, "") != question.valeur_condition:
                continue
        visibles.append(question)
    return visibles


def _finaliser_enquete(agent):
    """Clôt le brouillon d'un agent : niveau, numéro, référence, e-mail d'accusé."""
    reponses = reponses_par_code(agent)
    agent.niveau_maturite = classifier_niveau_agent(reponses)
    if agent.evaluation_id and agent.numero is None:
        dernier = (
            Agent.objects.filter(evaluation=agent.evaluation, numero__isnull=False)
            .exclude(pk=agent.pk)
            .aggregate(m=Max("numero"))["m"]
            or 0
        )
        agent.numero = dernier + 1
    agent.statut = "terminee"
    agent.save()
    if not agent.reference:
        agent.reference = f"MN-{timezone.now().year}-{agent.pk:06d}"
        agent.save(update_fields=["reference"])
    if agent.email_accuse:
        send_mail(
            subject="Confirmation de votre participation",
            message=render_to_string("email/confirmation_enquete.txt", {"agent": agent}),
            from_email=None,
            recipient_list=[agent.email_accuse],
            fail_silently=True,
        )


def enquete_intro(request):
    """Page d'accueil publique de l'enquête agent."""
    return render(request, "enquete/intro.html")


def enquete_demarrer(request):
    """Étape 1 : choix de l'administration, puis création du brouillon d'agent."""
    administrations = Administration.objects.order_by("nom")
    if request.method == "POST":
        administration = Administration.objects.filter(
            pk=request.POST.get("administration")
        ).first()
        if administration is None:
            messages.error(request, "Sélectionnez une administration pour continuer.")
        else:
            evaluation, _ = _evaluation_en_cours(administration, None)
            agent = Agent.objects.create(
                administration=administration,
                evaluation=evaluation,
                mode_saisie="autonome",
                statut="en_cours",
            )
            return redirect("enquete_section", token=agent.token, section="profil")
    return render(request, "enquete/administration.html", {"administrations": administrations})


def enquete_section(request, token, section):
    """Une section conditionnelle du parcours (profil, bases, usage, freins)."""
    agent = get_object_or_404(Agent, token=token)
    if agent.statut == "terminee":
        return redirect("enquete_confirmation", token=agent.token)

    version_b = _version_b()
    sections = _sections_agent(agent)
    if section not in sections:
        return redirect("enquete_section", token=agent.token, section=sections[0])

    reponses_codes = reponses_par_code(agent)
    questions = _questions_section(version_b, section, reponses_codes)
    reponses_existantes = {
        r.question_id: r.valeur
        for r in Reponse.objects.filter(agent=agent, question__in=questions)
    }
    index = sections.index(section)
    est_derniere = index == len(sections) - 1

    if request.method == "POST":
        autosave = request.POST.get("autosave") == "1"
        recule = "precedent" in request.POST
        form = build_reponses_form(
            questions, data=request.POST, partiel=autosave or recule
        )
        if form.is_valid():
            enregistrer_reponses(
                form, questions, agent=agent, administration=agent.administration
            )
            if section == "profil":
                _reporter_profil(agent)
            if request.POST.get("email_accuse"):
                agent.email_accuse = request.POST["email_accuse"].strip()
                agent.save(update_fields=["email_accuse"])
            if autosave:
                return HttpResponse(status=204)
            sections = _sections_agent(agent)
            index = sections.index(section) if section in sections else 0
            if recule and index > 0:
                return redirect("enquete_section", token=agent.token, section=sections[index - 1])
            if index < len(sections) - 1:
                return redirect("enquete_section", token=agent.token, section=sections[index + 1])
            try:
                _finaliser_enquete(agent)
            except Exception:
                # Erreur réseau/serveur : les réponses restent enregistrées.
                return render(request, "enquete/erreur.html", {"agent": agent})
            return redirect("enquete_confirmation", token=agent.token)
        if autosave:
            return HttpResponse(status=204)
    else:
        form = build_reponses_form(questions, reponses=reponses_existantes)

    champs = [{"q": q, "bf": form[f"q_{q.id}"]} for q in questions]
    sections_info = [
        {"key": s, "label": LIBELLES_SECTIONS_B.get(s, s.title())} for s in sections
    ]
    return render(request, "enquete/section.html", {
        "agent": agent,
        "section": section,
        "libelle_section": LIBELLES_SECTIONS_B.get(section, section.title()),
        "champs": champs,
        "form": form,
        "sections_info": sections_info,
        "index": index,
        "est_derniere": est_derniere,
        "progression": round((index + 2) / (len(sections) + 1) * 100),
    })


def _reporter_profil(agent):
    """Recopie les réponses B1.x dans les champs structurés de l'agent."""
    reponses = reponses_par_code(agent)
    modifie = []
    for code, champ in MAPPING_PROFIL_B.items():
        valeur = reponses.get(code)
        if valeur:
            setattr(agent, champ, valeur[:150])
            modifie.append(champ)
    if modifie:
        agent.save(update_fields=modifie)


def enquete_envoi(request, token):
    """Ré-essai de soumission après une erreur réseau."""
    agent = get_object_or_404(Agent, token=token)
    if agent.statut == "terminee":
        return redirect("enquete_confirmation", token=agent.token)
    if request.method == "POST":
        try:
            _finaliser_enquete(agent)
        except Exception:
            return render(request, "enquete/erreur.html", {"agent": agent})
        return redirect("enquete_confirmation", token=agent.token)
    return redirect("enquete_section", token=agent.token, section=_sections_agent(agent)[-1])


def enquete_confirmation(request, token):
    """Accusé de participation."""
    agent = get_object_or_404(Agent, token=token)
    if agent.statut != "terminee":
        return redirect("enquete_section", token=agent.token, section="profil")
    return render(request, "enquete/confirmation.html", {"agent": agent})
