"""
Jeu de données de démonstration : des administrations réelles avec des
évaluations clôturées, afin de voir les tableaux de bord, radars, comparaisons
et rapports remplis en conditions réelles.

    python manage.py seed_demo          # ajoute les données de démo
    python manage.py seed_demo --reset  # repart d'une base propre
"""
import random

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    Administration,
    Agent,
    Evaluation,
    Question,
    Reponse,
    VersionFormulaire,
)
from core.scoring import cloturer_evaluation

RESPONSABLES = [
    "Kossi Amegan", "Ama Dossou", "Yao Mensah", "Afi Koudjo",
    "Komlan Adjivon", "Essi Lawson", "Kodjo Bakari", "Adjo Nyaku",
]
POSTES = [
    "Agent d'accueil", "Secrétaire", "Chef de bureau", "Comptable",
    "Agent d'état civil", "Technicien", "Gestionnaire", "Archiviste",
    "Responsable RH", "Agent de saisie",
]
SERVICES = [
    "État civil", "Ressources humaines", "Comptabilité", "Urbanisme",
    "Service technique", "Accueil", "Secrétariat général", "Informatique",
]

# (nom, région, cibles de score par dimension, distribution N0..N5, clôturée ?)
ADMINISTRATIONS = [
    ("Mairie de Lomé", "Maritime",
     {"infra": 3.5, "services": 3.0, "juridique": 3.8, "engagement": 3.4},
     [8, 22, 40, 38, 24, 10], True),
    ("Préfecture de Kloto", "Plateaux",
     {"infra": 3.0, "services": 2.5, "juridique": 3.0, "engagement": 3.2},
     [12, 20, 18, 12, 6, 2], True),
    ("Commune d'Aného", "Maritime",
     {"infra": 3.8, "services": 3.5, "juridique": 3.2, "engagement": 3.6},
     [3, 8, 14, 18, 12, 7], True),
    ("Direction régionale de Kara", "Kara",
     {"infra": 2.4, "services": 2.0, "juridique": 2.6, "engagement": 2.5},
     [18, 22, 14, 6, 2, 0], True),
    ("Mairie de Sokodé", "Centrale",
     {"infra": 3.2, "services": 2.8, "juridique": 3.4, "engagement": 3.0},
     [6, 14, 20, 16, 8, 3], True),
    ("Commune de Kpalimé", "Plateaux",
     {"infra": 3.6, "services": 3.3, "juridique": 3.0, "engagement": 3.7},
     [4, 10, 16, 20, 14, 6], True),
    ("Préfecture de Tône", "Savanes",
     {"infra": 2.8, "services": 2.4, "juridique": 2.9, "engagement": 2.7},
     [14, 18, 16, 8, 4, 1], False),
    ("Direction régionale de Dapaong", "Savanes",
     {"infra": 2.6, "services": 2.2, "juridique": 2.5, "engagement": 2.8},
     [16, 20, 12, 6, 2, 0], False),
]


def _reponse_pour_cible(question, cible):
    """Valeur de réponse qui approche la note visée (0 à 5) pour une question."""
    code = question.type_champ.code
    if code == "texte_libre":
        return "Renseigné"
    if code == "echelle_1_5":
        return str(max(1, min(5, round(cible))))
    if code == "oui_non":
        return "oui" if cible >= 2.7 else "non"
    if code == "oui_non_partiel":
        return "oui" if cible >= 3.5 else ("partiel" if cible >= 2.2 else "non")
    if code in ("liste", "choix_multiple", "tranches"):
        from core.forms import choix_question
        from core.scoring import normaliser_reponse

        options = choix_question(question) or []
        notes = [(v, normaliser_reponse(v)) for v, _ in options]
        notes = [(v, n) for v, n in notes if n is not None]
        if notes:
            return min(notes, key=lambda t: abs(t[1] - cible))[0]
        return options[0][0] if options else "oui"
    return "oui"


class Command(BaseCommand):
    help = "Charge un jeu de données de démonstration (administrations + évaluations)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Supprime d'abord toutes les administrations et évaluations.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(42)
        call_command("seed_data")
        call_command("seed_recommandations")

        if options["reset"]:
            Reponse.objects.all().delete()
            Agent.objects.all().delete()
            Evaluation.objects.all().delete()
            Administration.objects.all().delete()
            self.stdout.write(self.style.WARNING("Administrations et évaluations remises à zéro."))

        version_a = VersionFormulaire.objects.get(formulaire__code="A", est_active=True)
        version_b = VersionFormulaire.objects.get(formulaire__code="B", est_active=True)
        questions_a = list(
            Question.objects.filter(version_formulaire=version_a, actif=True)
            .select_related("type_champ", "dimension")
            .prefetch_related("options")
        )

        for i, (nom, region, cibles, distrib, cloturee) in enumerate(ADMINISTRATIONS):
            administration, _ = Administration.objects.get_or_create(
                nom=nom, defaults={"region": region, "pays": "Togo"}
            )
            if Evaluation.objects.filter(administration=administration).exists():
                continue

            evaluation = Evaluation.objects.create(
                administration=administration,
                version_formulaire_a=version_a,
                version_formulaire_b=version_b,
                statut="en_cours",
                responsable_nom=f"{RESPONSABLES[i % len(RESPONSABLES)]}, chef du service informatique",
            )

            for question in questions_a:
                cible = cibles.get(question.dimension.code, 3.0)
                Reponse.objects.create(
                    evaluation=evaluation, question=question,
                    administration=administration,
                    valeur=_reponse_pour_cible(question, cible),
                )

            def _agent(numero, **extra):
                return Agent.objects.create(
                    administration=administration, evaluation=evaluation, numero=numero,
                    nom=f"{random.choice(RESPONSABLES).split()[0]} {random.choice('ABKMNPSY')}.",
                    poste=random.choice(POSTES), service=random.choice(SERVICES),
                    mode_saisie="assiste", **extra,
                )

            numero = 0
            for niveau, effectif in enumerate(distrib):
                for _ in range(effectif):
                    numero += 1
                    _agent(numero, statut="terminee", niveau_maturite=niveau,
                           reference=f"MN-2026-{administration.pk:03d}{numero:03d}")

            # Quelques enquêtes non terminées pour l'écran de l'enquêteur.
            numero += 1
            _agent(numero, statut="en_cours", progression=4)
            for _ in range(3):
                numero += 1
                _agent(numero, statut="a_faire")

            if cloturee:
                cloturer_evaluation(evaluation)
                self.stdout.write(self.style.SUCCESS(
                    f"{nom} : clôturée, score {evaluation.score_global} / 5, {numero} agents."
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"{nom} : évaluation en cours, {numero} agents enquêtés."
                ))

        self.stdout.write(self.style.SUCCESS("Données de démonstration prêtes."))
