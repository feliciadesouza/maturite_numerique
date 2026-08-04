from django.conf import settings
from django.db import models


class Dimension(models.Model):
    """Une des 5 dimensions de maturité numérique (Infrastructure TIC, Services en ligne, ...)."""
    nom = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    poids = models.DecimalField(
        max_digits=4, decimal_places=2, default=0.20,
        help_text="Poids de la dimension dans le score global (ex. 0.20 pour 20%)."
    )
    ordre = models.PositiveIntegerField(default=0)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordre", "nom"]

    def __str__(self):
        return self.nom


class TypeChamp(models.Model):
    """Type de champ d'une question : radio, échelle 1-5, choix multiple, texte libre..."""
    libelle = models.CharField(max_length=50)
    code = models.SlugField(max_length=50, unique=True)

    def __str__(self):
        return self.libelle


class Formulaire(models.Model):
    """Formulaire A (Administration) ou B (Agent)."""
    CODE_CHOICES = [("A", "Formulaire A - Fiche Administration"), ("B", "Formulaire B - Enquête individuelle agent")]
    code = models.CharField(max_length=1, choices=CODE_CHOICES, unique=True)
    nom = models.CharField(max_length=150)

    def __str__(self):
        return self.nom


class VersionFormulaire(models.Model):
    """
    Version figée d'un formulaire. Quand une question est modifiée après que des
    réponses aient déjà été soumises, on crée une nouvelle version plutôt que
    d'écraser l'ancienne, pour préserver l'historique des réponses.
    """
    formulaire = models.ForeignKey(Formulaire, on_delete=models.CASCADE, related_name="versions")
    numero_version = models.PositiveIntegerField()
    date_creation = models.DateTimeField(auto_now_add=True)
    est_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("formulaire", "numero_version")
        ordering = ["-numero_version"]

    def __str__(self):
        return f"{self.formulaire.code} - v{self.numero_version}"

    def save(self, *args, **kwargs):
        # Une seule version active par formulaire.
        if self.est_active:
            VersionFormulaire.objects.filter(
                formulaire=self.formulaire, est_active=True
            ).exclude(pk=self.pk).update(est_active=False)
        super().save(*args, **kwargs)


class Question(models.Model):
    """Une question, rattachée à une dimension et à une version de formulaire."""
    dimension = models.ForeignKey(Dimension, on_delete=models.CASCADE, related_name="questions")
    version_formulaire = models.ForeignKey(
        VersionFormulaire, on_delete=models.CASCADE, related_name="questions"
    )
    code = models.CharField(max_length=10, help_text="Ex. 1.1, B2.1, B3.4")
    texte = models.TextField()
    type_champ = models.ForeignKey(TypeChamp, on_delete=models.PROTECT)
    ordre = models.PositiveIntegerField(default=0)
    aide = models.CharField(max_length=255, blank=True, help_text="Texte d'aide contextuelle (icône ⓘ)")
    actif = models.BooleanField(default=True)
    # Logique conditionnelle simple : si renseignée, la question ne s'affiche
    # que si la question `question_condition` a la valeur `valeur_condition`.
    question_condition = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="questions_dependantes"
    )
    valeur_condition = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["dimension__ordre", "ordre"]

    def __str__(self):
        return f"{self.code} - {self.texte[:60]}"


class OptionReponse(models.Model):
    """Choix possible pour une question à choix (radio, choix multiple)."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    libelle = models.CharField(max_length=150)
    valeur = models.CharField(max_length=50, help_text="Valeur technique utilisée pour le scoring")
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordre"]

    def __str__(self):
        return self.libelle


class Administration(models.Model):
    """Une administration publique évaluée."""
    nom = models.CharField(max_length=200)
    secteur = models.CharField(max_length=150, blank=True)
    region = models.CharField(max_length=150, blank=True)
    pays = models.CharField(max_length=100, default="Togo")

    class Meta:
        verbose_name_plural = "Administrations"

    def __str__(self):
        return self.nom


class Utilisateur(models.Model):
    """Profil applicatif lié à un compte Django, avec le rôle métier."""
    ROLE_CHOICES = [
        ("agent_evaluateur", "Agent évaluateur"),
        ("agent_enquete", "Agent enquêté"),
        ("enqueteur", "Enquêteur"),
        ("dsi_decideur", "DSI / Décideur"),
        ("admin_contenu", "Administrateur de contenu"),
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profil")
    role = models.CharField(max_length=30, choices=ROLE_CHOICES)
    administration = models.ForeignKey(
        Administration, null=True, blank=True, on_delete=models.SET_NULL, related_name="utilisateurs"
    )

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"


class Agent(models.Model):
    """Agent individuel enquêté via le Formulaire B."""
    TRANCHE_AGE_CHOICES = [
        ("<30", "Moins de 30 ans"), ("30-45", "30-45 ans"),
        ("45-55", "45-55 ans"), (">55", "Plus de 55 ans"),
    ]
    administration = models.ForeignKey(Administration, on_delete=models.CASCADE, related_name="agents")
    poste = models.CharField(max_length=150)
    service = models.CharField(max_length=150, blank=True)
    tranche_age = models.CharField(max_length=10, choices=TRANCHE_AGE_CHOICES, blank=True)
    anciennete = models.CharField(max_length=20, blank=True)
    niveau_etudes = models.CharField(max_length=100, blank=True)
    mode_saisie = models.CharField(
        max_length=20, choices=[("autonome", "Autonome"), ("assiste", "Assisté par un enquêteur")],
        default="autonome"
    )
    niveau_maturite = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Niveau calculé de 0 (jamais utilisé un ordinateur) à 5"
    )

    def __str__(self):
        return f"{self.poste} - {self.administration}"


class Reponse(models.Model):
    """Une réponse à une question, pour une administration et/ou un agent donné."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="reponses")
    administration = models.ForeignKey(
        Administration, null=True, blank=True, on_delete=models.CASCADE, related_name="reponses"
    )
    agent = models.ForeignKey(
        Agent, null=True, blank=True, on_delete=models.CASCADE, related_name="reponses"
    )
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    valeur = models.CharField(max_length=255)
    date_reponse = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_reponse"]

    def __str__(self):
        cible = self.administration or self.agent
        return f"{self.question.code} = {self.valeur} ({cible})"
