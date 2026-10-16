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

from core.forms import choix_question
from core.models import (
    Administration,
    Agent,
    Evaluation,
    Question,
    Reponse,
    VersionFormulaire,
)
from core.scoring import classifier_niveau_agent, cloturer_evaluation

RESPONSABLES = [
    ("Kossi", "Amegan"), ("Ama", "Dossou"), ("Yao", "Mensah"), ("Afi", "Koudjo"),
    ("Komlan", "Adjivon"), ("Essi", "Lawson"), ("Kodjo", "Bakari"), ("Adjo", "Nyaku"),
]
PRENOMS = [p for p, _ in RESPONSABLES]
NOMS = [n for _, n in RESPONSABLES]
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


def _valeur_intention(question, intention):
    """Résout une intention sémantique ('oui', 'smartphone', 'souvent'...) en
    la valeur technique réellement valide pour cette question (texte libre :
    l'intention sert telle quelle)."""
    if question.type_champ.code == "texte_libre":
        return intention
    for valeur, _ in choix_question(question) or []:
        if valeur.strip().lower() == intention.strip().lower():
            return valeur
    return intention


# Intentions communes aux 6 niveaux (n'influencent pas classifier_niveau_agent).
FREINS_COMMUN = {"B5.1": "non", "B5.2": "formation", "B5.3": "oui"}


def _intentions_formulaire_b(niveau):
    """Intentions de réponse (hors profil B1.x, propre à chaque agent) pour
    reproduire exactement `niveau` via classifier_niveau_agent (core/scoring.py).
    Ne pose que les questions visibles à ce niveau (mêmes règles que
    _sections_agent/CONDITIONS_B côté views.py) : un agent N0 n'a pas de
    réponses B3.x/B4.x, un agent N1 n'a pas B3.4/B3.6 (pas de smartphone)."""
    intentions = {"B2.1": "oui", "B2.2": "oui"}
    if niveau == 0:
        intentions["B2.1"] = "non"
        intentions["B2.2"] = "non"
        intentions.update(FREINS_COMMUN)
        return intentions

    intentions["B3.1"] = "oui"
    intentions["B3.2"] = "oui"
    if niveau >= 2:
        intentions["B3.3"] = "smartphone"
        intentions["B3.4"] = "oui"
        intentions["B3.5"] = "oui"
        intentions["B3.6"] = "oui"
    else:
        intentions["B3.3"] = "basique"
        intentions["B3.5"] = "non"

    intentions["B4.1"] = "souvent" if niveau >= 3 else "jamais"
    intentions["B4.2"] = "jamais"
    intentions["B4.3"] = "non"
    intentions["B4.4"] = "oui" if niveau >= 4 else "non"
    intentions["B4.5"] = "5" if niveau >= 5 else "2"
    intentions["B4.6"] = "oui" if niveau >= 5 else "non"
    intentions.update(FREINS_COMMUN)
    return intentions


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
        questions_b_par_code = {
            q.code: q
            for q in Question.objects.filter(version_formulaire=version_b, actif=True)
            .select_related("type_champ").prefetch_related("options")
        }
        tranches_age = [v for v, _ in choix_question(questions_b_par_code["B1.3"])]
        anciennetes = [v for v, _ in choix_question(questions_b_par_code["B1.4"])]
        niveaux_etudes = [v for v, _ in choix_question(questions_b_par_code["B1.5"])]

        # Réponses B2.x-B5.x (hors profil, propre à chaque agent) résolues une
        # seule fois par niveau 0-5 — garanties de reproduire exactement ce
        # niveau via classifier_niveau_agent (vérifié ci-dessous).
        reponses_b_par_niveau = {}
        for niveau in range(6):
            intentions = _intentions_formulaire_b(niveau)
            resolues = {
                code: _valeur_intention(questions_b_par_code[code], intention)
                for code, intention in intentions.items()
            }
            obtenu = classifier_niveau_agent(resolues)
            if obtenu != niveau:
                raise ValueError(
                    f"seed_demo : les réponses générées pour le niveau {niveau} "
                    f"donnent {obtenu} via classifier_niveau_agent — grille désynchronisée."
                )
            reponses_b_par_niveau[niveau] = resolues

        for i, (nom, region, cibles, distrib, cloturee) in enumerate(ADMINISTRATIONS):
            administration, _ = Administration.objects.get_or_create(
                nom=nom, defaults={"region": region, "pays": "Togo"}
            )
            if Evaluation.objects.filter(administration=administration).exists():
                continue

            prenom, nom_famille = RESPONSABLES[i % len(RESPONSABLES)]
            evaluation = Evaluation.objects.create(
                administration=administration,
                version_formulaire_a=version_a,
                version_formulaire_b=version_b,
                statut="en_cours",
                responsable_nom=nom_famille,
                responsable_prenom=prenom,
                responsable_fonction="Chef du service informatique",
            )

            Reponse.objects.bulk_create([
                Reponse(
                    evaluation=evaluation, question=question,
                    administration=administration,
                    valeur=_reponse_pour_cible(
                        question, cibles.get(question.dimension.code, 3.0)
                    ),
                )
                for question in questions_a
            ])

            def _agent(numero, **extra):
                return Agent(
                    administration=administration, evaluation=evaluation, numero=numero,
                    nom=random.choice(NOMS), prenom=random.choice(PRENOMS),
                    poste=random.choice(POSTES), service=random.choice(SERVICES),
                    tranche_age=random.choice(tranches_age),
                    anciennete=random.choice(anciennetes),
                    niveau_etudes=random.choice(niveaux_etudes),
                    mode_saisie="assiste", **extra,
                )

            lot_agents, agents_termines, numero = [], [], 0
            for niveau, effectif in enumerate(distrib):
                for _ in range(effectif):
                    numero += 1
                    agent = _agent(
                        numero, statut="terminee", niveau_maturite=niveau,
                        reference=f"MN-2026-{administration.pk:03d}{numero:03d}",
                    )
                    lot_agents.append(agent)
                    agents_termines.append((agent, niveau))

            # Quelques enquêtes non terminées pour l'écran de l'enquêteur.
            numero += 1
            lot_agents.append(_agent(numero, statut="en_cours", progression=4))
            for _ in range(3):
                numero += 1
                lot_agents.append(_agent(numero, statut="a_faire"))
            Agent.objects.bulk_create(lot_agents)

            # Réponses détaillées du Formulaire B pour les agents "terminée"
            # (le profil B1.x reprend les champs propres à l'agent, le reste
            # vient de reponses_b_par_niveau) : sans ça, "Voir" sur un agent
            # de démo n'affichait aucune réponse (seul niveau_maturite était
            # renseigné).
            lot_reponses_b = []
            for agent, niveau in agents_termines:
                profil = {
                    "B1.0": agent.nom, "B1.0b": agent.prenom,
                    "B1.1": agent.poste, "B1.2": agent.service,
                    "B1.3": agent.tranche_age, "B1.4": agent.anciennete,
                    "B1.5": agent.niveau_etudes,
                }
                valeurs = {**profil, **reponses_b_par_niveau[niveau]}
                lot_reponses_b.extend(
                    Reponse(
                        evaluation=evaluation, agent=agent, administration=administration,
                        question=questions_b_par_code[code], valeur=valeur,
                    )
                    for code, valeur in valeurs.items()
                )
            Reponse.objects.bulk_create(lot_reponses_b)

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
