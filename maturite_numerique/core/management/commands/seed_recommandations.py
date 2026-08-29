from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import RegleRecommandation


# (code dimension, seuil de score sur 5, priorité, texte, ordre)
# La règle s'applique si le score de la dimension est <= seuil.
REGLES = [
    ("competences", 2.5, "P1",
     "Former les agents aux usages numériques de base (bureautique, messagerie).", 1),
    ("competences", 3.5, "P2",
     "Mettre en place un plan de montée en compétences ciblé par service.", 2),
    ("juridique", 2.0, "P1",
     "Se mettre en conformité avec la loi n°2019-014 sur les données personnelles.", 3),
    ("juridique", 3.0, "P1",
     "Établir une charte de protection des données (loi n°2019-014).", 4),
    ("infra", 2.5, "P1",
     "Sécuriser la connectivité et le parc d'équipements prioritaires.", 5),
    ("infra", 3.5, "P3",
     "Formaliser une procédure de sauvegarde et de maintenance.", 6),
    ("services", 2.0, "P1",
     "Ouvrir un canal de dépôt de demandes sans déplacement pour les usagers.", 7),
    ("services", 3.0, "P2",
     "Publier un premier service en ligne pilote pour les usagers.", 8),
    ("engagement", 2.5, "P1",
     "Inscrire la transformation numérique dans une stratégie validée par la direction.", 9),
    ("engagement", 3.0, "P3",
     "Nommer un référent numérique institutionnel.", 10),
]


class Command(BaseCommand):
    help = "Charge les règles de génération des recommandations priorisées."

    @transaction.atomic
    def handle(self, *args, **options):
        for code, seuil, priorite, texte, ordre in REGLES:
            RegleRecommandation.objects.update_or_create(
                dimension_code=code, texte=texte,
                defaults={"seuil_max": seuil, "priorite": priorite, "ordre": ordre},
            )
        self.stdout.write(self.style.SUCCESS(f"{len(REGLES)} règles de recommandation chargées."))
