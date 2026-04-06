#!/bin/sh
set -e
echo "[entrypoint] Running database migrations..."
python manage.py migrate --noinput
echo "[entrypoint] Starting gunicorn on port ${PORT:-8080}"
exec gunicorn chatbot_site.wsgi:application --bind "0.0.0.0:${PORT:-8080}" --workers 1 --threads 8 --timeout 0
