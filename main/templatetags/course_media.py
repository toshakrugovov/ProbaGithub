# Фильтры для отображения медиа курса/урока через защищённый URL (тот же хост/порт)
from django import template
from django.conf import settings

register = template.Library()


def _media_prefix():
    """Безопасно получить префикс медиа-URL (никогда не бросает исключение)."""
    try:
        url = getattr(settings, 'MEDIA_URL', None) or '/media/'
        return (url if isinstance(url, str) else str(url)).rstrip('/') or '/media'
    except Exception:
        return '/media'


@register.filter
def course_media_path(file_path):
    """
    Если file_path — локальный путь вида /media/lesson_pages/... или /media/course_content/...,
    возвращает относительную часть (lesson_pages/1/2/file.pdf) для serve_course_media.
    Иначе возвращает пустую строку. Не бросает исключений.
    """
    try:
        if file_path is None:
            return ''
        s = (file_path if isinstance(file_path, str) else str(file_path)).strip()
        if not s:
            return ''
        prefix = _media_prefix()
        if not (s.startswith(prefix + '/') or s.startswith(prefix)):
            return ''
        if s.startswith(prefix + '/'):
            return s[len(prefix) + 1:]
        return s[len(prefix):].lstrip('/')
    except Exception:
        return ''


@register.filter
def is_local_course_media(file_path):
    """True, если путь — наш медиа (lesson_pages или course_content). Не бросает исключений."""
    try:
        rel = course_media_path(file_path)
        return bool(rel and (rel.startswith('lesson_pages/') or rel.startswith('course_content/')))
    except Exception:
        return False
