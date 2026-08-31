from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import (
    Dimension,
    Formulaire,
    OptionReponse,
    Question,
    TypeChamp,
    VersionFormulaire,
)


# (code, nom, description, poids, ordre, couleur, icône Lucide)
DIMENSIONS = [
    ("infra", "Infrastructure TIC",
     "Équipements, réseaux, serveurs et connectivité disponibles", 0.20, 1, "#3E90F0", "server"),
    ("services", "Services en ligne",
     "Disponibilité et accessibilité des services publics numériques", 0.20, 2, "#4FBF88", "globe"),
    ("competences", "Compétences numériques",
     "Niveau réel des agents, mesuré par enquête et restitué en distribution (N0-N5)",
     0.25, 3, "#F2B33D", "users"),
    ("juridique", "Cadre juridique",
     "Textes, conformité et protection des données à caractère personnel", 0.15, 4, "#8B6FE0", "scale"),
    ("engagement", "Engagement institutionnel",
     "Stratégie, budget et portage humain de la transformation numérique", 0.20, 5, "#E85D74", "flag"),
]

TYPES_CHAMP = [
    ("Choix unique (Oui/Non)", "oui_non"),
    ("Choix unique (Oui/Non/Partiel)", "oui_non_partiel"),
    ("Choix unique (tranches %)", "tranches"),
    ("Échelle 1-5", "echelle_1_5"),
    ("Texte libre", "texte_libre"),
    ("Liste déroulante", "liste"),
    ("Choix multiple", "choix_multiple"),
]

# Jeux d'options réutilisables — la valeur sert au barème de scoring.
OPT_OUI_NON_PARTIEL = [("oui", "Oui"), ("non", "Non"), ("partiel", "Partiel")]
OPT_OUI_NON_ENCOURS = [("oui", "Oui"), ("non", "Non"), ("en_cours", "En cours")]
OPT_OUI_NON_NA = [("oui", "Oui"), ("non", "Non"), ("non_applicable", "Non applicable")]
OPT_TRANCHES_LT = [
    ("<25%", "Moins de 25 %"), ("25-50%", "25 à 50 %"),
    ("50-75%", "50 à 75 %"), (">75%", "Plus de 75 %"),
]
OPT_TRANCHES_0 = [
    ("0-25%", "0 à 25 %"), ("25-50%", "25 à 50 %"),
    ("50-75%", "50 à 75 %"), ("75-100%", "75 à 100 %"),
]
OPT_FREQ = [("jamais", "Jamais"), ("rarement", "Rarement"), ("souvent", "Souvent")]
OPT_AGE = [
    ("<30", "Moins de 30 ans"), ("30-45", "30 à 45 ans"),
    ("45-55", "45 à 55 ans"), (">55", "Plus de 55 ans"),
]
OPT_ANCIENNETE = [
    ("<5", "Moins de 5 ans"), ("5-15", "5 à 15 ans"), (">15", "Plus de 15 ans"),
]
OPT_ETUDES = [
    ("aucun", "Aucun diplôme"), ("primaire", "Primaire"),
    ("college", "Collège / BEPC"), ("bac", "Baccalauréat"),
    ("superieur", "Études supérieures"),
]
OPT_TEL = [("smartphone", "Smartphone"), ("basique", "Téléphone basique"), ("aucun", "Aucun")]
OPT_ORDI_POSTE = [("oui", "Oui"), ("non", "Non"), ("partage", "Partagé avec des collègues")]
OPT_FREINS = [
    ("formation", "Manque de formation"),
    ("materiel", "Manque de matériel"),
    ("confiance", "Peur ou manque de confiance"),
    ("inutile", "Pas utile pour mon poste"),
    ("aucun", "Aucun frein"),
]

# Formulaire A — groupe -> [(code, texte, type_code, options|None)]
# Le groupe « identification » est rattaché à la dimension Infrastructure mais
# porté par la section "identification" (première étape, hors dimension).
FORMULAIRE_A = {
    "identification": [
        ("A0.1", "Nom et prénom du responsable", "texte_libre", None),
        ("A0.2", "Fonction / poste occupé", "texte_libre", None),
    ],
    "Infrastructure TIC": [
        ("1.1", "L'administration dispose-t-elle d'une connexion internet stable ?", "echelle_1_5", None),
        ("1.2", "Quel est le taux d'équipement en ordinateurs par agent ?", "liste", OPT_TRANCHES_LT),
        ("1.3", "L'administration dispose-t-elle de serveurs propres ou d'un accès à un cloud "
                "gouvernemental ?", "liste", OPT_OUI_NON_ENCOURS),
        ("1.4", "Existe-t-il un réseau local interconnectant les services ?", "liste", OPT_OUI_NON_PARTIEL),
        ("1.5", "Un dispositif de sauvegarde des données est-il en place ?", "liste", OPT_OUI_NON_PARTIEL),
        ("1.6", "Un service de maintenance informatique est-il disponible (interne ou externalisé) ?",
                "oui_non", None),
    ],
    "Services en ligne": [
        ("2.1", "Quel pourcentage des services de l'administration est disponible en ligne ?",
                "liste", OPT_TRANCHES_0),
        ("2.2", "Les usagers peuvent-ils soumettre une demande sans se déplacer physiquement ?",
                "liste", OPT_OUI_NON_PARTIEL),
        ("2.3", "Existe-t-il un site web ou portail officiel actif et à jour ?", "oui_non", None),
        ("2.4", "Un système de suivi de dossier en ligne est-il proposé ?", "oui_non", None),
        ("2.5", "Les paiements en ligne sont-ils possibles pour les services concernés ?",
                "liste", OPT_OUI_NON_NA),
        ("2.6", "Une plateforme de dépôt de réclamations en ligne existe-t-elle ?", "oui_non", None),
    ],
    "Cadre juridique": [
        ("4.1", "L'administration applique-t-elle une politique de protection des données personnelles ?",
                "liste", OPT_OUI_NON_PARTIEL),
        ("4.2", "Un texte encadrant la signature électronique existe-t-il dans vos procédures ?",
                "oui_non", None),
        ("4.3", "Une charte ou politique de cybersécurité est-elle formalisée ?", "oui_non", None),
        ("4.4", "L'administration est-elle en conformité avec la loi nationale sur les données "
                "personnelles ?", "liste", OPT_OUI_NON_NA),
        ("4.5", "Les agents sont-ils sensibilisés aux risques de cybersécurité ?",
                "liste", OPT_OUI_NON_PARTIEL),
    ],
    "Engagement institutionnel": [
        ("5.1", "Existe-t-il une stratégie numérique formalisée et validée par la direction ?",
                "liste", OPT_OUI_NON_ENCOURS),
        ("5.2", "Un budget dédié à la transformation numérique est-il alloué chaque année ?",
                "liste", OPT_OUI_NON_PARTIEL),
        ("5.3", "La direction communique-t-elle régulièrement sur les avancées numériques ?",
                "oui_non", None),
        ("5.4", "Un responsable ou comité de pilotage de la transformation numérique existe-t-il ?",
                "oui_non", None),
        ("5.5", "Le personnel est-il impliqué dans la définition des priorités numériques ?",
                "echelle_1_5", None),
    ],
}

# Formulaire B — (code, texte, type_code, options|None, section)
FORMULAIRE_B = [
    ("B0.1", "À quelle administration appartenez-vous ?", "liste", None, "administration"),

    ("B1.0", "Nom et prénom", "texte_libre", None, "profil"),
    ("B1.1", "Poste occupé / fonction", "texte_libre", None, "profil"),
    ("B1.2", "Service / direction", "texte_libre", None, "profil"),
    ("B1.3", "Tranche d'âge", "liste", OPT_AGE, "profil"),
    ("B1.4", "Ancienneté dans l'administration", "liste", OPT_ANCIENNETE, "profil"),
    ("B1.5", "Niveau d'études", "liste", OPT_ETUDES, "profil"),

    ("B2.1", "Avez-vous déjà utilisé un ordinateur, ne serait-ce qu'une fois ?", "oui_non", None, "bases"),
    ("B2.2", "Disposez-vous d'un ordinateur à votre poste de travail (même si vous ne l'utilisez "
             "pas) ?", "liste", OPT_ORDI_POSTE, "bases"),

    ("B3.1", "Savez-vous allumer/éteindre un ordinateur seul ?", "oui_non", None, "bases_suite"),
    ("B3.2", "Savez-vous utiliser une souris et un clavier ?", "oui_non", None, "bases_suite"),
    ("B3.3", "Possédez-vous un téléphone portable ?", "liste", OPT_TEL, "bases_suite"),
    ("B3.4", "Si smartphone, utilisez-vous WhatsApp ou les réseaux sociaux ?", "oui_non", None, "bases_suite"),
    ("B3.5", "Avez-vous une adresse email personnelle ou professionnelle ?", "oui_non", None, "bases_suite"),
    ("B3.6", "Si oui, la consultez-vous au moins une fois par semaine ?", "oui_non", None, "bases_suite"),

    ("B4.1", "Utilisez-vous Word ou un traitement de texte dans votre travail ?", "liste", OPT_FREQ, "usage"),
    ("B4.2", "Utilisez-vous Excel ou un tableur dans votre travail ?", "liste", OPT_FREQ, "usage"),
    ("B4.3", "Avez-vous déjà rempli un formulaire administratif en ligne ?", "oui_non", None, "usage"),
    ("B4.4", "Utilisez-vous un logiciel métier propre à l'administration ?", "liste", OPT_OUI_NON_NA, "usage"),
    ("B4.5", "Vous sentez-vous capable d'apprendre seul(e) un nouvel outil numérique ?",
             "echelle_1_5", None, "usage"),
    ("B4.6", "Seriez-vous capable d'aider un collègue sur un outil numérique ?", "oui_non", None, "usage"),

    ("B5.1", "Avez-vous déjà suivi une formation en informatique ?", "oui_non", None, "freins"),
    ("B5.2", "Quel est le principal frein à votre usage du numérique ?", "liste", OPT_FREINS, "freins"),
    ("B5.3", "Seriez-vous intéressé(e) par une formation aux outils numériques ?", "oui_non", None, "freins"),
]

# Bornes affichées aux extrémités des questions « échelle 1 à 5 ».
BORNES_ECHELLE = {
    "1.1": ("Aucune", "Excellente"),
    "5.5": ("Pas du tout", "Fortement"),
    "B4.5": ("Pas du tout", "Tout à fait"),
}

# Conditions d'affichage : {code: (code de la question dont dépend l'affichage, valeur attendue)}
CONDITIONS_B = {
    "B3.4": ("B3.3", "smartphone"),
    "B3.6": ("B3.5", "oui"),
}


class Command(BaseCommand):
    help = "Charge le questionnaire de départ : dimensions, types de champ, Formulaires A et B."

    @transaction.atomic
    def handle(self, *args, **options):
        dim_objs = {}
        for code, nom, description, poids, ordre, couleur, icone in DIMENSIONS:
            dim, _ = Dimension.objects.update_or_create(
                nom=nom,
                defaults={
                    "code": code, "description": description, "poids": poids,
                    "ordre": ordre, "couleur": couleur, "icone": icone,
                },
            )
            dim_objs[nom] = dim
        self.stdout.write(self.style.SUCCESS(f"{len(dim_objs)} dimensions chargées."))

        type_objs = {}
        for libelle, code in TYPES_CHAMP:
            t, _ = TypeChamp.objects.update_or_create(code=code, defaults={"libelle": libelle})
            type_objs[code] = t

        form_a, _ = Formulaire.objects.update_or_create(
            code="A", defaults={"nom": "Formulaire A - Fiche Administration"}
        )
        form_b, _ = Formulaire.objects.update_or_create(
            code="B", defaults={"nom": "Formulaire B - Enquête individuelle agent"}
        )
        version_a, _ = VersionFormulaire.objects.get_or_create(
            formulaire=form_a, numero_version=1, defaults={"est_active": True}
        )
        version_b, _ = VersionFormulaire.objects.get_or_create(
            formulaire=form_b, numero_version=1, defaults={"est_active": True}
        )

        def enregistrer(code, texte, type_code, options, version, dimension, section, ordre):
            borne_min, borne_max = BORNES_ECHELLE.get(code, ("", ""))
            question, _ = Question.objects.update_or_create(
                code=code, version_formulaire=version,
                defaults={
                    "dimension": dimension, "texte": texte,
                    "type_champ": type_objs[type_code], "ordre": ordre,
                    "section": section,
                    "borne_min_label": borne_min, "borne_max_label": borne_max,
                },
            )
            question.options.all().delete()
            for i, (valeur, libelle) in enumerate(options or []):
                OptionReponse.objects.create(
                    question=question, valeur=valeur, libelle=libelle, ordre=i
                )
            return question

        # Formulaire A
        count_a = 0
        ordre = 0
        for groupe, questions in FORMULAIRE_A.items():
            if groupe == "identification":
                dimension, section = dim_objs["Infrastructure TIC"], "identification"
            else:
                dimension, section = dim_objs[groupe], ""
            for code, texte, type_code, opts in questions:
                enregistrer(code, texte, type_code, opts, version_a, dimension, section, ordre)
                ordre += 1
                count_a += 1
        self.stdout.write(self.style.SUCCESS(f"{count_a} questions du Formulaire A chargées."))

        # Formulaire B (deux passes : questions puis conditions)
        b_objs = {}
        for i, (code, texte, type_code, opts, section) in enumerate(FORMULAIRE_B):
            b_objs[code] = enregistrer(
                code, texte, type_code, opts, version_b,
                dim_objs["Compétences numériques"], section, i,
            )
        for code, (code_cond, valeur) in CONDITIONS_B.items():
            if code in b_objs and code_cond in b_objs:
                b_objs[code].question_condition = b_objs[code_cond]
                b_objs[code].valeur_condition = valeur
                b_objs[code].save(update_fields=["question_condition", "valeur_condition"])
        self.stdout.write(self.style.SUCCESS(f"{len(FORMULAIRE_B)} questions du Formulaire B chargées."))
        self.stdout.write(self.style.SUCCESS("Questionnaire de départ chargé."))
