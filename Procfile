web: python manage.py collectstatic --noinput && python manage.py migrate --noinput && gunicorn chatbot_site.wsgi:application --bind 0.0.0.0:$PORT
