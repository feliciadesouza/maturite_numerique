# Outil de suivi de la maturité numérique des administrations publiques

Base de projet Django correspondant au modèle de données et à la logique
métier conçus au Chapitre 3 du mémoire.

## Ce qui est déjà fonctionnel

- **Modèles complets** (`core/models.py`) : Dimension, Question, TypeChamp,
  OptionReponse, Formulaire, VersionFormulaire (avec gestion du versioning),
  Administration, Agent, Utilisateur, Reponse — conformes au diagramme de classes.
- **Back-office** (`core/admin.py`) : interface d'administration Django déjà
  fonctionnelle pour gérer les dimensions, questions et options de réponse.
  C'est la première brique de l'écran "Administrateur de contenu" — elle
  fonctionne dès maintenant, sans attendre la maquette finale.
- **Moteur de scoring** (`core/scoring.py`) : calcul du score par dimension,
  pondération, score global, dimension la plus faible, et classification
  du niveau de maturité individuelle (0 à 5) pour le Formulaire B.
- **Données initiales** (`core/management/commands/seed_data.py`) : charge
  automatiquement les 5 dimensions et toutes les questions des Formulaires
  A et B déjà rédigées dans le mémoire.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
pip install -r ../requirements-dev.txt   # outils de qualité (dev)
```

## Configuration (variables d'environnement)

La configuration sensible n'est pas dans le code : elle est lue depuis
l'environnement (`python-decouple`). En local, copiez le modèle et adaptez-le :

```bash
cp ../.env.example ../.env       # à la racine du dépôt ; .env n'est jamais versionné
```

Sans `.env`, des valeurs par défaut de développement s'appliquent
(SQLite, `DEBUG=True`, hôtes locaux). Pour PostgreSQL (cible de production,
cf. Chapitre 1), renseignez les variables `DB_*` dans `.env` — aucune
modification de `settings.py` n'est nécessaire.

## Garde-fous avant commit (pre-commit)

```bash
pre-commit install               # une seule fois
pre-commit run --all-files       # vérifier tout le dépôt (flake8, bandit, hygiène)
```

## Démarrage

```bash
python3 manage.py migrate
python3 manage.py seed_data            # questionnaire de départ (dimensions + questions)
python3 manage.py seed_recommandations # règles de recommandation
python3 manage.py setup_roles          # groupes Django par rôle
python3 manage.py create_test_users    # comptes de démonstration (agent_eval, enqueteur, dsi, admin_contenu)
python3 manage.py createsuperuser      # compte superviseur
python3 manage.py runserver
```

Comptes de démonstration : `agent_eval` / `AgentEval123!`, `enqueteur` /
`Enqueteur123!`, `dsi` / `Dsi123!`, `admin_contenu` / `Admin123!`.
La page de connexion (`/connexion/`) redirige chaque rôle vers son espace.
L'enquête agent est accessible sans compte sur `/enquete/`.

## Interfaces

| Rôle | Espace |
|---|---|
| Agent évaluateur | Formulaire A multi-étapes |
| Enquêteur | Liste des agents + Formulaire B assisté |
| DSI / Décideur | Tableau de bord, résultats, comparaison, rapports (PDF) |
| Administrateur de contenu | Back-office : dimensions, questions, versions |
| Agent enquêté | Formulaire B public, sans compte |

## Tests et qualité

```bash
python manage.py test
flake8 .
bandit --recursive core maturite_numerique --exclude '**/tests.py,**/migrations/**'
```

## Structure du projet

```
maturite_numerique/
├── core/
│   ├── models.py        # modèle de données
│   ├── views.py         # vues (site public, formulaires, DSI, back-office)
│   ├── forms.py         # formulaires + rendu dynamique des questions
│   ├── scoring.py       # moteur de scoring (fonctions pures)
│   ├── versioning.py    # versionnage du questionnaire
│   ├── permissions.py   # contrôle d'accès par rôle
│   ├── templates/       # 3 gabarits (public / app / enquête) + composants
│   ├── static/          # design system (tokens.css), Chart.js, police Inter
│   └── management/commands/
└── maturite_numerique/settings.py
```

Notes de développement pour le mémoire : `../docs/chapitre-4-developpement.md`.
