"""Django settings for InstAI - a local, single-user application."""
from __future__ import annotations

import os
import secrets
import sys
import tempfile
from pathlib import Path

from .envfile import BASE_DIR, ENV_PATH, load_env, write_env_value

load_env()

VERSION = "0.1.0"


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


DEBUG = _env_bool("INSTAI_DEBUG", False)

# A stable secret key per installation, generated on first run and kept in .env.
SECRET_KEY = os.environ.get("INSTAI_SECRET_KEY", "").strip()
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(50)
    if not (os.environ.get("INSTAI_TESTING") or "pytest" in sys.modules):
        try:
            write_env_value("INSTAI_SECRET_KEY", SECRET_KEY, ENV_PATH)
        except OSError:
            pass

HOST = os.environ.get("INSTAI_HOST", "127.0.0.1")
PORT = int(os.environ.get("INSTAI_PORT", "8765"))
# Only local host names: protects the local API from DNS-rebinding pages.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]
if HOST not in ("127.0.0.1", "localhost", "0.0.0.0", "::1"):
    ALLOWED_HOSTS.append(HOST)
if os.environ.get("INSTAI_ALLOWED_HOSTS"):
    ALLOWED_HOSTS += [h.strip() for h in os.environ["INSTAI_ALLOWED_HOSTS"].split(",") if h.strip()]

# pytest imports the settings before conftest.py runs, so tests are recognised by the module, not only by the variable
TESTING = bool(os.environ.get("INSTAI_TESTING")) or "pytest" in sys.modules
if TESTING:
    os.environ.setdefault("INSTAI_TESTING", "1")
    if not os.environ.get("INSTAI_DATA_DIR"):
        _tmp_root = tempfile.mkdtemp(prefix="instai-test-")
        os.environ["INSTAI_DATA_DIR"] = os.path.join(_tmp_root, "data")
        import atexit
        import shutil

        atexit.register(shutil.rmtree, _tmp_root, ignore_errors=True)  # rendered test videos are large: never leave them behind
DATA_DIR = Path(os.environ.get("INSTAI_DATA_DIR") or BASE_DIR / "data").resolve()
MEDIA_ROOT = DATA_DIR / "media"
LOG_DIR = DATA_DIR / "logs"
MODELS_DIR = Path(os.environ.get("INSTAI_MODELS_DIR") or BASE_DIR / "models").resolve()
TOOLS_DIR = Path(os.environ.get("INSTAI_TOOLS_DIR") or BASE_DIR / "tools").resolve()
for _d in (DATA_DIR, MEDIA_ROOT, LOG_DIR, DATA_DIR / "staticfiles"):
    _d.mkdir(parents=True, exist_ok=True)

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "instai.core",
    "instai.pages",
    "instai.styles",
    "instai.story",
    "instai.studio",
    "instai.assets",
    "instai.jobs",
    "instai.publishing",
    "instai.production",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "instai.urls"
WSGI_APPLICATION = "instai.wsgi.application"
TEMPLATES: list = []

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": 30,
            "transaction_mode": "IMMEDIATE",
            "init_command": (
                "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; "
                "PRAGMA busy_timeout=30000; PRAGMA foreign_keys=ON;"
            ),
        },
    }
}
if TESTING:
    # a file database (not :memory:) so worker threads and the test thread share one WAL database
    DATABASES["default"]["TEST"] = {"NAME": str(DATA_DIR / "test_db.sqlite3")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "fa"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "instai" / "static"]  # the built UI lives in instai/static/app
STATIC_ROOT = DATA_DIR / "staticfiles"
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True  # the UI is rebuilt while the server may be running
APPEND_SLASH = False
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024 * 1024  # reference images arrive as base64 JSON

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "instai.core.errors.api_exception_handler",
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S.%fZ",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"redact": {"()": "instai.core.logs.RedactFilter"}},
    "formatters": {
        "json": {"()": "instai.core.logs.JsonFormatter"},
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain", "filters": ["redact"]},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "instai.log"),
            "maxBytes": 5_000_000,
            "backupCount": 3,
            "encoding": "utf-8",
            "formatter": "json",
            "filters": ["redact"],
        },
    },
    "loggers": {
        "instai": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["file"], "level": "WARNING", "propagate": False},
    },
}

# Folder with the built React UI (committed to git so the GPU PC does not need Node).
UI_DIR = BASE_DIR / "instai" / "static" / "app"
