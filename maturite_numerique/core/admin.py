from django.contrib import admin
from .models import (
    Dimension, TypeChamp, Formulaire, VersionFormulaire, Question,
    OptionReponse, Administration, Utilisateur, Agent, Reponse,
)


class OptionReponseInline(admin.TabularInline):
    model = OptionReponse
    extra = 1


@admin.register(Dimension)
class DimensionAdmin(admin.ModelAdmin):
    list_display = ("nom", "poids", "ordre", "actif")
    list_editable = ("poids", "ordre", "actif")
    list_filter = ("actif",)
    search_fields = ("nom", "description")
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


@admin.register(Utilisateur)
class UtilisateurAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "administration")
    list_filter = ("role", "administration")
    search_fields = ("user__username", "user__first_name", "user__last_name", "administration__nom")
    autocomplete_fields = ("user", "administration")


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("poste", "administration", "tranche_age", "mode_saisie", "niveau_maturite")
    list_filter = ("administration", "mode_saisie", "tranche_age")
    search_fields = ("poste", "service", "administration__nom")
    autocomplete_fields = ("administration",)


@admin.register(Reponse)
class ReponseAdmin(admin.ModelAdmin):
    list_display = ("question", "valeur", "administration", "agent", "date_reponse")
    list_filter = ("question__dimension", "administration", "agent")
    search_fields = ("question__code", "question__texte", "valeur", "administration__nom", "agent__poste")
    autocomplete_fields = ("question", "administration", "agent", "utilisateur")
    date_hierarchy = "date_reponse"
