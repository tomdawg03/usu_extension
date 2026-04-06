#!/bin/sh
set -e
python manage.py migrate --noinput
exec gunicorn chatbot_site.wsgi:application --bind "0.0.0.0:${PORT:-8080}" --workers 1 --threads 8 --timeout 0
