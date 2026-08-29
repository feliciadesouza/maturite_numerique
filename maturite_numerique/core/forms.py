from django import forms

from .models import Administration, Agent, MessageContact, Reponse, Utilisateur


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
