import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Crée ou met à jour le superuser d'administration à partir des variables "
        "DJANGO_SUPERUSER_USERNAME / _PASSWORD / _EMAIL. Idempotent : rejoué à "
        "chaque démarrage du conteneur, il resynchronise le mot de passe."
    )

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not username or not password:
            self.stdout.write("DJANGO_SUPERUSER_USERNAME/PASSWORD non défini — ignoré.")
            return

        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username, defaults={"email": email}
        )
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        if email and not user.email:
            user.email = email
        user.set_password(password)
        user.save()
        etat = "créé" if created else "mis à jour"
        self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' {etat}."))
