from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect

from .models import Utilisateur


ROLE_CHOICES = {
    "agent_evaluateur": "Agent évaluateur",
    "agent_enquete": "Agent enquêté",
    "enqueteur": "Enquêteur",
    "dsi_decideur": "DSI / Décideur",
    "admin_contenu": "Administrateur de contenu",
}


def user_has_role(user, *roles):
    """Vérifie si l’utilisateur connecté possède l’un des rôles attendus."""
    if not user or not user.is_authenticated:
        return False

    try:
        profil = user.profil
    except Utilisateur.DoesNotExist:
        return False

    return profil.role in roles


def role_required(*roles):
    """Décorateur simple pour restreindre une vue à certains rôles métier."""

    def decorator(view_func):
        @wraps(view_func)
        @user_passes_test(lambda user: user_has_role(user, *roles))
        def _wrapped_view(request, *args, **kwargs):
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
