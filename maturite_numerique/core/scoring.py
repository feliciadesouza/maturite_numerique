"""
Moteur de scoring de l'outil de suivi de la maturité numérique.

Ce module contient uniquement de la logique métier pure (aucune dépendance
à une vue ou un template), afin de pouvoir être développé et testé dès
maintenant, indépendamment de la maquette.
"""
from dataclasses import dataclass

from django.utils import timezone

from .models import (
    Administration,
    Agent,
    Dimension,
    Recommandation,
    RegleRecommandation,
    Reponse,
)


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


# --- Libellés, badges et clôture d'une évaluation ---

# Paliers de maturité pour un score global sur 5 (borne haute exclue).
PALIERS_NIVEAU = [
    (1.5, "Initial"),
    (2.5, "Émergent"),
    (3.5, "Intermédiaire"),
    (4.5, "Avancé"),
]


def niveau_libelle(score: float) -> str:
    """Libellé de maturité (5 paliers) pour un score global sur 5."""
    for seuil, libelle in PALIERS_NIVEAU:
        if score < seuil:
            return libelle
    return "Optimisé"


def badge_score(score: float) -> str:
    """Classe d'un score : 'faible' (< 2,5), 'moyen' (2,5-3,5), 'fort' (>= 3,5)."""
    if score < 2.5:
        return "faible"
    if score < 3.5:
        return "moyen"
    return "fort"


def score_dimension_competences(distribution: dict) -> float:
    """
    Score sur 5 de la dimension "Compétences numériques" à partir de la
    distribution des agents sur les niveaux 0 à 5 : moyenne des niveaux
    pondérée par les effectifs (un niveau 0-5 valant déjà une note sur 5).
    Renvoie 0.0 si aucun agent n'est classé.
    """
    total = sum(distribution.values())
    if not total:
        return 0.0
    somme = sum(int(niveau) * effectif for niveau, effectif in distribution.items())
    return round(somme / total, 2)


def generer_recommandations(scores_par_code: dict) -> list:
    """
    Applique les RegleRecommandation aux scores d'une évaluation.
    `scores_par_code` : {code_dimension: score_sur_5}. Renvoie une liste de
    dicts {priorite, dimension_code, texte} triée par priorité puis par ordre.
    """
    recos = []
    for regle in RegleRecommandation.objects.all():
        score = scores_par_code.get(regle.dimension_code)
        if score is not None and score <= float(regle.seuil_max):
            recos.append({
                "priorite": regle.priorite,
                "dimension_code": regle.dimension_code,
                "texte": regle.texte,
                "ordre": regle.ordre,
            })
    recos.sort(key=lambda r: (r["priorite"], r["ordre"]))
    return recos


def cloturer_evaluation(evaluation) -> None:
    """
    Fige l'instantané de résultats d'une évaluation (scores par dimension,
    distribution, score global pondéré, libellé) et matérialise ses
    recommandations. Idempotent : rappelable pour recalculer tant que
    l'évaluation n'est pas archivée.
    """
    administration = evaluation.administration
    distribution = distribution_niveaux_administration(administration)

    scores_par_id = {}
    scores_par_code = {}
    score_global = 0.0
    for dimension in Dimension.objects.filter(actif=True):
        if dimension.code == "competences":
            brut = score_dimension_competences(distribution)
        else:
            brut = calculer_score_dimension(administration, dimension).score_brut
        scores_par_id[str(dimension.pk)] = brut
        if dimension.code:
            scores_par_code[dimension.code] = brut
        score_global += brut * float(dimension.poids)

    evaluation.score_global = round(score_global, 2)
    evaluation.score_par_dimension = scores_par_id
    evaluation.distribution_niveaux = {str(k): v for k, v in distribution.items()}
    evaluation.niveau_libelle = niveau_libelle(evaluation.score_global)
    evaluation.statut = "terminee"
    evaluation.date_cloture = timezone.now().date()
    evaluation.save()

    evaluation.recommandations.all().delete()
    for index, reco in enumerate(generer_recommandations(scores_par_code)):
        Recommandation.objects.create(
            evaluation=evaluation,
            priorite=reco["priorite"],
            texte=reco["texte"],
            ordre=index,
        )
