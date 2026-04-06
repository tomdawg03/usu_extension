"""
Django settings for chatbot_site project.
"""

from pathlib import Path

import dj_database_url
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
#
# Local: omit DATABASE_URL (or leave unset) to use SQLite (db.sqlite3).
# Production (e.g. Cloud SQL): set DATABASE_URL to a PostgreSQL URL
# (including Cloud SQL Unix socket: ?host=/cloudsql/PROJECT:REGION:INSTANCE).

_database_url = os.environ.get("DATABASE_URL", "").strip()
if _database_url:
    DATABASES = {
        "default": dj_database_url.parse(_database_url, conn_max_age=600),
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        },
    }


# Internationalization
# https://docs.djangoproject.com/en/stable/topics/i18n/

LANGUAGE_CODE = 'en-us'

# US Mountain Time (MST / MDT per daylight saving)
TIME_ZONE = 'America/Denver'

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
# Responses API + file_search (replaces Assistants when enabled and vector stores are set)
_openai_vs = os.environ.get("OPENAI_VECTOR_STORE_IDS", "").strip()
OPENAI_VECTOR_STORE_IDS = [x.strip() for x in _openai_vs.split(",") if x.strip()]
# Default: use Responses API when vector store IDs are configured
CHAT_USE_RESPONSES_API = os.environ.get(
    "CHAT_USE_RESPONSES_API",
    "true" if OPENAI_VECTOR_STORE_IDS else "false",
).lower() in ("1", "true", "yes")
OPENAI_RESPONSES_MODEL = os.environ.get("OPENAI_RESPONSES_MODEL", "gpt-4o").strip()
# Optional: drop file_search results below this relevance score (0–1). Empty = no score filter.
_fs_min = os.environ.get("FILE_SEARCH_MIN_RESULT_SCORE", "").strip()
FILE_SEARCH_MIN_RESULT_SCORE = float(_fs_min) if _fs_min else None

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

# GCS chat logging
GCS_CHAT_LOG_BUCKET = os.environ.get('GCS_CHAT_LOG_BUCKET', '').strip()
GCS_CHAT_LOG_PREFIX = os.environ.get('GCS_CHAT_LOG_PREFIX', 'chat-logs').strip() or 'chat-logs'
GCP_PROJECT = os.environ.get('GCP_PROJECT', '').strip()
APP_ENV = os.environ.get('APP_ENV', '').strip()

# Free tier: max successful chat answers per IP per rolling window (see chat_api).
CHAT_FREE_QUESTION_LIMIT = int(os.environ.get('CHAT_FREE_QUESTION_LIMIT', '7'))
CHAT_FREE_QUESTION_WINDOW_HOURS = int(os.environ.get('CHAT_FREE_QUESTION_WINDOW_HOURS', '24'))

# Chat latency / Assistants API
# Poll OpenAI run status this often (seconds). Lower = slightly faster time-to-first-byte after the run finishes; too low may rate-limit.
CHAT_ASSISTANT_POLL_SECONDS = float(os.environ.get('CHAT_ASSISTANT_POLL_SECONDS', '0.25'))
# If False, skip fact-sheet overlap check after each reply (loads full PDF index; saves CPU/IO per message).
CHAT_RETRIEVAL_VERIFY = os.environ.get('CHAT_RETRIEVAL_VERIFY', 'True') == 'True'
# Source URL matching (keyword pool + cosine similarity on URL text)
SOURCE_URL_TOP_FOR_SIMILARITY = int(os.environ.get('SOURCE_URL_TOP_FOR_SIMILARITY', '80'))
SOURCE_URL_MIN_SIMILARITY = float(os.environ.get('SOURCE_URL_MIN_SIMILARITY', '0.06'))
SOURCE_URL_MIN_OVERLAP = int(os.environ.get('SOURCE_URL_MIN_OVERLAP', '1'))
SOURCE_URL_STRONG_OVERLAP = int(os.environ.get('SOURCE_URL_STRONG_OVERLAP', '4'))
# Cap assistant output length (completion tokens per run). Empty = no cap. Typical short answers: 400–800.
_ch_max = os.environ.get('CHAT_ASSISTANT_MAX_COMPLETION_TOKENS', '').strip()
CHAT_ASSISTANT_MAX_COMPLETION_TOKENS = int(_ch_max) if _ch_max.isdigit() else None
