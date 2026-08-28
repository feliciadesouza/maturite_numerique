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
python3 manage.py seed_data          # charge les dimensions et toutes les questions
python3 manage.py createsuperuser    # créez votre compte Administrateur de contenu
python3 manage.py runserver
```

Rendez-vous ensuite sur **http://127.0.0.1:8000/admin/** et connectez-vous
avec le compte créé : vous pouvez déjà consulter, modifier et réordonner
les 5 dimensions et les ~44 questions des Formulaires A et B.

## Tester le moteur de scoring

```bash
python3 manage.py shell
```
```python
from core.models import Administration
from core.scoring import calculer_score_global
admin = Administration.objects.first()
resultat = calculer_score_global(admin)
print(resultat.score_global, resultat.dimension_la_plus_faible)
```

## Ce qui reste à faire (dépend de la maquette du designer)

- Les templates HTML des formulaires A et B (multi-étapes, logique
  conditionnelle du Niveau 0)
- Le tableau de bord avec le radar chart (Chart.js)
- La page de comparaison multi-administrations
- Le export du rapport synthétique (PDF)

## Structure du projet

```
maturite_numerique/
├── core/
│   ├── models.py              # Modèle de données (diagramme de classes)
│   ├── admin.py                # Back-office (Administrateur de contenu)
│   ├── scoring.py              # Moteur de scoring (logique métier pure)
│   └── management/commands/
│       └── seed_data.py        # Chargement des dimensions et questions
├── maturite_numerique/
│   └── settings.py
├── requirements.txt
└── manage.py
```
