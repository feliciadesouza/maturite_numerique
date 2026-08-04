# Contexte du projet — Outil de suivi de la maturité numérique

## À propos

Mémoire de fin de cycle (Licence, Lomé Business School, 2025-2026).

**Thème :** Conception et développement d'un outil de suivi de la maturité
numérique des administrations publiques en Afrique subsaharienne.

**Argument central du mémoire :** les administrations publiques en Afrique
subsaharienne lancent des projets de digitalisation sans diagnostic
préalable de leur maturité numérique, ce qui conduit à des investissements
mal calibrés. L'outil permet de diagnostiquer AVANT d'investir.

**Chapitres du mémoire :**
- Chapitre 1 — Généralités sur la programmation et les bases de données
- Chapitre 2 — Étude de l'existant
- Chapitre 3 — Analyse / conception (UML, modèle de données)
- Chapitre 4 — Mise en place de l'outil (développement)

Le jury évalue la capacité à modéliser une base de données, écrire une
logique métier, et justifier les choix techniques. **Éviter tout ce qui
ressemble à de la configuration d'outil no-code (Odoo, WordPress, etc.)
— le développement doit être visiblement le travail de l'étudiant.**

## Stack technique retenue (et pourquoi)

- **Backend :** Python / Django — choisi pour son ORM qui correspond
  directement au modèle de données déjà conçu, et pour l'admin Django
  qui sert de base au back-office.
- **Base de données :** PostgreSQL en cible (MySQL acceptable), SQLite
  utilisé pour le développement local rapide.
- **Frontend :** Templates Django + Bootstrap (pas de SPA nécessaire pour
  une Licence — garder simple et défendable).
- **Visualisation :** Chart.js pour le radar chart (élément visuel
  identitaire de l'outil).
- **Rejeté explicitement :** Odoo et WordPress — évalués et écartés car
  ils réduiraient la démonstration de compétences techniques attendue
  par le jury (trop de "configuration", pas assez de "développement").

## Les 5 dimensions de maturité numérique

Grille de référence (voir `core/management/commands/seed_data.py` pour le
détail complet des questions) :

1. **Infrastructure TIC** — équipements, réseaux, connectivité
2. **Services en ligne** — dématérialisation des services aux usagers
3. **Compétences numériques** — via le Formulaire B (voir plus bas)
4. **Cadre juridique** — protection des données, cybersécurité, signature électronique
5. **Engagement institutionnel** — stratégie, budget, gouvernance

Fondements théoriques (à citer dans le mémoire) :
- **GovTech Maturity Index (GTMI)** — Banque mondiale, le plus pertinent
  car conçu pour les économies en développement.
- **UN EGDI** (E-Government Development Index) — 3 piliers : services en
  ligne, infrastructure télécoms, capital humain. C'est un **indice
  composite**, pas un modèle de maturité — ne pas confondre dans le texte.
- **OCDE Digital Government Index (DGI)** — 6 dimensions.
- **DESI** — européen, à citer uniquement en le présentant explicitement
  comme adapté/transposé au contexte africain.
- **Précédent local :** étude de maturité numérique au Burkina Faso
  (référence de terrain pour le Chapitre 2).

Chaque dimension a un poids dans le score global (0.20 par défaut pour
5 dimensions à poids égal, ajustable).

## Deux formulaires distincts (raison métier importante)

**Formulaire A — Fiche Administration**
Rempli par 1 responsable (DSI, secrétaire général). Couvre les dimensions
Infrastructure TIC, Services en ligne, Cadre juridique, Engagement
institutionnel. 22 questions.

**Formulaire B — Enquête individuelle agent**
Pourquoi séparé : en Afrique subsaharienne, une partie significative des
agents publics n'a jamais utilisé d'ordinateur. Un formulaire en ligne
classique ne peut pas leur être administré directement.

- Rempli en **mode autonome** OU en **mode assisté** (un enquêteur pose
  les questions oralement et saisit à la place de l'agent).
- **Question filtre B2.1** : "Avez-vous déjà utilisé un ordinateur ?"
  Si NON → l'agent est classé automatiquement **Niveau 0** et saute
  directement aux questions sur les freins (jamais de questions
  techniques à quelqu'un qui va systématiquement répondre "non" —
  ça le met en échec).
- Alimente uniquement la dimension "Compétences numériques".
- 22 questions, avec logique conditionnelle en cascade (B3.x affiché
  seulement si B2.1=Oui, B4.x affiché seulement si B3.1 et B3.2=Oui).

**Classification du niveau individuel (0 à 5)** — voir
`core/scoring.py::classifier_niveau_agent()` :

| Niveau | Profil |
|---|---|
| 0 | N'a jamais utilisé un ordinateur |
| 1 | Sait allumer/utiliser un ordinateur, usage smartphone basique |
| 2 | Utilise WhatsApp/réseaux sociaux, email de base |
| 3 | Utilise Word/Excel occasionnellement |
| 4 | Utilise couramment des outils métier, autonome |
| 5 | Autonome + capable de former d'autres agents |

**Important :** le score de la dimension "Compétences numériques" pour
une administration = **distribution des agents sur ces 6 niveaux**, PAS
une simple moyenne (une administration à 50% niveau 0 / 50% niveau 5
n'a pas le même profil qu'une administration à 100% niveau 2-3, même si
la moyenne se ressemble). Voir `distribution_niveaux_administration()`.

## Exigence architecturale clé : formulaires modifiables

Les deux formulaires doivent être **entièrement modifiables depuis
l'application**, sans intervention développeur, par un nouveau rôle :
**Administrateur de contenu**.

Conséquence sur le modèle de données : `Formulaire` → `VersionFormulaire`
→ `Question`. Quand une question est modifiée après que des réponses
existent déjà, on ne l'écrase jamais : on crée une nouvelle version, et
l'ancienne reste archivée liée aux réponses historiques (sinon on fausse
le suivi dans le temps, qui est la raison d'être de l'outil).

Voir `VersionFormulaire.save()` dans `core/models.py` — une seule version
active par formulaire à la fois.

## Les 5 rôles / personas

1. **Agent évaluateur** — remplit le Formulaire A pour son administration
2. **Agent enquêté** — répond individuellement au Formulaire B
3. **Enquêteur** — administre le Formulaire B en mode assisté
4. **DSI / Décideur** — consulte résultats, dashboard comparatif, rapports
5. **Administrateur de contenu** — gère dimensions/questions/versions
   (back-office, actuellement = Django Admin)

## Écrans prévus (cf. brief designer)

1. Page de connexion
2. Tableau de bord d'accueil (score global, alerte dimension faible)
3. Formulaire A — multi-étapes par dimension, barre de progression
4. Formulaire B — mode autonome ET mode assisté, logique conditionnelle
5. Page de résultats individuels — **radar chart** en pièce maîtresse
6. Page de comparaison multi-administrations
7. Rapport synthétique exportable (PDF)
8. Back-office de gestion des formulaires (dimensions, questions)

Direction visuelle : institutionnel mais moderne ("GovTech", pas "site
gouvernemental des années 2000"), bleu institutionnel + accent vif,
responsive obligatoire (connexions faibles fréquentes, usage mobile
important).

## État actuel du projet (déjà fait, testé et fonctionnel)

- ✅ `core/models.py` — 10 modèles complets, conformes au diagramme de classes
- ✅ `core/admin.py` — back-office fonctionnel (Administrateur de contenu)
- ✅ `core/scoring.py` — moteur de scoring, testé de bout en bout
  (calcul par dimension, pondération, score global, dimension la plus
  faible, classification individuelle 0-5)
- ✅ `core/management/commands/seed_data.py` — charge les 5 dimensions +
  44 questions (22 Formulaire A + 22 Formulaire B)
- ✅ Migrations testées, `python manage.py check` passe sans erreur

## Ce qui reste à faire

**Indépendant de la maquette (peut avancer maintenant) :**
- Tests unitaires du moteur de scoring
- Affiner le barème de conversion réponse → note (actuellement simplifié
  dans `normaliser_reponse()`)
- Implémenter la logique conditionnelle en cascade du Formulaire B
  (le champ `question_condition` existe déjà sur le modèle `Question`,
  prêt à être exploité par les vues)
- Vues et routing (`urls.py`, `views.py`) pour servir les formulaires
- Système d'authentification et de permissions par rôle (5 groupes)

**Dépend de la maquette du designer :**
- Templates HTML des formulaires A et B
- Tableau de bord + intégration Chart.js (radar)
- Page de comparaison multi-administrations
- Export PDF du rapport synthétique

## Diagrammes UML disponibles (Chapitre 3)

Fichiers `.drawio` (draw.io / diagrams.net) déjà produits :
- Diagramme de cas d'utilisation (5 acteurs, 12 cas d'utilisation, avec
  relation `<<include>>` vers "Calculer le score")
- Diagramme de classes (10 classes, correspond à `core/models.py`)
- Diagramme de séquence — remplissage Formulaire B mode assisté (avec
  bloc `alt` sur la question filtre B2.1)
- Diagramme de séquence — calcul du score et génération du rapport

## Conventions de code à respecter

- Noms de champs et de modèles en français (cohérence avec le mémoire
  rédigé en français, et avec les diagrammes UML déjà produits)
- Docstrings en français expliquant le "pourquoi" métier, pas juste le
  "quoi" technique — utile pour la rédaction du Chapitre 4
- Toute nouvelle logique de scoring ou de versioning doit rester dans
  des fonctions pures et testables (`core/scoring.py`), séparées des vues
