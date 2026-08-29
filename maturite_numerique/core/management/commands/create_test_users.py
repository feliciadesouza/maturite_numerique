from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import Administration, Utilisateur


User = get_user_model()


TEST_USERS = [
    ("agent_eval", "AgentEval123!", "agent_evaluateur"),
    ("enqueteur", "Enqueteur123!", "enqueteur"),
    ("dsi", "Dsi123!", "dsi_decideur"),
    ("admin_contenu", "Admin123!", "admin_contenu"),
]

# Rôles rattachés à une administration pour les parcours de collecte.
ROLES_AVEC_ADMINISTRATION = {"agent_evaluateur", "enqueteur"}


class Command(BaseCommand):
    help = "Crée des comptes de test et les profils métier associés pour le projet."

    def handle(self, *args, **options):
        administration, _ = Administration.objects.get_or_create(
            nom="Mairie de Lomé", defaults={"region": "Maritime", "pays": "Togo"}
        )
        for username, password, role in TEST_USERS:
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password(password)
                user.save()
            profil, _ = Utilisateur.objects.get_or_create(user=user)
            profil.role = role
            if role in ROLES_AVEC_ADMINISTRATION:
                profil.administration = administration
            profil.save()
            self.stdout.write(self.style.SUCCESS(f"Compte '{username}' prêt avec le rôle '{role}'."))
