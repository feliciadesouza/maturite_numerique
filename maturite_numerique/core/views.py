from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.mail import send_mail
from django.db.models import Avg, Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    AgentForm,
    ContactForm,
    ProfileForm,
    build_question_form,
    build_reponses_form,
    enregistrer_reponses,
)
from .models import (
    Administration,
    Agent,
    Dimension,
    Evaluation,
    Question,
    Reponse,
    Utilisateur,
    VersionFormulaire,
)
from .permissions import ROLE_HOME_URLS, role_required
from .scoring import (
    calculer_score_global,
    classifier_niveau_agent,
    distribution_niveaux_administration,
    reponses_par_code,
)


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
    """Dimensions actives enrichies de leurs étiquettes de contenu."""
    return [
        {"obj": dim, "tags": DIMENSION_TAGS.get(dim.code, [])}
        for dim in Dimension.objects.filter(actif=True).order_by("ordre")
    ]


def get_role_home_url(user):
    """Retourne la page d’accueil correspondant au rôle métier d’un utilisateur."""
    if not user or not user.is_authenticated:
        return None

    try:
        profil = user.profil
    except Utilisateur.DoesNotExist:
        return None

    return ROLE_HOME_URLS.get(profil.role)


def home(request):
    """Page d'accueil du site vitrine (redirige les comptes connectés)."""
    if request.user.is_authenticated:
        role_home = get_role_home_url(request.user)
        if role_home:
            return redirect(role_home)

    score_moyen = (
        Evaluation.objects.filter(statut="terminee")
        .aggregate(moy=Avg("score_global"))
        .get("moy")
    )
    context = {
        "nb_administrations": Administration.objects.count(),
        "score_moyen": score_moyen,
        "dimensions": _dimensions_contenu(),
    }
    return render(request, "public/accueil.html", context)


def demarche(request):
    return render(request, "public/demarche.html")


def dimensions_publiques(request):
    return render(request, "public/dimensions.html", {"dimensions": _dimensions_contenu()})


def acces_par_role(request):
    return render(request, "public/acces_role.html")


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            message = form.save()
            destinataire = getattr(settings, "CONTACT_EMAIL", "contact@maturite-numerique.tg")
            send_mail(
                subject=f"[Contact] {message.get_sujet_display()} — {message.nom}",
                message=(
                    f"De : {message.nom} ({message.email})\n"
                    f"Administration : {message.administration or '-'}\n\n"
                    f"{message.message}"
                ),
                from_email=None,
                recipient_list=[destinataire],
                fail_silently=True,
            )
            messages.success(request, "Message envoyé. Réponse sous 48 h ouvrées.")
            return redirect("contact")
    else:
        form = ContactForm()
    return render(request, "public/contact.html", {"form": form})


def confidentialite(request):
    return render(request, "public/confidentialite.html")


def conditions(request):
    return render(request, "public/conditions.html")


def login_view(request):
    """Page de connexion basique pour les utilisateurs Django."""
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


def logout_view(request):
    logout(request)
    messages.info(request, "Déconnexion réussie.")
    return redirect("home")


@login_required
@role_required("dsi_decideur")
def dashboard(request):
    """Tableau de bord réservé au DSI / décideur."""
    administrations = Administration.objects.order_by("nom")
    scores = []
    for administration in administrations:
        scores.append((administration, calculer_score_global(administration)))

    return render(request, "core/dashboard.html", {"scores": scores})


@login_required
@role_required("admin_contenu")
def backoffice(request):
    """Back-office pour l’administrateur de contenu."""
    dimensions = Dimension.objects.order_by("ordre", "nom")
    formulaires = [
        {"code": "A", "label": "Formulaire A - Administration"},
        {"code": "B", "label": "Formulaire B - Agent"},
    ]
    return render(request, "core/backoffice.html", {"dimensions": dimensions, "formulaires": formulaires})


@login_required
@role_required("enqueteur")
def enqueteur_home(request):
    """Accueil enquêteur : liste des agents d’une administration à interviewer."""
    profil = get_object_or_404(Utilisateur, user=request.user)
    if profil.administration:
        agents = Agent.objects.filter(
            administration=profil.administration
        ).order_by("poste")
    else:
        agents = []
    return render(
        request,
        "core/enqueteur_home.html",
        {"agents": agents, "administration": profil.administration},
    )


@login_required
@role_required("dsi_decideur")
def administration_detail(request, administration_id):
    """Vue de détail d’une administration avec son score global."""
    administration = get_object_or_404(Administration, pk=administration_id)
    resultat = calculer_score_global(administration)
    distribution = distribution_niveaux_administration(administration)

    return render(
        request,
        "core/administration_detail.html",
        {
            "administration": administration,
            "resultat": resultat,
            "distribution": distribution,
        },
    )


@login_required
@role_required("agent_evaluateur", "enqueteur", "dsi_decideur", "admin_contenu")
def profile(request):
    """Vue de profil utilisateur pour rattacher le compte Django au rôle métier."""
    profile_obj, _ = Utilisateur.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil mis à jour.")
            return redirect("dashboard")
    else:
        form = ProfileForm(instance=profile_obj)

    return render(request, "core/profile.html", {"form": form})


def _evaluation_en_cours(administration, user):
    """Récupère (ou ouvre) l'évaluation en cours d'une administration."""
    version_a = VersionFormulaire.objects.filter(
        formulaire__code="A", est_active=True
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
            cree_par=user,
            statut="en_cours",
        )
    elif evaluation.version_formulaire_a_id is None and version_a:
        evaluation.version_formulaire_a = version_a
        evaluation.save(update_fields=["version_formulaire_a"])
    return evaluation, version_a


def _etapes_formulaire_a(version_a):
    """Les dimensions couvertes par le Formulaire A, dans l'ordre — une par étape."""
    if not version_a:
        return []
    return list(
        Dimension.objects.filter(
            actif=True,
            questions__version_formulaire=version_a,
            questions__actif=True,
        )
        .distinct()
        .order_by("ordre")
    )


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

    dimension = etapes[numero - 1]
    questions = list(
        Question.objects.filter(
            version_formulaire=version_a, dimension=dimension, actif=True
        )
        .select_related("type_champ")
        .prefetch_related("options")
        .order_by("ordre")
    )
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
        "dimension": dimension,
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
    """Saisie du formulaire B en mode assisté, réservée aux enquêteurs."""
    if request.method == "POST":
        agent_form = AgentForm(request.POST)
        question_form = build_question_form("B", data=request.POST)

        if agent_form.is_valid() and question_form.is_valid():
            agent = agent_form.save()
            for question in Question.objects.filter(version_formulaire__formulaire__code="B", actif=True):
                answer = question_form.cleaned_data.get(f"q_{question.id}")
                if answer:
                    Reponse.objects.create(
                        question=question,
                        agent=agent,
                        administration=agent.administration,
                        valeur=answer,
                    )
            messages.success(request, "Formulaire B enregistré avec succès.")
            return redirect("enqueteur_home")
    else:
        agent_form = AgentForm()
        question_form = build_question_form("B")

    return render(
        request,
        "core/formulaire_b.html",
        {"agent_form": agent_form, "question_form": question_form},
    )


# ----------------------------- Formulaire B public -----------------------------

SECTIONS_FORMULAIRE_B = ["profil", "bases", "usage", "freins"]
LIBELLES_SECTIONS_B = {
    "profil": "Profil", "bases": "Bases", "usage": "Usage", "freins": "Freins",
}
# Report des réponses B1.x vers les champs structurés de l'agent.
MAPPING_PROFIL_B = {
    "B1.1": "poste", "B1.2": "service", "B1.3": "tranche_age",
    "B1.4": "anciennete", "B1.5": "niveau_etudes", "B1.6": "mode_saisie",
}


def _version_b():
    return VersionFormulaire.objects.filter(
        formulaire__code="B", est_active=True
    ).first()


def _sections_agent(agent):
    """Sections à parcourir : « usage » est sautée si l'agent n'a jamais utilisé d'ordinateur."""
    reponses = reponses_par_code(agent)
    if reponses.get("B2.1", "").strip().lower() == "non":
        return ["profil", "bases", "freins"]
    return list(SECTIONS_FORMULAIRE_B)


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
            message=(
                "Vos réponses ont bien été enregistrées. Merci pour votre temps.\n"
                f"Référence : {agent.reference}"
            ),
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


@login_required
@role_required("admin_contenu", "dsi_decideur")
def roles(request):
    """Vue documentaire sur les rôles métier du projet."""
    return render(request, "core/roles.html")
