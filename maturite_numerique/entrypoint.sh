#!/bin/sh
# Démarrage du conteneur en production.
set -e

echo "→ Migrations"
python manage.py migrate --noinput

echo "→ Questionnaire de référence (idempotent)"
python manage.py seed_data

echo "→ Comptes de test par rôle (idempotent)"
python manage.py create_test_users

# Superuser d'administration : créé/resynchronisé depuis DJANGO_SUPERUSER_*.
echo "→ Superuser d'administration"
python manage.py ensure_superuser

# Jeu de données de démonstration : uniquement si SEED_DEMO=1 (remet tout à zéro).
if [ "$SEED_DEMO" = "1" ]; then
  echo "→ SEED_DEMO=1 : (ré)génération du jeu de démonstration"
  python manage.py seed_demo --reset
fi

echo "→ Gunicorn sur le port ${PORT:-8000}"
exec gunicorn maturite_numerique.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-3}" \
  --access-logfile - --error-logfile -
