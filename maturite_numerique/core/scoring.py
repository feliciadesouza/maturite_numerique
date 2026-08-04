"""
Moteur de scoring de l'outil de suivi de la maturité numérique.

Ce module contient uniquement de la logique métier pure (aucune dépendance
à une vue ou un template), afin de pouvoir être développé et testé dès
maintenant, indépendamment de la maquette.
"""
from dataclasses import dataclass
from decimal import Decimal

from .models import Dimension, Reponse, Administration, Agent


@dataclass
class ScoreDimension:
    dimension: Dimension
    score_brut: float          # moyenne des réponses normalisées (0 à 5)
    score_pondere: float       # score_brut * poids de la dimension


@dataclass
class ScoreGlobal:
    administration: Administration
    scores_par_dimension: list
    score_global: float        # somme des scores pondérés, sur 5
    dimension_la_plus_faible: Dimension


# Barème de conversion des valeurs de réponse en note de 0 à 5.
# À affiner selon le type de champ (échelle 1-5 déjà numérique,
# Oui/Non/Partiel à convertir, tranches % à convertir...).
BAREME_OUI_NON = {
    "oui": 5, "non": 0, "partiel": 2.5,
    "en_cours": 2.5, "non_applicable": None,
}
BAREME_TRANCHES = {
    "<25%": 1, "25-50%": 2.5, "50-75%": 3.5, ">75%": 5,
    "0-25%": 1, "75-100%": 5,
}


def normaliser_reponse(valeur: str) -> float | None:
    """Convertit une valeur brute de réponse en note sur 5."""
    v = valeur.strip().lower()
    if v.replace(".", "", 1).isdigit():
        # Échelle 1-5 déjà numérique
        return float(v)
    if v in BAREME_OUI_NON:
        return BAREME_OUI_NON[v]
    if v in BAREME_TRANCHES:
        return BAREME_TRANCHES[v]
    return None


def calculer_score_dimension(administration: Administration, dimension: Dimension) -> ScoreDimension:
    """Calcule le score d'une administration pour une dimension donnée."""
    reponses = Reponse.objects.filter(
        administration=administration, question__dimension=dimension
    ).select_related("question")

    notes = []
    for r in reponses:
        note = normaliser_reponse(r.valeur)
        if note is not None:
            notes.append(note)

    score_brut = sum(notes) / len(notes) if notes else 0.0
    score_pondere = score_brut * float(dimension.poids)
    return ScoreDimension(dimension=dimension, score_brut=round(score_brut, 2), score_pondere=round(score_pondere, 3))


def calculer_score_global(administration: Administration) -> ScoreGlobal:
    """Calcule le score global d'une administration, dimension par dimension."""
    dimensions = Dimension.objects.filter(actif=True)
    scores = [calculer_score_dimension(administration, d) for d in dimensions]

    score_global = sum(s.score_pondere for s in scores)
    dimension_faible = min(scores, key=lambda s: s.score_brut).dimension if scores else None

    return ScoreGlobal(
        administration=administration,
        scores_par_dimension=scores,
        score_global=round(score_global, 2),
        dimension_la_plus_faible=dimension_faible,
    )


# --- Classification du niveau de maturité individuelle (Formulaire B) ---

def classifier_niveau_agent(reponses_agent: dict) -> int:
    """
    Calcule le niveau de maturité (0 à 5) d'un agent à partir de ses réponses
    au Formulaire B, selon la grille de classification définie au chapitre 3.

    `reponses_agent` : dict {code_question: valeur}, ex. {"B2.1": "Non", "B3.1": "Oui", ...}
    """
    if reponses_agent.get("B2.1", "").lower() == "non":
        return 0  # N'a jamais utilisé un ordinateur

    niveau = 1  # sait allumer/utiliser un ordinateur (implicite si B2.1 = Oui)

    if reponses_agent.get("B3.4") == "Oui" or reponses_agent.get("B3.5") == "Oui":
        niveau = 2  # WhatsApp / réseaux sociaux / email de base

    if reponses_agent.get("B4.1") in ("Souvent", "Rarement") or reponses_agent.get("B4.2") in ("Souvent", "Rarement"):
        niveau = 3  # Word / Excel occasionnellement

    if reponses_agent.get("B4.4") == "Oui":
        niveau = 4  # Outils métier, autonome

    if reponses_agent.get("B4.6") == "Oui" and niveau >= 4:
        niveau = 5  # Capable de former d'autres agents

    return niveau


def distribution_niveaux_administration(administration: Administration) -> dict:
    """
    Distribution des agents d'une administration sur les 6 niveaux (0 à 5).
    Utilisé pour le score de la dimension "Compétences numériques" - on ne
    prend jamais une simple moyenne, cf. justification au chapitre 3.
    """
    agents = Agent.objects.filter(administration=administration, niveau_maturite__isnull=False)
    distribution = {n: 0 for n in range(6)}
    for agent in agents:
        distribution[agent.niveau_maturite] += 1
    return distribution
