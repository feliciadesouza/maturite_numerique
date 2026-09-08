# Sécurité de l'authentification et connexion en 2 étapes (OTP)

## 1. Mécanismes de sécurité déjà en place

Avant l'ajout de l'OTP, l'application s'appuyait sur plusieurs couches,
toutes actives en production (`maturite_numerique/settings.py`) :

- **Mots de passe** : validateurs standard Django (`AUTH_PASSWORD_VALIDATORS`)
  — longueur minimale, pas trop proche du nom d'utilisateur, pas dans la
  liste des mots de passe courants, pas 100 % numérique.
- **Sessions** : cookies `Secure` + `HttpOnly` en production
  (`SESSION_COOKIE_SECURE`), CSRF token sur tous les formulaires
  (`CSRF_COOKIE_SECURE`, `CSRF_TRUSTED_ORIGINS`).
- **Transport** : redirection HTTPS forcée (`SECURE_SSL_REDIRECT`), HSTS
  activé 1 an avec sous-domaines et préchargement
  (`SECURE_HSTS_SECONDS=31536000`), `X_FRAME_OPTIONS=DENY`,
  `SECURE_CONTENT_TYPE_NOSNIFF=True`.
- **Limitation de débit** (`django-ratelimit`) :
  - `/connexion/` : 10 tentatives/minute/IP
  - `/contact/` : 5/minute + 30/heure/IP
  - `/enquete/demarrer/` : 15/heure/IP
- **Contrôle d'accès par rôle** (`core/permissions.py`) : décorateur
  `role_required(*roles)` — visiteur non connecté → redirigé vers
  `/connexion/` ; connecté mais mauvais rôle → `403 Forbidden` (pas de fuite
  d'information sur l'existence de la page). Le superuser passe toujours
  (compte de secours/support).
- **Séparation des rôles** : 4 rôles avec compte (`agent_evaluateur`,
  `enqueteur`, `dsi_decideur`, `admin_contenu`), chacun avec sa page
  d'atterrissage (`ROLE_HOME_URLS`) et ses vues propres ; l'agent enquêté
  répond sans compte via un lien à token (`Agent.token`, UUID).
- **Aucun secret dans le code** : tout est lu depuis l'environnement
  (`python-decouple`) — clé Django, base de données, e-mail.

Ce que l'authentification ne couvrait **pas** jusqu'ici : une fois
identifiant + mot de passe corrects, la session s'ouvrait directement. Un
mot de passe volé ou deviné suffisait donc à se connecter.

## 2. Nouvelle fonctionnalité : connexion en 2 étapes par e-mail

Objectif : ajouter un second facteur (« quelque chose que vous recevez »)
sans casser les comptes existants qui n'ont pas d'adresse e-mail
renseignée (comptes de démo créés par `create_test_users`).

### Fonctionnement

```
Identifiant + mot de passe (login_view)
        │
        ├── compte SANS e-mail  → session ouverte directement (inchangé)
        │
        └── compte AVEC e-mail  → code à 6 chiffres généré + envoyé
                                   │
                                   ▼
                    /connexion/verification/ (verification_code_view)
                                   │
                    code correct, < 10 min, jamais utilisé ?
                                   │
                         oui ──────┴────── non
                          │                 │
                   session ouverte    message d'erreur,
                   → page du rôle     nouvelle tentative
```

### Détails techniques

- **Modèle `CodeConnexion`** (`core/models.py`, migration `0011`) : code
  (6 chiffres, généré avec `secrets.randbelow`, pas `random`), utilisateur,
  date de création, date d'expiration (+10 min), drapeau `utilise`.
- **`login_view`** : après `authenticate()` réussi, si `user.email` est
  renseigné, envoie le code (`_envoyer_code_connexion`) et stocke
  `user.pk` en session (`code_connexion_user_id`) au lieu d'appeler
  `login()` tout de suite.
- **`verification_code_view`** (`/connexion/verification/`) : formulaire
  à 6 chiffres (`CodeConnexionForm`), bouton « Renvoyer le code », limité à
  10 tentatives/minute/IP (même mécanisme que le login). Le code est
  marqué `utilise=True` dès validation (usage unique).
- **E-mail envoyé** : `core/templates/email/code_connexion.txt`, sujet
  « Votre code de connexion ».
- **Repli volontaire sans e-mail** : ce choix évite qu'un compte provisionné
  sans adresse (via `/admin/`) se retrouve bloqué. Un administrateur qui
  veut activer la 2FA pour un utilisateur n'a qu'à renseigner son e-mail.
- **Tests** : 8 tests dédiés (`CodeConnexionTests` dans `core/tests.py`)
  couvrant redirection, e-mail envoyé, bon/mauvais/expiré/déjà-utilisé,
  renvoi, repli sans e-mail. 71 tests au total dans le projet.

### Configuration de l'envoi (SMTP)

Sans configuration, `EMAIL_BACKEND` reste le backend console (les e-mails
s'affichent dans les logs, rien n'est réellement envoyé — pratique en dev).
Pour un envoi réel, 6 variables d'environnement (voir `.env.example`) :

```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=...
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
EMAIL_USE_TLS=True
```

En local, testé et validé avec [Resend](https://resend.com) (`smtp.resend.com`).
**Limite connue** : leur domaine d'essai partagé (`onboarding@resend.dev`)
n'autorise l'envoi qu'vers l'adresse ayant créé le compte Resend — il faudra
vérifier un domaine propre (DNS SPF/DKIM) avant une mise en production
destinée à de vrais utilisateurs.

## 3. Reste à faire

- Vérifier un domaine sur le service SMTP choisi avant la mise en prod du
  SMTP réel (sinon les e-mails ne partiront qu'à une seule adresse de test).
- Ajouter les variables `EMAIL_*` dans les variables d'environnement Render.
- S'assurer que les vrais comptes créés via `/admin/` ont une adresse
  e-mail renseignée, pour bénéficier de la 2FA.
- Fusionner la branche `feature/otp-connexion` (PR à créer manuellement).
