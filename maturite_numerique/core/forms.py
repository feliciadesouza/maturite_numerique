from django import forms

from .models import (
    Administration,
    Agent,
    Dimension,
    MessageContact,
    OptionReponse,
    Question,
    Reponse,
    TypeChamp,
    Utilisateur,
)


# --- Rendu dynamique des questions (Formulaires A et B) ---

CHOIX_PAR_TYPE = {
    "oui_non": [("Oui", "Oui"), ("Non", "Non")],
    "oui_non_partiel": [("Oui", "Oui"), ("Non", "Non"), ("Partiel", "Partiel")],
    "tranches": [
        ("<25%", "Moins de 25 %"), ("25-50%", "25 % à 50 %"),
        ("50-75%", "50 % à 75 %"), (">75%", "Plus de 75 %"),
    ],
    "echelle_1_5": [(str(i), str(i)) for i in range(1, 6)],
}


def choix_question(question):
    """Liste (valeur, libellé) des options d'une question, ou None si champ libre."""
    code = question.type_champ.code
    if code in CHOIX_PAR_TYPE:
        return CHOIX_PAR_TYPE[code]
    if code in ("liste", "choix_multiple"):
        return [(o.valeur, o.libelle) for o in question.options.all().order_by("ordre")]
    return None


def build_reponses_form(questions, *, reponses=None, data=None, partiel=False):
    """
    Formulaire dynamique pour un ensemble de questions.
    `reponses` : dict {question_id: valeur} pour pré-remplir.
    `partiel` : si vrai, aucun champ n'est obligatoire (sauvegarde auto).
    """
    reponses = reponses or {}
    fields = {}
    for question in questions:
        name = f"q_{question.id}"
        code = question.type_champ.code
        valeur = reponses.get(question.id)
        requis = bool(question.obligatoire) and not partiel

        if code == "choix_multiple":
            fields[name] = forms.MultipleChoiceField(
                choices=choix_question(question) or [],
                required=requis, widget=forms.CheckboxSelectMultiple,
                initial=valeur.split(";") if valeur else None,
            )
        elif code == "texte_libre":
            # Les champs libres du questionnaire sont courts (nom, service, fonction).
            fields[name] = forms.CharField(
                required=requis, max_length=255,
                widget=forms.TextInput(attrs={"class": "input"}), initial=valeur,
            )
        else:
            fields[name] = forms.ChoiceField(
                choices=choix_question(question) or [("", "")],
                required=requis, widget=forms.RadioSelect, initial=valeur,
            )

    return type("ReponsesForm", (forms.Form,), fields)(data=data)


def enregistrer_reponses(form, questions, *, evaluation=None, agent=None,
                         administration=None, utilisateur=None):
    """Enregistre (ou met à jour / supprime) les réponses d'un formulaire dynamique."""
    for question in questions:
        brut = form.cleaned_data.get(f"q_{question.id}")
        valeur = ";".join(brut) if isinstance(brut, list) else (brut or "")
        if valeur == "":
            Reponse.objects.filter(
                question=question, evaluation=evaluation, agent=agent
            ).delete()
            continue
        Reponse.objects.update_or_create(
            question=question, evaluation=evaluation, agent=agent,
            defaults={
                "valeur": valeur,
                "administration": administration,
                "utilisateur": utilisateur,
            },
        )


class ContactForm(forms.ModelForm):
    class Meta:
        model = MessageContact
        fields = ["nom", "administration", "email", "sujet", "message"]
        labels = {
            "nom": "Nom complet",
            "administration": "Administration / structure",
            "email": "E-mail professionnel",
            "sujet": "Sujet",
            "message": "Message",
        }
        widgets = {
            "nom": forms.TextInput(attrs={"placeholder": "Ex. : Kossi Amegan"}),
            "administration": forms.TextInput(attrs={"placeholder": "Ex. : Mairie de Lomé"}),
            "email": forms.EmailInput(attrs={"placeholder": "prenom.nom@administration.tg"}),
            "message": forms.Textarea(attrs={"placeholder": "Décrivez votre besoin en quelques lignes…", "rows": 5}),
        }


class AdministrationForm(forms.ModelForm):
    class Meta:
        model = Administration
        fields = ["nom", "secteur", "region", "pays"]
        labels = {
            "nom": "Nom de l’administration",
            "secteur": "Secteur",
            "region": "Région",
            "pays": "Pays",
        }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Utilisateur
        fields = ["role", "administration"]
        labels = {
            "role": "Rôle métier",
            "administration": "Administration associée",
        }


class NouvelAgentForm(forms.ModelForm):
    """Ajout d'un agent à enquêter par l'enquêteur (l'administration est fixée)."""
    class Meta:
        model = Agent
        fields = ["poste", "service", "tranche_age", "anciennete", "niveau_etudes"]
        labels = {
            "poste": "Poste occupé / fonction",
            "service": "Service / direction",
            "tranche_age": "Tranche d'âge",
            "anciennete": "Ancienneté",
            "niveau_etudes": "Niveau d'études",
        }
        widgets = {
            "poste": forms.TextInput(attrs={"placeholder": "Ex. : Agent d'accueil"}),
            "service": forms.TextInput(attrs={"placeholder": "Ex. : État civil"}),
        }


# --- Back-office : administrateur de contenu ---

class DimensionForm(forms.ModelForm):
    class Meta:
        model = Dimension
        fields = ["nom", "code", "description", "poids", "couleur", "icone", "actif"]
        labels = {
            "nom": "Nom de la dimension",
            "code": "Code (identifiant stable)",
            "description": "Description",
            "poids": "Poids dans le score global",
            "couleur": "Couleur (hex)",
            "icone": "Icône (nom Lucide)",
            "actif": "Dimension active",
        }
        help_texts = {
            "poids": "Ex. 0.20 pour 20 %.",
            "couleur": "Ex. #3E90F0.",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
        }


TYPES_AVEC_OPTIONS = ("liste", "choix_multiple")


class QuestionBackofficeForm(forms.ModelForm):
    """Édition d'une question. Les options sont saisies une par ligne : valeur | libellé."""
    options_texte = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "oui | Oui\nnon | Non"}),
        label="Options de réponse",
        help_text="Une par ligne, format « valeur | libellé ». Utilisé pour Liste et Choix multiple.",
    )

    class Meta:
        model = Question
        fields = [
            "code", "texte", "type_champ", "section",
            "borne_min_label", "borne_max_label", "aide", "obligatoire", "actif",
        ]
        labels = {
            "code": "Code (ex. 2.1, B3.4)",
            "texte": "Intitulé de la question",
            "type_champ": "Type de champ",
            "section": "Section (Formulaire B)",
            "borne_min_label": "Borne basse de l'échelle",
            "borne_max_label": "Borne haute de l'échelle",
            "aide": "Aide contextuelle (facultatif)",
            "obligatoire": "Réponse obligatoire",
            "actif": "Question active",
        }
        widgets = {
            "texte": forms.Textarea(attrs={"rows": 2}),
            "borne_min_label": forms.TextInput(attrs={"placeholder": "Aucune"}),
            "borne_max_label": forms.TextInput(attrs={"placeholder": "Excellente"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["type_champ"].queryset = TypeChamp.objects.order_by("libelle")
        if self.instance and self.instance.pk:
            lignes = [
                f"{o.valeur} | {o.libelle}"
                for o in self.instance.options.order_by("ordre")
            ]
            self.fields["options_texte"].initial = "\n".join(lignes)

    def options_parsees(self):
        """Liste [(valeur, libellé)] issue du champ texte."""
        resultat = []
        for ligne in (self.cleaned_data.get("options_texte") or "").splitlines():
            ligne = ligne.strip()
            if not ligne:
                continue
            if "|" in ligne:
                valeur, libelle = (p.strip() for p in ligne.split("|", 1))
            else:
                valeur = libelle = ligne
            resultat.append((valeur, libelle))
        return resultat


def appliquer_options(question, paires):
    """Remplace les options d'une question par la liste (valeur, libellé) fournie."""
    if question.type_champ.code not in TYPES_AVEC_OPTIONS:
        question.options.all().delete()
        return
    question.options.all().delete()
    for ordre, (valeur, libelle) in enumerate(paires):
        OptionReponse.objects.create(
            question=question, valeur=valeur, libelle=libelle, ordre=ordre
        )
