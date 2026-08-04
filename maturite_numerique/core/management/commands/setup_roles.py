from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


ROLE_GROUPS = {
    "agent_evaluateur": ["view_administration", "view_agent", "view_reponse"],
    "agent_enquete": ["view_question", "view_reponse"],
    "enqueteur": ["view_question", "add_reponse", "change_reponse", "view_reponse"],
    "dsi_decideur": ["view_administration", "view_agent", "view_reponse"],
    "admin_contenu": ["add_question", "change_question", "delete_question", "view_question", "add_dimension", "change_dimension", "view_dimension", "view_formulaire", "view_versionformulaire"],
}


class Command(BaseCommand):
    help = "Crée les groupes Django correspondant aux rôles métier du projet."

    def handle(self, *args, **options):
        for role_name, codename_list in ROLE_GROUPS.items():
            group, _ = Group.objects.get_or_create(name=role_name)
            permissions = []
            for codename in codename_list:
                try:
                    permission = Permission.objects.get(codename=codename)
                except Permission.DoesNotExist:
                    continue
                permissions.append(permission)
            group.permissions.set(permissions)
            self.stdout.write(self.style.SUCCESS(f"Groupe '{role_name}' prêt."))
