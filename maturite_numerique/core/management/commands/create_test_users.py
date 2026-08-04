from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import Utilisateur


User = get_user_model()


TEST_USERS = [
    ("agent_eval", "AgentEval123!", "agent_evaluateur"),
    ("agent_enquete", "AgentEnquete123!", "agent_enquete"),
    ("enqueteur", "Enqueteur123!", "enqueteur"),
    ("dsi", "Dsi123!", "dsi_decideur"),
    ("admin_contenu", "Admin123!", "admin_contenu"),
]


class Command(BaseCommand):
    help = "Crée des comptes de test et les profils métier associés pour le projet."

    def handle(self, *args, **options):
        for username, password, role in TEST_USERS:
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password(password)
                user.save()
            profil, _ = Utilisateur.objects.get_or_create(user=user)
            profil.role = role
            profil.save()
            self.stdout.write(self.style.SUCCESS(f"Compte '{username}' prêt avec le rôle '{role}'."))
