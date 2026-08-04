from django import forms

from .models import Administration, Agent, OptionReponse, Question, Utilisateur, VersionFormulaire


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
    version = VersionFormulaire.objects.filter(formulaire__code=form_code, est_active=True).first()
    questions = Question.objects.filter(version_formulaire=version, actif=True).select_related("type_champ") if version else []

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
