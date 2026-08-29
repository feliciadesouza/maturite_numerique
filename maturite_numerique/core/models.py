import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Dimension(models.Model):
    """Une des 5 dimensions de maturité numérique (Infrastructure TIC, Services en ligne, ...)."""
    nom = models.CharField(max_length=150)
    code = models.SlugField(
        max_length=30, blank=True,
        help_text="Identifiant stable : infra, services, competences, juridique, engagement."
    )
    description = models.TextField(blank=True)
    poids = models.DecimalField(
        max_digits=4, decimal_places=2, default=0.20,
        help_text="Poids de la dimension dans le score global (ex. 0.20 pour 20%)."
    )
    couleur = models.CharField(
        max_length=7, default="#3E90F0",
        help_text="Couleur hex pour le radar et les pastilles (ex. #3E90F0)."
    )
    icone = models.CharField(max_length=40, blank=True, help_text="Nom d'icône Lucide.")
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
    obligatoire = models.BooleanField(default=True)
    actif = models.BooleanField(default=True)
    # Formulaire B : regroupe les questions par section du parcours.
    section = models.CharField(
        max_length=30, blank=True,
        help_text="Section du Formulaire B : administration, profil, bases, usage, freins."
    )
    # Bornes affichées aux extrémités d'une échelle 1 à 5.
    borne_min_label = models.CharField(
        max_length=50, blank=True, help_text="Libellé de la borne basse (ex. « Aucune »)."
    )
    borne_max_label = models.CharField(
        max_length=50, blank=True, help_text="Libellé de la borne haute (ex. « Excellente »)."
    )
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


class Evaluation(models.Model):
    """
    Une campagne de diagnostic : une administration évaluée avec une version
    figée de chaque formulaire, avec un cycle de vie et un instantané de
    résultats calculé à la clôture (pour l'historique et la comparaison).
    """
    STATUT_CHOICES = [
        ("brouillon", "Brouillon"),
        ("en_cours", "En cours"),
        ("terminee", "Terminée"),
        ("archivee", "Archivée"),
    ]

    administration = models.ForeignKey(
        Administration, on_delete=models.CASCADE, related_name="evaluations"
    )
    version_formulaire_a = models.ForeignKey(
        VersionFormulaire, null=True, blank=True, on_delete=models.PROTECT,
        related_name="evaluations_formulaire_a",
    )
    version_formulaire_b = models.ForeignKey(
        VersionFormulaire, null=True, blank=True, on_delete=models.PROTECT,
        related_name="evaluations_formulaire_b",
    )
    statut = models.CharField(max_length=15, choices=STATUT_CHOICES, default="brouillon")
    date_ouverture = models.DateField(auto_now_add=True)
    date_cloture = models.DateField(null=True, blank=True)
    responsable_nom = models.CharField(
        max_length=150, blank=True, help_text="Ex. « Chef de service informatique »."
    )
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="evaluations_creees",
    )
    reference = models.CharField(
        max_length=30, unique=True, null=True, blank=True,
        help_text="Identifiant du rapport, ex. MN-2026-000372.",
    )
    # Instantané figé à la clôture (jamais recalculé après archivage).
    score_global = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    score_par_dimension = models.JSONField(default=dict, blank=True)
    distribution_niveaux = models.JSONField(default=dict, blank=True)
    niveau_libelle = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["-date_ouverture", "-id"]

    def __str__(self):
        return f"{self.administration} — {self.get_statut_display()}"

    def save(self, *args, **kwargs):
        creation = self._state.adding
        super().save(*args, **kwargs)
        if creation and not self.reference:
            annee = (self.date_ouverture or timezone.now().date()).year
            self.reference = f"MN-{annee}-{self.pk:06d}"
            super().save(update_fields=["reference"])


class Utilisateur(models.Model):
    """Profil applicatif lié à un compte Django, avec le rôle métier."""
    # L'agent enquêté n'a pas de compte : il répond au Formulaire B par un
    # lien public. Il n'y a donc que quatre rôles authentifiés.
    ROLE_CHOICES = [
        ("agent_evaluateur", "Agent évaluateur"),
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
    STATUT_CHOICES = [
        ("a_faire", "À faire"),
        ("en_cours", "En cours"),
        ("terminee", "Terminée"),
    ]
    administration = models.ForeignKey(Administration, on_delete=models.CASCADE, related_name="agents")
    evaluation = models.ForeignKey(
        Evaluation, null=True, blank=True, on_delete=models.CASCADE, related_name="agents"
    )
    token = models.UUIDField(
        default=uuid.uuid4, db_index=True, editable=False,
        help_text="Jeton d'accès au brouillon d'enquête (reprise sans compte).",
    )
    numero = models.PositiveIntegerField(
        null=True, blank=True, help_text="Numéro séquentiel de l'agent dans l'évaluation (ex. 037)."
    )
    poste = models.CharField(max_length=150)
    service = models.CharField(max_length=150, blank=True)
    tranche_age = models.CharField(max_length=10, choices=TRANCHE_AGE_CHOICES, blank=True)
    anciennete = models.CharField(max_length=20, blank=True)
    niveau_etudes = models.CharField(max_length=100, blank=True)
    mode_saisie = models.CharField(
        max_length=20, choices=[("autonome", "Autonome"), ("assiste", "Assisté par un enquêteur")],
        default="autonome"
    )
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default="a_faire")
    progression = models.PositiveIntegerField(
        default=0, help_text="Index de la dernière question répondue (reprise d'enquête)."
    )
    enqueteur = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="enquetes_menees",
    )
    reference = models.CharField(
        max_length=30, blank=True, help_text="Accusé de participation (ex. MN-2026-000372)."
    )
    email_accuse = models.EmailField(
        blank=True, help_text="E-mail optionnel pour l'accusé, non relié aux réponses."
    )
    niveau_maturite = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Niveau calculé de 0 (jamais utilisé un ordinateur) à 5"
    )

    def __str__(self):
        return f"{self.poste} - {self.administration}"


class Reponse(models.Model):
    """Une réponse à une question, pour une administration et/ou un agent donné."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="reponses")
    evaluation = models.ForeignKey(
        Evaluation, null=True, blank=True, on_delete=models.CASCADE, related_name="reponses"
    )
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


class RegleRecommandation(models.Model):
    """
    Règle curatée : si le score d'une dimension est ≤ `seuil_max`, la
    recommandation `texte` est proposée avec la priorité indiquée.
    """
    PRIORITE_CHOICES = [
        ("P1", "P1 — critique"),
        ("P2", "P2 — important"),
        ("P3", "P3 — à planifier"),
    ]
    dimension_code = models.SlugField(max_length=30)
    seuil_max = models.DecimalField(
        max_digits=3, decimal_places=1,
        help_text="Règle appliquée si le score de la dimension est ≤ ce seuil (sur 5).",
    )
    priorite = models.CharField(max_length=2, choices=PRIORITE_CHOICES)
    texte = models.CharField(max_length=300)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["priorite", "ordre"]
        verbose_name = "Règle de recommandation"
        verbose_name_plural = "Règles de recommandation"

    def __str__(self):
        return f"[{self.priorite}] {self.dimension_code} ≤ {self.seuil_max}"


class Recommandation(models.Model):
    """Recommandation matérialisée pour une évaluation donnée, à sa clôture."""
    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.CASCADE, related_name="recommandations"
    )
    dimension = models.ForeignKey(
        Dimension, null=True, blank=True, on_delete=models.SET_NULL, related_name="recommandations"
    )
    priorite = models.CharField(max_length=2, choices=RegleRecommandation.PRIORITE_CHOICES)
    texte = models.CharField(max_length=300)
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["priorite", "ordre"]

    def __str__(self):
        return f"[{self.priorite}] {self.texte[:60]}"


class MessageContact(models.Model):
    """Message envoyé depuis le formulaire de contact du site public."""
    SUJET_CHOICES = [
        ("rejoindre", "Rejoindre la démarche"),
        ("demonstration", "Demander une démonstration"),
        ("question", "Poser une question"),
    ]
    nom = models.CharField(max_length=150)
    administration = models.CharField(max_length=200, blank=True)
    email = models.EmailField()
    sujet = models.CharField(max_length=20, choices=SUJET_CHOICES, default="question")
    message = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)
    traite = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date_creation"]
        verbose_name = "Message de contact"
        verbose_name_plural = "Messages de contact"

    def __str__(self):
        return f"{self.nom} — {self.get_sujet_display()}"
