from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import Utilisateur


# Page d'atterrissage après connexion, selon le rôle métier.
# Libellés des rôles : unique source = Utilisateur.ROLE_CHOICES (models.py).
ROLE_HOME_URLS = {
    "agent_evaluateur": "formulaire_a",
    "enqueteur": "enqueteur_home",
    "dsi_decideur": "dashboard",
    "admin_contenu": "backoffice",
}


def user_has_role(user, *roles):
    """Vérifie si l'utilisateur connecté possède l'un des rôles attendus."""
    if not user or not user.is_authenticated:
        return False

    # Le superuser a accès à toutes les vues (back-office de secours, support).
    if user.is_superuser:
        return True

    try:
        profil = user.profil
    except Utilisateur.DoesNotExist:
        return False

    return profil.role in roles


def role_required(*roles):
    """
    Restreint une vue à certains rôles métier.
    - Visiteur non connecté  -> redirection vers la page de connexion.
    - Connecté au mauvais rôle -> 403 (chaque rôle a son propre menu, l'accès
      par URL à une autre section est un cas anormal).
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(
                    request.get_full_path(), settings.LOGIN_URL, "next"
                )
            if not user_has_role(request.user, *roles):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
