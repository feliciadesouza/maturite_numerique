FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Dépendances système : Pango/Cairo pour WeasyPrint (export PDF), libpq pour
# PostgreSQL, polices pour un rendu correct des PDF.
RUN apt-get update && apt-get install --no-install-recommends -y \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        shared-mime-info \
        libpq5 \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY maturite_numerique/requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY maturite_numerique/ ./

# Collecte des fichiers statiques au build (SECRET_KEY factice suffisant ici).
RUN SECRET_KEY=build-only DEBUG=False python manage.py collectstatic --noinput

EXPOSE 8000

# Au démarrage : migrations + seeds + superuser optionnel, puis gunicorn.
# Ne jamais utiliser `runserver` en conteneur.
CMD ["sh", "entrypoint.sh"]
