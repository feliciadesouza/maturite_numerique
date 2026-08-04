from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AdministrationForm, AgentForm, ProfileForm, build_question_form
from .models import Administration, Agent, Question, Reponse, Utilisateur
from .permissions import role_required
from .scoring import calculer_score_global, distribution_niveaux_administration


def home(request):
    """Page d’accueil simple du projet, avant la maquette finale."""
    administrations = Administration.objects.order_by("nom")
    return render(request, "core/home.html", {"administrations": administrations})


def login_view(request):
    """Page de connexion basique pour les utilisateurs Django."""
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = authenticate(request, username=form.cleaned_data["username"], password=form.cleaned_data["password"])
            if user is not None:
                login(request, user)
                messages.success(request, "Connexion réussie.")
                return redirect("dashboard")
    else:
        form = AuthenticationForm()

    return render(request, "core/login.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.info(request, "Déconnexion réussie.")
    return redirect("home")


@login_required
@role_required("agent_evaluateur", "agent_enquete", "enqueteur", "dsi_decideur", "admin_contenu")
def dashboard(request):
    """Tableau de bord de base avec le score global pour chaque administration."""
    administrations = Administration.objects.order_by("nom")
    scores = []
    for administration in administrations:
        scores.append((administration, calculer_score_global(administration)))

    return render(request, "core/dashboard.html", {"scores": scores})


@login_required
@role_required("agent_evaluateur", "dsi_decideur", "admin_contenu")
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
@role_required("agent_evaluateur", "agent_enquete", "enqueteur", "dsi_decideur", "admin_contenu")
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


@login_required
@role_required("agent_evaluateur", "admin_contenu")
def formulaire_a(request):
    """Saisie du formulaire A, sans interface finale."""
    if request.method == "POST":
        form = AdministrationForm(request.POST)
        if form.is_valid():
            administration = form.save()
            messages.success(request, "Formulaire A enregistré avec succès.")
            return redirect("administration_detail", administration_id=administration.pk)
    else:
        form = AdministrationForm()

    return render(request, "core/formulaire_a.html", {"form": form})


@login_required
@role_required("agent_enquete", "enqueteur", "admin_contenu")
def formulaire_b(request):
    """Saisie du formulaire B, sans interface finale."""
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
            return redirect("administration_detail", administration_id=agent.administration_id)
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
