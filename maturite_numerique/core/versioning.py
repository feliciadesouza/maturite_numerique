"""
Versionnage du questionnaire.

Règle métier : on n'écrase jamais une question qui a déjà des réponses. On
crée une nouvelle version du formulaire (clone de toutes ses questions), on y
applique la modification, et l'ancienne version reste archivée liée aux
réponses historiques. C'est ce qui permet de comparer une administration dans
le temps sans fausser les scores.
"""
from django.db import transaction
from django.db.models import Max

from .models import OptionReponse, Question, Reponse, VersionFormulaire


def version_a_des_reponses(version: VersionFormulaire) -> bool:
    """Vrai si au moins une question de cette version a reçu une réponse."""
    return Reponse.objects.filter(question__version_formulaire=version).exists()


@transaction.atomic
def dupliquer_version(version: VersionFormulaire) -> VersionFormulaire:
    """
    Crée la version suivante d'un formulaire en clonant ses questions, leurs
    options et leurs conditions d'affichage. La nouvelle version devient active
    (``VersionFormulaire.save`` garantit une seule version active).
    """
    dernier = (
        VersionFormulaire.objects.filter(formulaire=version.formulaire)
        .aggregate(m=Max("numero_version"))["m"]
        or 0
    )
    nouvelle = VersionFormulaire.objects.create(
        formulaire=version.formulaire,
        numero_version=dernier + 1,
        est_active=True,
    )

    clones = {}
    for question in version.questions.all():
        clone = Question.objects.create(
            dimension=question.dimension,
            version_formulaire=nouvelle,
            code=question.code,
            texte=question.texte,
            type_champ=question.type_champ,
            ordre=question.ordre,
            aide=question.aide,
            obligatoire=question.obligatoire,
            actif=question.actif,
            section=question.section,
            borne_min_label=question.borne_min_label,
            borne_max_label=question.borne_max_label,
            valeur_condition=question.valeur_condition,
        )
        clones[question.pk] = clone
        for option in question.options.all():
            OptionReponse.objects.create(
                question=clone,
                libelle=option.libelle,
                valeur=option.valeur,
                ordre=option.ordre,
            )

    # Recâblage des conditions d'affichage vers les clones.
    for ancienne_pk, clone in clones.items():
        cond_id = version.questions.get(pk=ancienne_pk).question_condition_id
        if cond_id in clones:
            clone.question_condition = clones[cond_id]
            clone.save(update_fields=["question_condition"])

    return nouvelle
