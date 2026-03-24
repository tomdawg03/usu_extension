"""
Django settings for chatbot_site project.
"""

from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env (project root)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/stable/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-dev-key-change-in-production'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
    'extensionassistant.org',
    'www.extensionassistant.org',
    'usu-extension-test-905684985699.europe-west1.run.app',
    'test-usu-extension-905684985699.us-west1.run.app',
    '127.0.0.1',
    'usu-extension-381213932906.us-west1.run.app',
]

# Required for CSRF when serving on HTTPS (e.g. Cloud Run)
CSRF_TRUSTED_ORIGINS = [
    'https://extensionassistant.org',
    'https://www.extensionassistant.org',
    'https://usu-extension-test-905684985699.europe-west1.run.app',
    'https://test-usu-extension-905684985699.us-west1.run.app',
    'https://usu-extension-381213932906.us-west1.run.app',
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'chat',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'chatbot_site.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
            ],
        },
    },
]

WSGI_APPLICATION = 'chatbot_site.wsgi.application'


# Database
# https://docs.djangoproject.com/en/stable/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Internationalization
# https://docs.djangoproject.com/en/stable/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/stable/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
# https://docs.djangoproject.com/en/stable/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()

# Backend data
FACT_SHEETS_DB_PATH = BASE_DIR / "Backend" / "fact_sheets.db"
COUNTY_CONTACTS_CSV_PATH = BASE_DIR / "Backend" / "County Contact info - Sheet1 (1).csv"
HARDINESS_ZONE_CSV_PATH = BASE_DIR / "Backend" / "Hardiness Zone - Sheet1.csv"

# Extension articles
EXTENSION_ARTICLES_DB_PATH = BASE_DIR / "extension_articles.db"
EXTENSION_PRODUCTS_CSV_PATH = BASE_DIR / "extension-products_2026_02_06_with-domain.csv"

# Email config
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
ESCALATION_EMAIL = os.environ.get('ESCALATION_EMAIL', 'lauren.knox@usu.edu')
ESCALATION_CC_EMAIL = os.environ.get('ESCALATION_CC_EMAIL', 'christopher.t.corcoran@usu.edu')
