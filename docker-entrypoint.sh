#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."
# Используем переменные окружения или значения по умолчанию
DB_HOST=${DB_HOST:-db}
DB_PORT=${DB_PORT:-5432}

while ! nc -z $DB_HOST $DB_PORT; do
  echo "Waiting for PostgreSQL at $DB_HOST:$DB_PORT..."
  sleep 1
done
echo "PostgreSQL is ready!"

# Выполняем миграции
echo "Running migrations..."
python manage.py migrate --noinput

# Собираем статические файлы
echo "Collecting static files..."
python manage.py collectstatic --noinput || true

# Создаем суперпользователя, если его нет
echo "Checking for superuser..."
python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(email='admin@gmail.com').exists():
    User.objects.create_superuser(
        username='admin',
        email='admin@gmail.com',
        password='4856106Anton'
    )
    print("Superuser created: admin@gmail.com / 4856106Anton")
else:
    print("Superuser already exists")
EOF

# Запускаем команду, переданную в CMD
exec "$@"

