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

# Superuser de test : mot de passe connu, resynchronisé à chaque exécution
# (contrairement aux comptes de rôle, on ne se fie pas au « if created »).
SUPERUSER = ("admin", "Admin123!", "admin@maturite-numerique.tg")

# Rôles rattachés à une administration pour les parcours de collecte.
ROLES_AVEC_ADMINISTRATION = {"agent_evaluateur", "enqueteur"}


class Command(BaseCommand):
    help = "Crée des comptes de test et les profils métier associés pour le projet."

    def handle(self, *args, **options):
        administration, _ = Administration.objects.get_or_create(
            nom="Mairie de Lomé", defaults={"region": "Maritime", "pays": "Togo"}
        )

        su_name, su_pwd, su_email = SUPERUSER
        su, _ = User.objects.get_or_create(
            username=su_name, defaults={"email": su_email}
        )
        su.is_staff = su.is_superuser = su.is_active = True
        su.set_password(su_pwd)
        su.save()
        self.stdout.write(self.style.SUCCESS(f"Superuser '{su_name}' prêt."))

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
            if role == "enqueteur":
                # Affectation de l'enquêteur : sa Mairie + toute autre administration
                # existante, pour exercer le cas « plusieurs administrations ».
                administration.enqueteurs.add(user)
                for autre in Administration.objects.exclude(pk=administration.pk)[:1]:
                    autre.enqueteurs.add(user)
            self.stdout.write(self.style.SUCCESS(f"Compte '{username}' prêt avec le rôle '{role}'."))
