from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import (
    Administration,
    Agent,
    Dimension,
    Formulaire,
    Question,
    Reponse,
    TypeChamp,
    Utilisateur,
    VersionFormulaire,
)
from core.scoring import (
    calculer_score_dimension,
    classifier_niveau_agent,
    distribution_niveaux_administration,
    normaliser_reponse,
)

User = get_user_model()


class AuthenticationProfileTests(TestCase):
    def test_user_can_be_linked_to_a_role_profile(self):
        user = User.objects.create_user(username="tester", password="testpass123")
        profil, created = Utilisateur.objects.get_or_create(user=user)
        profil.role = "admin_contenu"
        profil.save()

        self.assertTrue(created)
        self.assertEqual(profil.role, "admin_contenu")

    def test_login_page_is_available(self):
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_requires_login(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 302)

    def test_user_with_role_can_access_dashboard(self):
        user = User.objects.create_user(username="dashboard_user", password="testpass123")
        profil, _ = Utilisateur.objects.get_or_create(user=user)
        profil.role = "admin_contenu"
        profil.save()

        self.client.force_login(user)
        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)


class FormSubmissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dimension = Dimension.objects.create(
            nom="Compétences numériques",
            description="Test",
            poids=0.20,
            ordre=1,
        )
        cls.type_champ = TypeChamp.objects.create(libelle="Oui/Non", code="oui_non")
        cls.formulaire = Formulaire.objects.create(code="B", nom="Formulaire B")
        cls.version = VersionFormulaire.objects.create(formulaire=cls.formulaire, numero_version=1, est_active=True)
        cls.question = Question.objects.create(
            dimension=cls.dimension,
            version_formulaire=cls.version,
            code="B2.1",
            texte="Avez-vous déjà utilisé un ordinateur ?",
            type_champ=cls.type_champ,
            ordre=1,
        )
        cls.administration = Administration.objects.create(
            nom="Administration Test",
            secteur="IT",
            region="Lomé",
            pays="Togo",
        )

    def test_formulaire_a_submission_creates_an_administration(self):
        user = User.objects.create_user(username="form_a_user", password="testpass123")
        Utilisateur.objects.create(user=user, role="agent_evaluateur")
        self.client.force_login(user)

        response = self.client.post(
            "/formulaire-a/",
            {
                "nom": "Administration créée par test",
                "secteur": "Public",
                "region": "Lomé",
                "pays": "Togo",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Administration.objects.filter(nom="Administration créée par test").exists())

    def test_formulaire_b_submission_creates_agent_and_answers(self):
        user = User.objects.create_user(username="form_b_user", password="testpass123")
        Utilisateur.objects.create(user=user, role="enqueteur")
        self.client.force_login(user)

        response = self.client.post(
            "/formulaire-b/",
            {
                "administration": self.administration.pk,
                "poste": "Agent test",
                "service": "Digital",
                "tranche_age": "<30",
                "anciennete": "2 ans",
                "niveau_etudes": "Licence",
                "mode_saisie": "autonome",
                f"q_{self.question.id}": "Oui",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Agent.objects.filter(poste="Agent test", administration=self.administration).exists())
        self.assertTrue(Reponse.objects.filter(question=self.question, agent__poste="Agent test").exists())


class ScoringEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dimension = Dimension.objects.create(
            nom="Compétences numériques",
            description="Test",
            poids=0.20,
            ordre=1,
        )
        cls.type_champ = TypeChamp.objects.create(libelle="Oui/Non", code="oui_non")
        cls.formulaire = Formulaire.objects.create(code="B", nom="Formulaire B")
        cls.version = VersionFormulaire.objects.create(formulaire=cls.formulaire, numero_version=1, est_active=True)
        cls.question = Question.objects.create(
            dimension=cls.dimension,
            version_formulaire=cls.version,
            code="B2.1",
            texte="Avez-vous déjà utilisé un ordinateur ?",
            type_champ=cls.type_champ,
            ordre=1,
        )
        cls.administration = Administration.objects.create(
            nom="Administration Test",
            secteur="IT",
            region="Lomé",
            pays="Togo",
        )

    def test_normaliser_reponse_supporte_oui_non_et_tranche(self):
        self.assertEqual(normaliser_reponse("Oui"), 5)
        self.assertEqual(normaliser_reponse("Non"), 0)
        self.assertEqual(normaliser_reponse("<25%"), 1)
        self.assertEqual(normaliser_reponse("3.5"), 3.5)

    def test_classifier_niveau_agent_retourne_niveau_attendu(self):
        reponses_agent = {
            "B2.1": "Oui",
            "B3.4": "Oui",
            "B3.5": "Oui",
            "B4.1": "Souvent",
            "B4.2": "Souvent",
            "B4.4": "Oui",
            "B4.6": "Oui",
        }
        self.assertEqual(classifier_niveau_agent(reponses_agent), 5)

    def test_calculer_score_dimension_pondere_une_dimension(self):
        Reponse.objects.create(
            administration=self.administration,
            question=self.question,
            valeur="Oui",
        )
        Reponse.objects.create(
            administration=self.administration,
            question=self.question,
            valeur="Non",
        )

        score = calculer_score_dimension(self.administration, self.dimension)

        self.assertEqual(score.score_brut, 2.5)
        self.assertEqual(score.score_pondere, 0.5)

    def test_distribution_niveaux_administration_compte_les_agents(self):
        Agent.objects.create(
            administration=self.administration,
            poste="Agent 1",
            service="Digital",
            niveau_maturite=0,
        )
        Agent.objects.create(
            administration=self.administration,
            poste="Agent 2",
            service="Digital",
            niveau_maturite=1,
        )

        distribution = distribution_niveaux_administration(self.administration)

        self.assertEqual(distribution[0], 1)
        self.assertEqual(distribution[1], 1)
        self.assertEqual(distribution[2], 0)
