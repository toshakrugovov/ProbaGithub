from pathlib import Path
import os

# Загрузка переменных окружения из .env файла (если установлен python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Если python-dotenv не установлен, просто пропускаем загрузку .env файла
    # Переменные окружения можно задать другим способом
    pass

# ================== Пути ==================
BASE_DIR = Path(__file__).resolve().parent.parent

# ================== Секрет и отладка ==================
SECRET_KEY = os.environ.get('SECRET_KEY', os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-s=gsg*^y^b&gzj9=v67@es*wdg&fzy-fmo-ox$2fq0e(oc+h3l'))
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'
ALLOWED_HOSTS = ['*']


# Принудительно показывать кастомную страницу 500 даже в DEBUG режиме
# Это позволяет middleware перехватывать исключения и показывать кастомную страницу
DEBUG_PROPAGATE_EXCEPTIONS = False  # Django будет использовать наш handler500

# ================== Приложения ==================
# Проверка наличия django_prometheus (опциональная зависимость)
try:
    import django_prometheus
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',  # Для обслуживания статических файлов в DEBUG режиме
    'rest_framework',
    'drf_yasg',
    'main.apps.MainConfig',
]

# Добавляем django_prometheus только если доступен
if PROMETHEUS_AVAILABLE:
    INSTALLED_APPS.append('django_prometheus')

# ================== Middleware ==================
MIDDLEWARE = []

# Добавляем Prometheus middleware только если доступен
if PROMETHEUS_AVAILABLE:
    MIDDLEWARE.append('django_prometheus.middleware.PrometheusBeforeMiddleware')

MIDDLEWARE.extend([
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Для обслуживания статических файлов в продакшене
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'main.middleware.DatabaseEmptyCheckMiddleware',  # Проверка, что БД не пуста (должен быть после SessionMiddleware)
    'main.middleware.BlockedUserMiddleware',  # Проверка блокировки пользователя (после AuthenticationMiddleware)
    'main.middleware.AdminAccessMiddleware',
    'main.middleware.CustomErrorHandlerMiddleware', 
])

# Добавляем Prometheus middleware в конец только если доступен
if PROMETHEUS_AVAILABLE:
    MIDDLEWARE.append('django_prometheus.middleware.PrometheusAfterMiddleware')

# ================== URLs ==================
ROOT_URLCONF = 'mptcourse.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'mptcourse.wsgi.application'


db_host = os.environ.get('DB_HOST', 'localhost')
is_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'
if db_host == 'db' and not is_docker:
    db_host = 'localhost'

USE_SQLITE = os.environ.get('USE_SQLITE', 'True').lower() == 'true'

if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'mptcourse'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', '1'),
            'HOST': db_host,
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }

# ================== Валидация пароля ==================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ================== Локализация ==================
LANGUAGE_CODE = 'ru-RU'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

# ================== Статические файлы ==================
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'main' / 'static'
]

# WhiteNoise для обслуживания статических файлов (только в продакшене)
if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ================== Медиа ==================
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ================== Сессии и Cookies ==================
# Для продакшена с HTTPS установите в True
SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'
CSRF_COOKIE_SECURE = os.environ.get('CSRF_COOKIE_SECURE', 'False') == 'True'
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False

# ================== Переменные по умолчанию ==================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ================== Login ==================
LOGIN_URL = '/login/'                # redirect при @login_required
LOGIN_REDIRECT_URL = '/profile/'     # куда редирект после login()
LOGOUT_REDIRECT_URL = '/'

# ================== Django REST Framework ==================
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
}

# ================== Настройки кастомного пользователя (если будет) ==================
# AUTH_USER_MODEL = 'main.User'  # Раскомментировать, если есть кастомная модель

# ================== Настройки администратора ==================
# Секретное слово для восстановления БД (можно изменить через переменную окружения)
ADMIN_RESTORE_SECRET = os.environ.get('ADMIN_RESTORE_SECRET', 'mimi')

# ================== Настройки шифрования ==================
# Ключ шифрования для чувствительных данных в БД
# Можно задать через переменную окружения ENCRYPTION_KEY
# Если не задан, будет сгенерирован на основе SECRET_KEY
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', None)

# Включить шифрование чувствительных полей (по умолчанию True)
ENABLE_DATA_ENCRYPTION = os.environ.get('ENABLE_DATA_ENCRYPTION', 'True').lower() == 'true'