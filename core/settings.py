# core/settings.py
#
# Django settings for the RAG backend.
# All secrets are loaded from environment variables — never hardcode them here.
# Copy .env.example to .env and fill in your values before running.

from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Security ---
SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = os.getenv("DEBUG", "False") == "True"

# In production narrow this down to your actual domain / Render hostname.
# "ALLOWED_HOSTS=*" is acceptable for local dev but not for prod.
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")

# --- Application definition ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # pgvector adds the VectorField type and cosine-distance ORM helpers.
    "pgvector",
    "rest_framework",
    "documents",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

# --- Database ---
# PostgreSQL with pgvector extension.
# The extension itself is enabled via migration 0001_enable_vector.py.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# --- Auth password validators ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalisation ---
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static files ---
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Primary key type ---
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Gemini API key ---
# Read directly by documents/services/client.py via os.getenv("GEMINI_API_KEY").
# Declared here only as a reminder that it must be set in .env.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- DRF defaults ---
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    # TODO: Switch to TokenAuthentication or SessionAuthentication in production
    # and enable IsAuthenticated on each view.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
}

# --- Logging ---
# Routes application logs to the console.  In production point handlers at
# a file or a log aggregation service (e.g. Sentry, Datadog).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        # Show INFO+ from our own code; keep Django/libraries at WARNING.
        "documents": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# --- Celery (optional async ingestion) ---
# Uncomment and configure when you add a Redis broker.
# See documents/tasks.py for the task definition.
# CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# CELERY_RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# CELERY_TASK_SERIALIZER = "json"
# CELERY_RESULT_SERIALIZER = "json"
