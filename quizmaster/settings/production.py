from .base import *
import dj_database_url

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases
# In production, we use PostgreSQL. We can configure it via DATABASE_URL or individual env vars.
DATABASE_URL = config('DATABASE_URL', default=None)

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='quizmaster'),
            'USER': config('DB_USER', default='quizmaster_user'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }

# HTTPS and Security Headers
# Only enable these if SSL is configured (recommended for production)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Static files storage for production (compressing and caching)
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# CSRF Trusted Origins for production HTTPS requests
CSRF_TRUSTED_ORIGINS = []
allowed_hosts = config('ALLOWED_HOSTS', default='').split(',')
for host in allowed_hosts:
    host = host.strip()
    if host:
        if host == '*':
            continue
        if host.startswith('.'):
            CSRF_TRUSTED_ORIGINS.append(f"https://*{host}")
            CSRF_TRUSTED_ORIGINS.append(f"http://*{host}")
        else:
            CSRF_TRUSTED_ORIGINS.append(f"https://{host}")
            CSRF_TRUSTED_ORIGINS.append(f"http://{host}")

# Auto-detect Render's external URL
RENDER_EXTERNAL_URL = config('RENDER_EXTERNAL_URL', default=None)
if RENDER_EXTERNAL_URL:
    CSRF_TRUSTED_ORIGINS.append(RENDER_EXTERNAL_URL)

