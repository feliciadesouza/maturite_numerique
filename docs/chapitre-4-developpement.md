# Chapitre 4 — Mise en place de l'outil (notes de développement)

Support pour la rédaction du mémoire. Reprend l'organisation du dépôt, les
choix techniques et leur justification.

## 1. Pile technique retenue

| Couche | Choix | Justification |
|---|---|---|
| Langage / framework | Python 3.13 · Django 5.2 | ORM aligné sur le modèle de données du Chapitre 3 ; admin intégré comme back-office de secours |
| Base de données | SQLite en développement, PostgreSQL en cible | démarrage sans configuration ; bascule pilotée par variables d'environnement, sans toucher au code |
| Front | Templates Django + CSS maison (design system) | pas de SPA nécessaire pour une Licence ; rendu serveur, défendable |
| Visualisation | Chart.js 4 (radar), auto-hébergé dans `static/vendor/` | élément visuel identitaire ; embarqué pour les connexions faibles |
| Export PDF | WeasyPrint, avec repli sur l'impression navigateur | réutilise les gabarits HTML ; fonctionne en production Linux, dégradé propre sur poste sans Pango/Cairo |
| Police | Inter, auto-hébergée (`static/fonts/`) | pas de dépendance à un CDN tiers |
| Qualité | flake8, bandit, tests Django, pre-commit | intégration continue GitHub Actions bloquante avant fusion |

Rejetés explicitement : Odoo, WordPress (configuration d'outil no-code, peu de
démonstration de compétences de développement).

## 2. Modèle de données (implémentation)

Modèles principaux dans `core/models.py` :

- **Dimension** — 5 dimensions, poids ajustable, couleur et icône.
- **Formulaire → VersionFormulaire → Question → OptionReponse** — le
  versionnage : une question déjà répondue n'est jamais écrasée ; on clone la
  version (`core/versioning.py::dupliquer_version`) et l'ancienne reste liée à
  ses réponses. C'est ce qui rend le suivi dans le temps fiable.
- **Question** — type de champ, section, bornes d'échelle, condition
  d'affichage (`question_condition` / `valeur_condition`).
- **Administration**, **Utilisateur** (rôle métier), **Agent** (répondant au
  Formulaire B : jeton de reprise, statut, progression, numéro, référence).
- **Evaluation** — le pivot : une administration × une version de
  questionnaire, un cycle de vie (brouillon / en cours / terminée / archivée),
  et un **instantané de résultats figé à la clôture** (scores par dimension,
  distribution N0–N5, libellé de niveau).
- **RegleRecommandation** / **Recommandation** — recommandations priorisées
  générées par règles selon les scores.
- **MessageContact** — formulaire de contact du site public.

## 3. Moteur de scoring (`core/scoring.py`, fonctions pures)

- `normaliser_reponse` — conversion d'une réponse en note sur 5.
- `calculer_score_dimension` / `calculer_score_global` — moyenne pondérée.
- **`score_dimension_competences`** — la dimension Compétences dérive de la
  **distribution** des agents sur 6 niveaux (N0–N5), pas d'une moyenne : une
  administration 50 % N0 / 50 % N5 n'a pas le même profil qu'une à 100 % N2–N3.
- `classifier_niveau_agent` — grille de classification 0 → 5 à partir des
  réponses au Formulaire B.
- `niveau_libelle` (Initial → Optimisé) et `badge_score` (faible / moyen / fort).
- `cloturer_evaluation` — fige l'instantané et matérialise les recommandations.
- `resultat_administration` — résultats affichés : instantané si l'évaluation
  est terminée, sinon aperçu calculé à la volée.

## 4. Les deux formulaires

- **Formulaire A** (agent évaluateur, avec compte) — parcours multi-étapes,
  une étape « Identification » puis une par dimension ; sauvegarde à chaque
  étape et sauvegarde automatique (fetch). 24 questions.
- **Formulaire B** (agent enquêté, sans compte, via lien) — parcours
  conditionnel en 6 sections : la section « Bases (suite) » n'apparaît que si
  l'agent a déjà utilisé un ordinateur ; « Usage » que s'il sait allumer un
  poste et se servir d'une souris/clavier. Brouillon repris via un jeton,
  soumission idempotente, accusé par e-mail facultatif. 25 questions.
  Deux modes : autonome (public) ou assisté (l'enquêteur pose les questions
  une à une). Le Formulaire B recueille l'identité du répondant ; la
  restitution se fait de façon agrégée.

## 5. Accès par rôle

Page de connexion unique → redirection automatique vers l'atterrissage du
rôle. Chaque rôle a **son propre menu** (pas de menu commun avec des liens
grisés) ; l'accès par URL à une section d'un autre rôle renvoie une page 403.

| Rôle | Atterrissage | Sections |
|---|---|---|
| Agent évaluateur | Formulaire A | Formulaire A, profil |
| Enquêteur | Liste des agents | enquêtes, Formulaire B assisté |
| DSI / Décideur | Tableau de bord | dashboard, administrations & résultats, comparaison, rapports |
| Administrateur de contenu | Back-office | dimensions, questions, versions — **aucun accès aux résultats** |
| Agent enquêté | *lien public* | Formulaire B uniquement, sans compte |

## 6. Restitution

- **Tableau de bord DSI** — indicateurs, radar du profil moyen, alerte sur la
  dimension la plus à risque.
- **Page Résultats** — radar, recommandations P1/P2/P3, détail par dimension,
  distribution N0–N5.
- **Comparaison** — radar superposé + tableau à cellules colorées ;
  avertissement si les administrations comparées n'ont pas la même version de
  questionnaire.
- **Rapport** — page imprimable, export PDF (WeasyPrint).

## 7. Démarche de construction

Le dépôt a été construit par incréments, une branche et une *pull request* par
lot, la CI (system check, flake8, bandit, tests, migrations, compilation)
verte avant chaque fusion :

0. modèle de données et scoring ·
1. design system et gabarits ·
2. site public ·
3. Formulaire A ·
4. Formulaire B public ·
5. espace enquêteur ·
6. espace DSI (tableau de bord, résultats, comparaison, export PDF) ·
7. back-office de contenu ·
8. finitions (pages d'erreur, e-mails, auto-hébergement des polices,
   accessibilité).

## 8. Configuration et déploiement

- Paramètres sensibles lus depuis l'environnement (`python-decouple`) : aucun
  secret dans le code.
- Dépendances épinglées ; `Dockerfile` prêt (collectstatic au build, migrate
  + gunicorn au démarrage).
- CI/CD GitHub Actions : contrôle qualité, construction d'image, étape de
  déploiement protégée par environnement.
