#!/bin/sh
# Démarrage du conteneur en production.
set -e

echo "→ Migrations"
python manage.py migrate --noinput

echo "→ Questionnaire de référence (idempotent)"
python manage.py seed_data

echo "→ Comptes de test (rôles + superuser 'admin'), resynchronisés à chaque démarrage"
python manage.py create_test_users

# Jeu de données de démonstration : uniquement si SEED_DEMO=1 (remet tout à zéro).
if [ "$SEED_DEMO" = "1" ]; then
  echo "→ SEED_DEMO=1 : (ré)génération du jeu de démonstration"
  python manage.py seed_demo --reset
fi

echo "→ Gunicorn sur le port ${PORT:-8000}"
# Peu de RAM sur l'offre gratuite : moins de workers, mais des threads pour
# encaisser l'attente des requêtes PostgreSQL (base distante). Les workers sont
# recyclés régulièrement pour éviter toute dérive mémoire (WeasyPrint).
exec gunicorn maturite_numerique.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --worker-class gthread \
  --workers "${WEB_CONCURRENCY:-2}" \
  --threads "${WEB_THREADS:-4}" \
  --max-requests 400 --max-requests-jitter 50 \
  --timeout 60 \
  --access-logfile - --error-logfile -
