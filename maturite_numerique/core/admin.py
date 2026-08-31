from django.contrib import admin
from .models import (
    Dimension, TypeChamp, Formulaire, VersionFormulaire, Question,
    OptionReponse, Administration, Utilisateur, Agent, Reponse,
    Evaluation, RegleRecommandation, Recommandation, MessageContact,
)


class OptionReponseInline(admin.TabularInline):
    model = OptionReponse
    extra = 1


@admin.register(Dimension)
class DimensionAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "poids", "ordre", "couleur", "actif")
    list_editable = ("poids", "ordre", "actif")
    list_filter = ("actif",)
    search_fields = ("nom", "code", "description")
    ordering = ("ordre",)


@admin.register(TypeChamp)
class TypeChampAdmin(admin.ModelAdmin):
    list_display = ("libelle", "code")
    search_fields = ("libelle", "code")


@admin.register(Formulaire)
class FormulaireAdmin(admin.ModelAdmin):
    list_display = ("code", "nom")


@admin.register(VersionFormulaire)
class VersionFormulaireAdmin(admin.ModelAdmin):
    list_display = ("formulaire", "numero_version", "date_creation", "est_active")
    list_filter = ("formulaire", "est_active")
    search_fields = ("formulaire__code", "formulaire__nom", "numero_version")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("code", "texte_court", "dimension", "version_formulaire", "type_champ", "ordre", "actif")
    list_filter = ("dimension", "version_formulaire", "type_champ", "actif")
    list_editable = ("ordre", "actif")
    search_fields = ("code", "texte")
    autocomplete_fields = ("dimension", "version_formulaire", "type_champ", "question_condition")
    inlines = [OptionReponseInline]
    list_per_page = 25

    def texte_court(self, obj):
        return obj.texte[:70]
    texte_court.short_description = "Question"


@admin.register(Administration)
class AdministrationAdmin(admin.ModelAdmin):
    list_display = ("nom", "secteur", "region", "pays")
    list_filter = ("pays", "region", "secteur")
    search_fields = ("nom", "secteur", "region", "pays")
    ordering = ("nom",)
    filter_horizontal = ("enqueteurs",)


@admin.register(Utilisateur)
class UtilisateurAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "role", "administration")
    list_filter = ("role", "administration")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "administration__nom")
    autocomplete_fields = ("user", "administration")
    ordering = ("user__username",)
    list_display_links = ("username",)
    fieldsets = (
        ("Compte", {"fields": ("user", "username", "email")}),
        ("Rôle métier", {"fields": ("role", "administration")}),
    )
    readonly_fields = ("username", "email")

    @admin.display(description="Nom d’utilisateur")
    def username(self, obj):
        return obj.user.username

    @admin.display(description="Email")
    def email(self, obj):
        return obj.user.email or "-"


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("nom", "prenom", "poste", "administration", "mode_saisie", "niveau_maturite")
    list_filter = ("administration", "mode_saisie", "tranche_age")
    search_fields = ("nom", "prenom", "poste", "service", "administration__nom")
    autocomplete_fields = ("administration",)


@admin.register(Reponse)
class ReponseAdmin(admin.ModelAdmin):
    list_display = ("question", "valeur", "administration", "agent", "date_reponse")
    list_filter = ("question__dimension", "administration", "agent")
    search_fields = ("question__code", "question__texte", "valeur", "administration__nom", "agent__poste")
    autocomplete_fields = ("question", "administration", "agent", "utilisateur")
    date_hierarchy = "date_reponse"


class RecommandationInline(admin.TabularInline):
    model = Recommandation
    extra = 0


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ("reference", "administration", "statut", "score_global", "niveau_libelle",
                    "date_ouverture", "date_cloture")
    list_filter = ("statut", "administration")
    search_fields = ("reference", "administration__nom", "responsable_nom")
    readonly_fields = ("reference", "date_ouverture", "score_global", "score_par_dimension",
                       "distribution_niveaux", "niveau_libelle")
    autocomplete_fields = ("administration",)
    date_hierarchy = "date_ouverture"
    inlines = [RecommandationInline]


@admin.register(RegleRecommandation)
class RegleRecommandationAdmin(admin.ModelAdmin):
    list_display = ("dimension_code", "seuil_max", "priorite", "ordre", "texte")
    list_filter = ("priorite", "dimension_code")
    list_editable = ("seuil_max", "priorite", "ordre")
    search_fields = ("dimension_code", "texte")
    ordering = ("priorite", "ordre")


@admin.register(MessageContact)
class MessageContactAdmin(admin.ModelAdmin):
    list_display = ("nom", "prenom", "administration", "sujet", "email", "date_creation", "traite")
    list_filter = ("sujet", "traite")
    list_editable = ("traite",)
    search_fields = ("nom", "prenom", "administration", "email", "message")
    date_hierarchy = "date_creation"
    readonly_fields = ("date_creation",)
