# Use an official Python runtime as the base image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Cloud Run sets PORT=8080; default for local runs
ENV PORT=8080

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY . .

# Collect static files (Django)
RUN python manage.py collectstatic --noinput --clear 2>/dev/null || true

# Run gunicorn bound to 0.0.0.0:PORT so Cloud Run can send traffic
CMD exec gunicorn chatbot_site.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0
