from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase

from core.models import (
    Administration,
    Agent,
    Dimension,
    Evaluation,
    Formulaire,
    MessageContact,
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

    def test_formulaire_a_ouvre_une_evaluation_et_enregistre_les_reponses(self):
        from core.models import Evaluation, Formulaire, VersionFormulaire

        dim = Dimension.objects.create(nom="Infrastructure TIC", code="infra", ordre=1)
        tc, _ = TypeChamp.objects.get_or_create(code="oui_non", defaults={"libelle": "Oui/Non"})
        form_a = Formulaire.objects.create(code="A", nom="Formulaire A")
        version = VersionFormulaire.objects.create(formulaire=form_a, numero_version=1, est_active=True)
        question = Question.objects.create(
            dimension=dim, version_formulaire=version, code="1.1",
            texte="Connexion internet stable ?", type_champ=tc, ordre=1,
        )

        user = User.objects.create_user(username="form_a_user", password="testpass123")
        Utilisateur.objects.create(
            user=user, role="agent_evaluateur", administration=self.administration
        )
        self.client.force_login(user)

        entree = self.client.get("/formulaire-a/")
        self.assertEqual(entree.status_code, 302)
        self.assertEqual(entree.url, "/formulaire-a/etape/1/")
        self.assertEqual(self.client.get("/formulaire-a/etape/1/").status_code, 200)

        suite = self.client.post("/formulaire-a/etape/1/", {f"q_{question.id}": "Oui"})
        self.assertEqual(suite.status_code, 302)

        evaluation = Evaluation.objects.get(administration=self.administration)
        self.assertEqual(evaluation.statut, "en_cours")
        self.assertTrue(Reponse.objects.filter(evaluation=evaluation, question=question, valeur="Oui").exists())

    def test_formulaire_a_exige_une_administration_sur_le_profil(self):
        user = User.objects.create_user(username="sans_admin", password="testpass123")
        Utilisateur.objects.create(user=user, role="agent_evaluateur")
        self.client.force_login(user)
        response = self.client.get("/formulaire-a/")
        self.assertRedirects(response, "/profile/", fetch_redirect_response=False)

    def test_formulaire_b_redirige_vers_la_liste_des_enquetes(self):
        user = User.objects.create_user(username="form_b_user", password="testpass123")
        Utilisateur.objects.create(
            user=user, role="enqueteur", administration=self.administration
        )
        self.client.force_login(user)
        response = self.client.get("/formulaire-b/")
        self.assertRedirects(response, "/enquetes/", fetch_redirect_response=False)

    def test_enquete_publique_accessible_sans_compte(self):
        self.assertEqual(self.client.get("/enquete/").status_code, 200)
        self.assertEqual(self.client.get("/agent-enquete/").status_code, 200)
        self.assertEqual(self.client.get("/enquete/demarrer/").status_code, 200)


class EnquetePubliqueTests(TestCase):
    def setUp(self):
        call_command("seed_data")
        self.administration = Administration.objects.create(nom="Mairie de Lomé", region="Maritime")
        self.version_b = VersionFormulaire.objects.get(
            formulaire__code="B", est_active=True
        )

    def _codes(self, section):
        return list(
            Question.objects.filter(
                version_formulaire=self.version_b, section=section, actif=True
            ).order_by("ordre")
        )

    def _payload(self, questions, override=None):
        override = override or {}
        data = {}
        for q in questions:
            if q.code in override:
                data[f"q_{q.id}"] = override[q.code]
                continue
            code = q.type_champ.code
            if code == "oui_non":
                data[f"q_{q.id}"] = "Oui"
            elif code == "oui_non_partiel":
                data[f"q_{q.id}"] = "Partiel"
            elif code == "echelle_1_5":
                data[f"q_{q.id}"] = "4"
            elif code == "tranches":
                data[f"q_{q.id}"] = "50-75%"
            elif code in ("liste", "choix_multiple"):
                opt = q.options.first()
                data[f"q_{q.id}"] = opt.valeur if opt else ""
            else:
                data[f"q_{q.id}"] = "Réponse test"
        return data

    def test_parcours_complet_cree_un_agent_et_un_accuse(self):
        demarrer = self.client.post("/enquete/demarrer/", {"administration": self.administration.pk})
        self.assertEqual(demarrer.status_code, 302)
        agent = Agent.objects.get(administration=self.administration)
        base = f"/enquete/{agent.token}/section/"

        for section in ["profil", "bases", "usage", "freins"]:
            questions = self._codes(section)
            override = {"B2.1": "Oui"} if section == "bases" else None
            resp = self.client.post(base + section + "/", self._payload(questions, override))
            self.assertEqual(resp.status_code, 302)

        agent.refresh_from_db()
        self.assertEqual(agent.statut, "terminee")
        self.assertRegex(agent.reference, r"^MN-\d{4}-\d{6}$")
        self.assertIsNotNone(agent.niveau_maturite)
        conf = self.client.get(f"/enquete/{agent.token}/confirmation/")
        self.assertEqual(conf.status_code, 200)

    def test_filtre_niveau_0_saute_la_section_usage(self):
        self.client.post("/enquete/demarrer/", {"administration": self.administration.pk})
        agent = Agent.objects.get(administration=self.administration)
        base = f"/enquete/{agent.token}/section/"

        self.client.post(base + "profil/", self._payload(self._codes("profil")))
        rep = self.client.post(base + "bases/", self._payload(self._codes("bases"), {"B2.1": "Non"}))
        self.assertEqual(rep.status_code, 302)
        self.assertEqual(rep.url, base + "freins/")

        # « usage » redirige vers la 1re section effective
        self.assertEqual(self.client.get(base + "usage/").status_code, 302)

        self.client.post(base + "freins/", self._payload(self._codes("freins")))
        agent.refresh_from_db()
        self.assertEqual(agent.statut, "terminee")
        self.assertEqual(agent.niveau_maturite, 0)

    def test_soumission_idempotente(self):
        self.client.post("/enquete/demarrer/", {"administration": self.administration.pk})
        agent = Agent.objects.get(administration=self.administration)
        base = f"/enquete/{agent.token}/section/"
        for section in ["profil", "bases", "usage", "freins"]:
            self.client.post(base + section + "/", self._payload(self._codes(section), {"B2.1": "Oui"}))
        ref = Agent.objects.get(pk=agent.pk).reference
        # revisiter une section après clôture redirige vers la confirmation
        again = self.client.get(base + "profil/")
        self.assertEqual(again.status_code, 302)
        self.assertEqual(Agent.objects.get(pk=agent.pk).reference, ref)


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


class PublicSiteTests(TestCase):
    def setUp(self):
        call_command("seed_data")

    def test_pages_publiques_repondent(self):
        for path in ["/", "/demarche/", "/dimensions/", "/acces-par-role/",
                     "/contact/", "/confidentialite/", "/conditions-utilisation/"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_contact_enregistre_et_envoie_un_message(self):
        response = self.client.post("/contact/", {
            "nom": "Kossi Amegan",
            "administration": "Mairie de Lomé",
            "email": "kossi@mairie.tg",
            "sujet": "rejoindre",
            "message": "Nous souhaitons rejoindre la démarche.",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(MessageContact.objects.filter(email="kossi@mairie.tg").exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_accueil_redirige_un_compte_connecte(self):
        user = User.objects.create_user(username="dsi_home", password="testpass123")
        Utilisateur.objects.create(user=user, role="dsi_decideur")
        self.client.force_login(user)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")


class DsiEspaceTests(TestCase):
    def setUp(self):
        call_command("seed_data")
        self.administration = Administration.objects.create(nom="Mairie de Lomé", region="Maritime")
        user = User.objects.create_user(username="dsi_u", password="testpass123")
        Utilisateur.objects.create(user=user, role="dsi_decideur")
        self.client.force_login(user)

    def test_pages_dsi_repondent(self):
        for path in ["/dashboard/", "/administrations/", "/comparaison/", "/rapports/"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_resultats_et_rapport_d_une_administration(self):
        from core.models import Evaluation, RegleRecommandation
        from core.scoring import cloturer_evaluation

        Agent.objects.create(administration=self.administration, poste="A", niveau_maturite=1)
        Agent.objects.create(administration=self.administration, poste="B", niveau_maturite=2)
        RegleRecommandation.objects.create(
            dimension_code="competences", seuil_max=3.0, priorite="P1",
            texte="Former les agents.", ordre=1,
        )
        evaluation = Evaluation.objects.create(administration=self.administration, statut="en_cours")
        cloturer_evaluation(evaluation)

        res = self.client.get(f"/administrations/{self.administration.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Recommandations priorisées")

        rap = self.client.get(f"/administrations/{self.administration.pk}/rapport/")
        self.assertEqual(rap.status_code, 200)
        self.assertContains(rap, "Rapport de maturité numérique")

    def test_admin_contenu_n_a_pas_acces_au_tableau_de_bord(self):
        user = User.objects.create_user(username="ac_u", password="testpass123")
        Utilisateur.objects.create(user=user, role="admin_contenu")
        self.client.force_login(user)
        self.assertEqual(self.client.get("/dashboard/").status_code, 302)

    def test_comparaison_avec_plusieurs_administrations(self):
        kloto = Administration.objects.create(nom="Préfecture de Kloto")
        Administration.objects.create(nom="Commune d'Aného")
        response = self.client.get(
            f"/comparaison/?admin={self.administration.pk}&admin={kloto.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Score global")
        self.assertContains(response, "Profils superposés")

    def test_export_pdf_bascule_sur_l_apercu_si_weasyprint_absent(self):
        # WeasyPrint n'est pas chargeable sur cet environnement : on doit être
        # redirigé vers l'aperçu HTML sans erreur.
        response = self.client.get(
            f"/administrations/{self.administration.pk}/rapport/?format=pdf"
        )
        self.assertIn(response.status_code, (200, 302))


class EnqueteurTests(TestCase):
    def setUp(self):
        call_command("seed_data")
        self.administration = Administration.objects.create(nom="Mairie de Lomé", region="Maritime")
        self.user = User.objects.create_user(username="enq", password="testpass123")
        Utilisateur.objects.create(
            user=self.user, role="enqueteur", administration=self.administration
        )
        self.client.force_login(self.user)

    def test_liste_des_enquetes_repond(self):
        self.assertEqual(self.client.get("/enquetes/").status_code, 200)

    def test_nouvel_agent_cree_et_numerote(self):
        response = self.client.post("/enquetes/nouvel-agent/", {
            "poste": "Agent d'accueil", "service": "État civil",
        })
        self.assertEqual(response.status_code, 302)
        agent = Agent.objects.get(poste="Agent d'accueil")
        self.assertEqual(agent.numero, 1)
        self.assertEqual(agent.mode_saisie, "assiste")
        self.assertEqual(agent.enqueteur, self.user)

    def test_parcours_assiste_question_par_question(self):
        agent = Agent.objects.create(
            administration=self.administration, mode_saisie="assiste",
            enqueteur=self.user, numero=1,
        )
        from core.views import _questions_agent_ordonnees

        total = len(_questions_agent_ordonnees(agent))
        self.assertGreater(total, 0)

        for index in range(total):
            questions = _questions_agent_ordonnees(agent)
            if index >= len(questions):
                break
            q = questions[index]
            code = q.type_champ.code
            if code == "oui_non":
                valeur = "Oui"
            elif code == "oui_non_partiel":
                valeur = "Partiel"
            elif code == "echelle_1_5":
                valeur = "4"
            elif code in ("liste", "choix_multiple"):
                opt = q.options.first()
                valeur = opt.valeur if opt else ""
            else:
                valeur = "Réponse"
            resp = self.client.post(
                f"/enquetes/agent/{agent.pk}/question/{index}/", {f"q_{q.id}": valeur}
            )
            self.assertEqual(resp.status_code, 302)

        agent.refresh_from_db()
        self.assertEqual(agent.statut, "terminee")
        self.assertIsNotNone(agent.niveau_maturite)
        self.assertRegex(agent.reference, r"^MN-\d{4}-\d{6}$")

    def test_agent_d_une_autre_administration_est_inaccessible(self):
        autre = Administration.objects.create(nom="Préfecture de Kloto")
        agent = Agent.objects.create(administration=autre, mode_saisie="assiste")
        self.assertEqual(
            self.client.get(f"/enquetes/agent/{agent.pk}/question/0/").status_code, 404
        )


class BackofficeTests(TestCase):
    def setUp(self):
        call_command("seed_data")
        user = User.objects.create_user(username="ac", password="testpass123")
        Utilisateur.objects.create(user=user, role="admin_contenu")
        self.client.force_login(user)
        self.version_a = VersionFormulaire.objects.get(
            formulaire__code="A", est_active=True
        )
        self.dimension = Dimension.objects.get(code="infra")

    def test_pages_backoffice_repondent(self):
        for path in ["/back-office/", "/back-office/questions/", "/back-office/versions/",
                     f"/back-office/dimensions/{self.dimension.pk}/questions/"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_ajout_dimension(self):
        response = self.client.post("/back-office/dimensions/nouvelle/", {
            "nom": "Gouvernance des données", "code": "gouvernance",
            "description": "", "poids": "0.10", "couleur": "#123456",
            "icone": "shield", "actif": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Dimension.objects.filter(code="gouvernance").exists())

    def test_edition_question_sans_reponse_reste_dans_la_meme_version(self):
        question = Question.objects.filter(
            version_formulaire=self.version_a, dimension=self.dimension
        ).first()
        nb_versions = VersionFormulaire.objects.filter(formulaire__code="A").count()
        response = self.client.post(
            f"/back-office/questions/{question.pk}/editer/",
            {
                "code": question.code, "texte": "Nouvel intitulé", "section": "",
                "type_champ": question.type_champ_id, "borne_min_label": "",
                "borne_max_label": "", "aide": "", "obligatoire": "on", "actif": "on",
                "options_texte": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        question.refresh_from_db()
        self.assertEqual(question.texte, "Nouvel intitulé")
        self.assertEqual(
            VersionFormulaire.objects.filter(formulaire__code="A").count(), nb_versions
        )

    def test_edition_question_avec_reponses_cree_une_nouvelle_version(self):
        question = Question.objects.filter(
            version_formulaire=self.version_a, dimension=self.dimension
        ).first()
        administration = Administration.objects.create(nom="Mairie de Lomé")
        Reponse.objects.create(question=question, administration=administration, valeur="3")
        nb_versions = VersionFormulaire.objects.filter(formulaire__code="A").count()

        response = self.client.post(
            f"/back-office/questions/{question.pk}/editer/",
            {
                "code": question.code, "texte": "Intitulé révisé", "section": "",
                "type_champ": question.type_champ_id, "borne_min_label": "",
                "borne_max_label": "", "aide": "", "obligatoire": "on", "actif": "on",
                "options_texte": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            VersionFormulaire.objects.filter(formulaire__code="A").count(), nb_versions + 1
        )
        question.refresh_from_db()
        self.assertNotEqual(question.texte, "Intitulé révisé")  # l'ancienne version est intacte
        nouvelle = VersionFormulaire.objects.filter(
            formulaire__code="A", est_active=True
        ).first()
        self.assertEqual(nouvelle.questions.get(code=question.code).texte, "Intitulé révisé")

    def test_dsi_n_a_pas_acces_au_backoffice(self):
        user = User.objects.create_user(username="dsi_bo", password="testpass123")
        Utilisateur.objects.create(user=user, role="dsi_decideur")
        self.client.force_login(user)
        self.assertEqual(self.client.get("/back-office/").status_code, 302)


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
