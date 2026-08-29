from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from core.models import (
    Administration,
    Agent,
    Dimension,
    Evaluation,
    Formulaire,
    OptionReponse,
    Question,
    RegleRecommandation,
    Reponse,
    TypeChamp,
    Utilisateur,
    VersionFormulaire,
)
from core.scoring import (
    badge_score,
    calculer_score_dimension,
    classifier_niveau_agent,
    cloturer_evaluation,
    distribution_niveaux_administration,
    generer_recommandations,
    niveau_libelle,
    normaliser_reponse,
    score_dimension_competences,
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
        response = self.client.get("/connexion/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_requires_login(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 302)

    def test_dsi_role_can_access_dashboard(self):
        user = User.objects.create_user(username="dashboard_user", password="testpass123")
        profil, _ = Utilisateur.objects.get_or_create(user=user)
        profil.role = "dsi_decideur"
        profil.save()

        self.client.force_login(user)
        response = self.client.get("/dashboard/")

        self.assertEqual(response.status_code, 200)

    def test_login_redirects_to_role_specific_homepage(self):
        user = User.objects.create_user(username="role_redirect_user", password="testpass123")
        profil, _ = Utilisateur.objects.get_or_create(user=user)
        profil.role = "enqueteur"
        profil.save()

        response = self.client.post(
            "/connexion/",
            {"username": "role_redirect_user", "password": "testpass123"},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/enquetes/")

    def test_enqueteur_cannot_access_formulaire_a(self):
        user = User.objects.create_user(username="restricted_user", password="testpass123")
        profil, _ = Utilisateur.objects.get_or_create(user=user)
        profil.role = "enqueteur"
        profil.save()

        self.client.force_login(user)
        response = self.client.get("/formulaire-a/")

        self.assertEqual(response.status_code, 302)


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

    def test_public_formulaire_b_is_accessible_without_login(self):
        response = self.client.post(
            "/agent-enquete/",
            {
                "administration": self.administration.pk,
                "poste": "Agent public",
                "service": "Digital",
                "tranche_age": "<30",
                "anciennete": "2 ans",
                "niveau_etudes": "Licence",
                "mode_saisie": "autonome",
                f"q_{self.question.id}": "Oui",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Agent.objects.filter(poste="Agent public", administration=self.administration).exists())
        self.assertTrue(Reponse.objects.filter(question=self.question, agent__poste="Agent public").exists())


class SeedDataTests(TestCase):
    def test_seed_data_creates_response_options_for_list_questions(self):
        call_command("seed_data")

        question = Question.objects.get(code="B1.2", version_formulaire__formulaire__code="B")
        options = OptionReponse.objects.filter(question=question)

        self.assertTrue(options.exists())
        self.assertGreaterEqual(options.count(), 3)


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


class MaturityHelpersTests(TestCase):
    def test_niveau_libelle_par_palier(self):
        self.assertEqual(niveau_libelle(1.0), "Initial")
        self.assertEqual(niveau_libelle(2.0), "Émergent")
        self.assertEqual(niveau_libelle(3.2), "Intermédiaire")
        self.assertEqual(niveau_libelle(4.0), "Avancé")
        self.assertEqual(niveau_libelle(4.8), "Optimisé")

    def test_badge_score_seuils(self):
        self.assertEqual(badge_score(2.1), "faible")
        self.assertEqual(badge_score(3.0), "moyen")
        self.assertEqual(badge_score(3.5), "fort")

    def test_score_dimension_competences_pondere_par_effectif(self):
        # 50 % niveau 0 / 50 % niveau 5 -> moyenne 2.5
        self.assertEqual(score_dimension_competences({0: 2, 5: 2}), 2.5)
        self.assertEqual(score_dimension_competences({}), 0.0)


class RecommandationsTests(TestCase):
    def test_seed_recommandations_cree_les_regles(self):
        call_command("seed_recommandations")
        self.assertGreaterEqual(RegleRecommandation.objects.count(), 8)

    def test_generer_recommandations_filtre_sur_le_seuil(self):
        RegleRecommandation.objects.create(
            dimension_code="competences", seuil_max=2.5, priorite="P1",
            texte="Former les agents.", ordre=1,
        )
        RegleRecommandation.objects.create(
            dimension_code="infra", seuil_max=2.0, priorite="P2",
            texte="Renforcer le réseau.", ordre=2,
        )

        recos = generer_recommandations({"competences": 2.1, "infra": 3.8})

        self.assertEqual(len(recos), 1)
        self.assertEqual(recos[0]["dimension_code"], "competences")
        self.assertEqual(recos[0]["priorite"], "P1")


class EvaluationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.administration = Administration.objects.create(nom="Mairie de Lomé")

    def test_reference_est_generee_a_la_creation(self):
        evaluation = Evaluation.objects.create(administration=self.administration)
        self.assertRegex(evaluation.reference, r"^MN-\d{4}-\d{6}$")

    def test_cloturer_evaluation_fige_l_instantane_et_les_recommandations(self):
        Dimension.objects.create(
            nom="Compétences numériques", code="competences", poids="1.00", ordre=1,
        )
        RegleRecommandation.objects.create(
            dimension_code="competences", seuil_max=2.5, priorite="P1",
            texte="Former les agents.", ordre=1,
        )
        Agent.objects.create(administration=self.administration, poste="A", niveau_maturite=0)
        Agent.objects.create(administration=self.administration, poste="B", niveau_maturite=2)

        evaluation = Evaluation.objects.create(administration=self.administration)
        cloturer_evaluation(evaluation)
        evaluation.refresh_from_db()

        self.assertEqual(evaluation.statut, "terminee")
        self.assertIsNotNone(evaluation.date_cloture)
        self.assertEqual(float(evaluation.score_global), 1.0)  # (0 + 2) / 2 agents
        self.assertEqual(evaluation.niveau_libelle, "Initial")
        self.assertEqual(evaluation.distribution_niveaux["0"], 1)
        self.assertEqual(evaluation.recommandations.count(), 1)
