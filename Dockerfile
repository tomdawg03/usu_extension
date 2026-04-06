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

RUN chmod +x docker-entrypoint.sh

# Collect static files (Django)
RUN python manage.py collectstatic --noinput --clear 2>/dev/null || true

# Create SQLite schema inside the image. If Cloud Run overrides CMD and skips
# docker-entrypoint.sh, the app still has tables (until you add new migrations).
RUN python manage.py migrate --noinput

# Apply DB migrations on each container start, then run gunicorn (Cloud Run sets PORT)
CMD ["./docker-entrypoint.sh"]
