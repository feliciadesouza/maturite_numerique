from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.mail import send_mail
from django.db.models import Avg
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

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
from .scoring import calculer_score_global, distribution_niveaux_administration


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


def formulaire_b_public(request):
    """Formulaire B public pour l’agent enquêté, sans authentification."""
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
            return redirect("home")
    else:
        agent_form = AgentForm()
        question_form = build_question_form("B")

    return render(
        request,
        "core/formulaire_b.html",
        {"agent_form": agent_form, "question_form": question_form},
    )


@login_required
@role_required("admin_contenu", "dsi_decideur")
def roles(request):
    """Vue documentaire sur les rôles métier du projet."""
    return render(request, "core/roles.html")
