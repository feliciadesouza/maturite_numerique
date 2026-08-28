FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY maturite_numerique/requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY maturite_numerique/ ./

# Collecte des fichiers statiques au build (SECRET_KEY factice suffisant ici).
RUN SECRET_KEY=build-only python manage.py collectstatic --noinput

EXPOSE 8000

# Au démarrage : migrations puis serveur WSGI de production (gunicorn).
# Ne jamais utiliser `runserver` en conteneur.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn maturite_numerique.wsgi:application --bind 0.0.0.0:8000 --workers 3"]
