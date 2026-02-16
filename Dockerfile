# Используем официальный Python образ
FROM python:3.12-slim

# Устанавливаем переменные окружения
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Устанавливаем системные зависимости и шрифты для поддержки кириллицы в PDF
RUN apt-get update && apt-get install -y \
    postgresql-client \
    libpq-dev \
    gcc \
    netcat-openbsd \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию
WORKDIR /app

# Обновляем pip для более быстрой установки
RUN pip install --upgrade pip setuptools wheel

# Копируем requirements.txt и устанавливаем зависимости
# Используем увеличенные таймауты для надежной установки
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=300 --retries=5 -r requirements.txt

# Копируем весь проект
COPY . .

# Создаем директории для статики и медиа
RUN mkdir -p /app/staticfiles /app/media

# Собираем статические файлы (может не работать без БД, но это нормально)
RUN python manage.py collectstatic --noinput || true

# Создаем пользователя для запуска приложения
RUN useradd -m -u 1000 appuser || true

# Копируем и делаем исполняемым entrypoint скрипт
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Устанавливаем права на файлы (если возможно)
RUN chown -R appuser:appuser /app 2>/dev/null || true

# НЕ переключаемся на appuser здесь, так как при монтировании тома
# файлы могут принадлежать другому пользователю
# Переключение будет выполнено в entrypoint скрипте при необходимости

# Открываем порт
EXPOSE 8000

# Entrypoint скрипт будет запущен при старте контейнера
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "mptcourse.wsgi:application"]

