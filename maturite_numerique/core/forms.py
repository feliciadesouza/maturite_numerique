from django import forms

from .models import (
    Administration,
    Agent,
    MessageContact,
    OptionReponse,
    Question,
    Reponse,
    Utilisateur,
    VersionFormulaire,
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
            fields[name] = forms.CharField(
                required=requis, widget=forms.Textarea(attrs={"rows": 3}), initial=valeur,
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


class AgentForm(forms.ModelForm):
    class Meta:
        model = Agent
        fields = [
            "administration",
            "poste",
            "service",
            "tranche_age",
            "anciennete",
            "niveau_etudes",
            "mode_saisie",
        ]
        labels = {
            "administration": "Administration",
            "poste": "Poste occupé",
            "service": "Service",
            "tranche_age": "Tranche d’âge",
            "anciennete": "Ancienneté",
            "niveau_etudes": "Niveau d’études",
            "mode_saisie": "Mode de saisie",
        }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Utilisateur
        fields = ["role", "administration"]
        labels = {
            "role": "Rôle métier",
            "administration": "Administration associée",
        }


def build_question_form(form_code: str, data=None, files=None):
    version = VersionFormulaire.objects.filter(
        formulaire__code=form_code, est_active=True
    ).first()
    if version:
        questions = Question.objects.filter(
            version_formulaire=version, actif=True
        ).select_related("type_champ")
    else:
        questions = []

    class DynamicQuestionForm(forms.Form):
        pass

    for question in questions:
        field_name = f"q_{question.id}"
        field_label = f"{question.code} — {question.texte}"
        type_code = question.type_champ.code

        if type_code == "oui_non":
            choices = [("Oui", "Oui"), ("Non", "Non")]
            field = forms.ChoiceField(label=field_label, choices=choices, required=False)
        elif type_code == "oui_non_partiel":
            choices = [("Oui", "Oui"), ("Non", "Non"), ("Partiel", "Partiel")]
            field = forms.ChoiceField(label=field_label, choices=choices, required=False)
        elif type_code == "tranches":
            choices = [
                ("<25%", "Moins de 25 %"),
                ("25-50%", "25 % à 50 %"),
                ("50-75%", "50 % à 75 %"),
                (">75%", "Plus de 75 %"),
            ]
            field = forms.ChoiceField(label=field_label, choices=choices, required=False)
        elif type_code == "echelle_1_5":
            choices = [(str(i), str(i)) for i in range(1, 6)]
            field = forms.ChoiceField(label=field_label, choices=choices, required=False)
        elif type_code == "liste":
            options = OptionReponse.objects.filter(question=question).order_by("ordre")
            choices = [(option.valeur, option.libelle) for option in options]
            if not choices:
                choices = [("", "Sélectionnez une option")]
            field = forms.ChoiceField(label=field_label, choices=choices, required=False)
        else:
            field = forms.CharField(label=field_label, required=False, widget=forms.Textarea)

        DynamicQuestionForm.base_fields[field_name] = field

    return DynamicQuestionForm(data=data, files=files)
