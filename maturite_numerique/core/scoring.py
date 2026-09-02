"""
Moteur de scoring de l'outil de suivi de la maturité numérique.

Ce module contient uniquement de la logique métier pure (aucune dépendance
à une vue ou un template), afin de pouvoir être développé et testé dès
maintenant, indépendamment de la maquette.
"""
from dataclasses import dataclass

from django.core.cache import cache
from django.utils import timezone

from .models import (
    Administration,
    Agent,
    Dimension,
    Recommandation,
    RegleRecommandation,
    Reponse,
)


def dimensions_actives():
    """Dimensions actives, triées, mises en cache 5 min.

    Le référentiel change seulement en back-office (qui vide ce cache) ; sans
    cela, chaque `resultat_administration` / `calculer_score_dimension`
    relance la même requête — coûteux quand on itère sur les administrations
    (tableau de bord, liste, comparaison, rapports).
    """
    return list(
        cache.get_or_set(
            "scoring:dimensions_actives",
            lambda: list(Dimension.objects.filter(actif=True).order_by("ordre")),
            300,
        )
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


def calculer_score_dimension(administration: Administration, dimension: Dimension,
                             *, evaluation=None) -> ScoreDimension:
    """Score d'une dimension. Rattaché à une évaluation (campagne) si fournie,
    sinon à toutes les réponses de l'administration (compat / rétro-calcul)."""
    reponses = Reponse.objects.filter(question__dimension=dimension)
    if evaluation is not None:
        reponses = reponses.filter(evaluation=evaluation)
    else:
        reponses = reponses.filter(administration=administration)
    reponses = reponses.select_related("question")

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
    scores = [calculer_score_dimension(administration, d) for d in dimensions_actives()]

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
    La comparaison est insensible à la casse (les options peuvent être des slugs).
    """
    def v(code):
        return (reponses_agent.get(code) or "").strip().lower()

    if v("B2.1") == "non":
        return 0  # N'a jamais utilisé un ordinateur

    niveau = 1  # sait allumer/utiliser un ordinateur (implicite si B2.1 = Oui)

    if v("B3.4") == "oui" or v("B3.5") == "oui":
        niveau = 2  # WhatsApp / réseaux sociaux / email de base

    if v("B4.1") in ("souvent", "rarement") or v("B4.2") in ("souvent", "rarement"):
        niveau = 3  # Word / Excel occasionnellement

    if v("B4.4") == "oui":
        niveau = 4  # Outils métier, autonome

    if v("B4.6") == "oui" and niveau >= 4:
        niveau = 5  # Capable de former d'autres agents

    return niveau


def reponses_par_code(agent) -> dict:
    """Réponses d'un agent sous forme {code_question: valeur}."""
    return {
        r.question.code: r.valeur
        for r in agent.reponses.select_related("question")
    }


def distribution_niveaux_administration(administration: Administration) -> dict:
    """Distribution N0-N5 de TOUS les agents d'une administration (toutes campagnes)."""
    agents = Agent.objects.filter(administration=administration, niveau_maturite__isnull=False)
    distribution = {n: 0 for n in range(6)}
    for agent in agents:
        distribution[agent.niveau_maturite] += 1
    return distribution


def distribution_niveaux(evaluation) -> dict:
    """Distribution N0-N5 des agents rattachés à UNE évaluation (campagne)."""
    distribution = {n: 0 for n in range(6)}
    if evaluation is None:
        return distribution
    agents = Agent.objects.filter(evaluation=evaluation, niveau_maturite__isnull=False)
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


def score_dimension_competences(distribution: dict):
    """
    Score sur 5 de la dimension "Compétences numériques" à partir de la
    distribution des agents sur les niveaux 0 à 5 : moyenne des niveaux
    pondérée par les effectifs (un niveau 0-5 valant déjà une note sur 5).
    Renvoie None si aucun agent n'est classé (dimension « en attente » :
    à distinguer d'un vrai score de 0 où tous les agents seraient N0).
    """
    total = sum(distribution.values())
    if not total:
        return None
    somme = sum(int(niveau) * effectif for niveau, effectif in distribution.items())
    return round(somme / total, 2)


def _instantane(evaluation, distribution):
    """Scores par dimension + score global pondéré d'une évaluation.
    Une dimension sans donnée (compétences sans répondant) vaut None et est
    exclue du global, dont les pondérations sont renormalisées sur le reste."""
    administration = evaluation.administration
    scores_par_id, scores_par_code = {}, {}
    poids_pris, somme_ponderee = 0.0, 0.0
    for dimension in dimensions_actives():
        if dimension.code == "competences":
            brut = score_dimension_competences(distribution)
        else:
            brut = calculer_score_dimension(
                administration, dimension, evaluation=evaluation
            ).score_brut
        scores_par_id[str(dimension.pk)] = brut
        if dimension.code:
            scores_par_code[dimension.code] = brut
        if brut is not None:
            poids_pris += float(dimension.poids)
            somme_ponderee += brut * float(dimension.poids)
    score_global = round(somme_ponderee / poids_pris, 2) if poids_pris else 0.0
    return scores_par_id, scores_par_code, score_global


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


@dataclass
class ResultatAdministration:
    administration: Administration
    evaluation: object          # Evaluation clôturée, ou None
    score_global: float
    niveau: str                 # libellé de maturité
    badge: str                  # 'faible' / 'moyen' / 'fort'
    scores_dimensions: list     # [{dimension, score, badge, en_attente}]
    distribution: dict          # {0..5: effectif}
    recommandations: list       # [{priorite, texte, dimension}]
    est_apercu: bool            # True si calculé à la volée (pas de clôture)


def resultat_administration(administration) -> ResultatAdministration:
    """
    Résultats d'une administration : depuis l'instantané figé s'il existe une
    évaluation terminée, sinon calculés à la volée sur l'évaluation en cours.
    """
    evaluation = (
        administration.evaluations.filter(statut="terminee")
        .order_by("-date_cloture", "-id")
        .first()
    )
    dimensions = dimensions_actives()
    distribution = {n: 0 for n in range(6)}

    if evaluation and evaluation.score_global is not None:
        scores_par_id = {
            str(k): (float(v) if v is not None else None)
            for k, v in (evaluation.score_par_dimension or {}).items()
        }
        dist_json = evaluation.distribution_niveaux or {}
        if dist_json:
            distribution = {int(k): v for k, v in dist_json.items()}
        recos = [
            {"priorite": r.priorite, "texte": r.texte, "dimension": r.dimension}
            for r in evaluation.recommandations.all()
        ]
        score_global = float(evaluation.score_global)
        est_apercu = False
    else:
        apercu = (
            administration.evaluations.exclude(statut="archivee")
            .order_by("-date_ouverture", "-id")
            .first()
        )
        distribution = distribution_niveaux(apercu)
        if apercu is not None:
            scores_par_id, scores_par_code, score_global = _instantane(apercu, distribution)
        else:
            scores_par_id, scores_par_code, score_global = {}, {}, 0.0
        recos = generer_recommandations(
            {k: v for k, v in scores_par_code.items() if v is not None}
        )
        for reco in recos:
            reco["dimension"] = None
        est_apercu = True

    scores_dimensions = []
    for dimension in dimensions:
        brut = scores_par_id.get(str(dimension.pk))
        if brut is None:
            scores_dimensions.append(
                {"dimension": dimension, "score": None, "badge": "neutre", "en_attente": True}
            )
        else:
            valeur = round(float(brut), 2)
            scores_dimensions.append(
                {"dimension": dimension, "score": valeur,
                 "badge": badge_score(valeur), "en_attente": False}
            )

    return ResultatAdministration(
        administration=administration,
        evaluation=evaluation,
        score_global=score_global,
        niveau=niveau_libelle(score_global),
        badge=badge_score(score_global),
        scores_dimensions=scores_dimensions,
        distribution={n: distribution.get(n, 0) for n in range(6)},
        recommandations=recos,
        est_apercu=est_apercu,
    )


def cloturer_evaluation(evaluation) -> None:
    """
    Fige l'instantané de résultats d'une évaluation (scores par dimension,
    distribution, score global pondéré, libellé) et matérialise ses
    recommandations. Idempotent : rappelable pour recalculer tant que
    l'évaluation n'est pas archivée.
    """
    distribution = distribution_niveaux(evaluation)
    scores_par_id, scores_par_code, score_global = _instantane(evaluation, distribution)

    evaluation.score_global = score_global
    evaluation.score_par_dimension = scores_par_id
    evaluation.distribution_niveaux = {str(k): v for k, v in distribution.items()}
    evaluation.niveau_libelle = niveau_libelle(score_global)
    evaluation.statut = "terminee"
    evaluation.date_cloture = timezone.now().date()
    evaluation.save()

    scores_reco = {k: v for k, v in scores_par_code.items() if v is not None}
    evaluation.recommandations.all().delete()
    for index, reco in enumerate(generer_recommandations(scores_reco)):
        Recommandation.objects.create(
            evaluation=evaluation,
            priorite=reco["priorite"],
            texte=reco["texte"],
            ordre=index,
        )
