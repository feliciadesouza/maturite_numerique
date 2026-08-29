from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Dimension, TypeChamp, Formulaire, VersionFormulaire, Question, OptionReponse


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

# Bornes affichées aux extrémités des questions de type "échelle 1 à 5".
BORNES_ECHELLE = {
    "1.1": ("Très instable", "Très stable"),
    "5.5": ("Pas du tout", "Fortement"),
    "B4.5": ("Pas du tout", "Tout à fait"),
}

# Section du parcours du Formulaire B pour chaque préfixe de code question.
SECTION_FORMULAIRE_B = {
    "B1": "profil",
    "B2": "bases",
    "B3": "bases",
    "B4": "usage",
    "B5": "freins",
}

# Formulaire A - questions par dimension (code, texte, type_champ_code)
FORMULAIRE_A = {
    "Infrastructure TIC": [
        ("1.1", "L'administration dispose-t-elle d'une connexion internet stable ?", "echelle_1_5"),
        ("1.2", "Quel est le taux d'équipement en ordinateurs par agent ?", "tranches"),
        ("1.3", "L'administration dispose-t-elle de serveurs propres ou d'un accès à un cloud gouvernemental ?", "oui_non_partiel"),  # noqa: E501
        ("1.4", "Existe-t-il un réseau local interconnectant les services ?", "oui_non_partiel"),
        ("1.5", "Un dispositif de sauvegarde des données est-il en place ?", "oui_non_partiel"),
        ("1.6", "Un service de maintenance informatique est-il disponible (interne ou externalisé) ?", "oui_non"),
    ],
    "Services en ligne": [
        ("2.1", "Quel pourcentage des services de l'administration est disponible en ligne ?", "tranches"),
        ("2.2", "Les usagers peuvent-ils soumettre une demande sans se déplacer physiquement ?", "oui_non_partiel"),
        ("2.3", "Existe-t-il un site web ou portail officiel actif et à jour ?", "oui_non"),
        ("2.4", "Un système de suivi de dossier en ligne est-il proposé ?", "oui_non"),
        ("2.5", "Les paiements en ligne sont-ils possibles pour les services concernés ?", "oui_non"),
        ("2.6", "Une plateforme de dépôt de réclamations en ligne existe-t-elle ?", "oui_non"),
    ],
    "Cadre juridique": [
        ("4.1", "L'administration applique-t-elle une politique de protection des données personnelles ?", "oui_non_partiel"),  # noqa: E501
        ("4.2", "Un texte encadrant la signature électronique existe-t-il dans vos procédures ?", "oui_non"),
        ("4.3", "Une charte ou politique de cybersécurité est-elle formalisée ?", "oui_non"),
        ("4.4", "L'administration est-elle en conformité avec la loi nationale sur les données personnelles ?", "oui_non"),  # noqa: E501
        ("4.5", "Les agents sont-ils sensibilisés aux risques de cybersécurité ?", "oui_non_partiel"),
    ],
    "Engagement institutionnel": [
        ("5.1", "Existe-t-il une stratégie numérique formalisée et validée par la direction ?", "oui_non_partiel"),
        ("5.2", "Un budget dédié à la transformation numérique est-il alloué chaque année ?", "oui_non_partiel"),
        ("5.3", "La direction communique-t-elle régulièrement sur les avancées numériques ?", "oui_non"),
        ("5.4", "Un responsable ou comité de pilotage de la transformation numérique existe-t-il ?", "oui_non"),
        ("5.5", "Le personnel est-il impliqué dans la définition des priorités numériques ?", "echelle_1_5"),
    ],
}

# Formulaire B - questions (code, texte, type_champ_code) - toutes rattachées
# à la dimension "Compétences numériques"
FORMULAIRE_B = [
    ("B1.1", "Poste occupé / fonction", "texte_libre"),
    ("B1.2", "Service / direction", "liste"),
    ("B1.3", "Tranche d'âge", "liste"),
    ("B1.4", "Ancienneté dans l'administration", "liste"),
    ("B1.5", "Niveau d'études", "liste"),
    ("B1.6", "Formulaire rempli en mode :", "liste"),
    ("B2.1", "Avez-vous déjà utilisé un ordinateur, ne serait-ce qu'une fois ?", "oui_non"),
    ("B3.1", "Savez-vous allumer/éteindre un ordinateur seul ?", "oui_non"),
    ("B3.2", "Savez-vous utiliser une souris et un clavier ?", "oui_non"),
    ("B3.3", "Possédez-vous un téléphone portable ?", "liste"),
    ("B3.4", "Si smartphone, utilisez-vous WhatsApp ou les réseaux sociaux ?", "oui_non"),
    ("B3.5", "Avez-vous une adresse email personnelle ou professionnelle ?", "oui_non"),
    ("B3.6", "Si oui, la consultez-vous au moins une fois par semaine ?", "oui_non"),
    ("B4.1", "Utilisez-vous Word ou un traitement de texte dans votre travail ?", "liste"),
    ("B4.2", "Utilisez-vous Excel ou un tableur dans votre travail ?", "liste"),
    ("B4.3", "Avez-vous déjà rempli un formulaire administratif en ligne ?", "oui_non"),
    ("B4.4", "Utilisez-vous un logiciel métier propre à l'administration ?", "oui_non"),
    ("B4.5", "Vous sentez-vous capable d'apprendre seul(e) un nouvel outil numérique ?", "echelle_1_5"),
    ("B4.6", "Seriez-vous capable d'aider un collègue sur un outil numérique ?", "oui_non"),
    ("B5.1", "Avez-vous déjà suivi une formation en informatique ?", "oui_non"),
    ("B5.2", "Quel est le principal frein à votre usage du numérique ?", "liste"),
    ("B5.3", "Seriez-vous intéressé(e) par une formation aux outils numériques ?", "oui_non"),
]

LIST_OPTIONS = {
    "B1.2": [
        ("direction", "Direction"),
        ("service", "Service"),
        ("cellule", "Cellule"),
    ],
    "B1.3": [
        ("<30", "Moins de 30 ans"),
        ("30-45", "30 à 45 ans"),
        ("45-55", "45 à 55 ans"),
        (">55", "Plus de 55 ans"),
    ],
    "B1.4": [
        ("<1an", "Moins d'un an"),
        ("1-3", "1 à 3 ans"),
        ("3-5", "3 à 5 ans"),
        (">5", "Plus de 5 ans"),
    ],
    "B1.5": [
        ("primaire", "Primaire"),
        ("secondaire", "Secondaire"),
        ("bac", "Bac"),
        ("licence", "Licence"),
        ("master", "Master"),
    ],
    "B1.6": [
        ("autonome", "Autonome"),
        ("assisté", "Assisté par un enquêteur"),
    ],
    "B3.3": [
        ("oui", "Oui"),
        ("non", "Non"),
    ],
    "B4.1": [
        ("jamais", "Jamais"),
        ("occasionnellement", "Occasionnellement"),
        ("souvent", "Souvent"),
    ],
    "B4.2": [
        ("jamais", "Jamais"),
        ("occasionnellement", "Occasionnellement"),
        ("souvent", "Souvent"),
    ],
    "B5.2": [
        ("manque_materiel", "Manque de matériel"),
        ("manque_competence", "Manque de compétences"),
        ("manque_temps", "Manque de temps"),
        ("peur", "Peur de la technologie"),
    ],
}


class Command(BaseCommand):
    help = "Charge les données initiales : dimensions, types de champ, formulaires A et B avec leurs questions."

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
        self.stdout.write(self.style.SUCCESS(f"{len(type_objs)} types de champ chargés."))

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

        count = 0
        for dim_nom, questions in FORMULAIRE_A.items():
            for i, (code, texte, type_code) in enumerate(questions):
                borne_min, borne_max = BORNES_ECHELLE.get(code, ("", ""))
                Question.objects.update_or_create(
                    code=code, version_formulaire=version_a,
                    defaults={
                        "dimension": dim_objs[dim_nom], "texte": texte,
                        "type_champ": type_objs[type_code], "ordre": i,
                        "borne_min_label": borne_min, "borne_max_label": borne_max,
                    },
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"{count} questions du Formulaire A chargées."))

        count_b = 0
        for i, (code, texte, type_code) in enumerate(FORMULAIRE_B):
            borne_min, borne_max = BORNES_ECHELLE.get(code, ("", ""))
            section = SECTION_FORMULAIRE_B.get(code.split(".")[0], "")
            question, _ = Question.objects.update_or_create(
                code=code, version_formulaire=version_b,
                defaults={
                    "dimension": dim_objs["Compétences numériques"], "texte": texte,
                    "type_champ": type_objs[type_code], "ordre": i,
                    "section": section,
                    "borne_min_label": borne_min, "borne_max_label": borne_max,
                },
            )
            if type_code == "liste" and code in LIST_OPTIONS:
                for ordre, (valeur, libelle) in enumerate(LIST_OPTIONS[code]):
                    OptionReponse.objects.update_or_create(
                        question=question,
                        valeur=valeur,
                        defaults={"libelle": libelle, "ordre": ordre},
                    )
            count_b += 1
        self.stdout.write(self.style.SUCCESS(f"{count_b} questions du Formulaire B chargées."))

        self.stdout.write(self.style.SUCCESS("Chargement des données initiales terminé."))
