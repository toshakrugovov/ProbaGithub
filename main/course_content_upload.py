"""
Обработка загружаемых файлов курса: PDF, PowerPoint, Word.
Для файла автоматически создаётся по одной странице контента на каждую страницу/слайд.
Поддержка загрузки PDF по ссылке (в т.ч. Google Drive).
"""
import os
import re
from django.conf import settings


def _sanitize_filename(name):
    """Безопасное имя файла."""
    base = os.path.basename(name)
    base, ext = os.path.splitext(base)
    base = re.sub(r'[^\w\s\-]', '', base)[:80] or 'file'
    return base + ext.lower()


def _get_media_root():
    """Возвращает MEDIA_ROOT как строку (для совместимости с Windows и os.path)."""
    root = getattr(settings, 'MEDIA_ROOT', None)
    if not root:
        raise ValueError('В настройках проекта не задан MEDIA_ROOT. Задайте MEDIA_ROOT в settings.py для загрузки файлов.')
    return os.path.normpath(os.path.abspath(str(root)))


def _ensure_media_root():
    """Создаёт каталог MEDIA_ROOT, если его нет (для загрузки файлов)."""
    os.makedirs(_get_media_root(), exist_ok=True)


def _save_upload(uploaded_file, course_id):
    """Сохраняет файл в media/course_content/<course_id>/ и возвращает относительный URL. В БД хранится только путь, не файл."""
    _ensure_media_root()
    root = _get_media_root()
    subdir = os.path.join('course_content', str(course_id))
    dest_dir = os.path.join(root, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    name = _sanitize_filename(uploaded_file.name)
    path = os.path.join(dest_dir, name)
    with open(path, 'wb') as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    media_url = (getattr(settings, 'MEDIA_URL', '/media/') or '/media/').rstrip('/')
    return (media_url + '/' + subdir.replace('\\', '/') + '/' + name).replace('\\', '/')


def _lesson_media_subdir(course_id, lesson_id):
    return os.path.join('lesson_pages', str(course_id), str(lesson_id))


def save_lesson_page_image(uploaded_file, course_id, lesson_id, slot_index=0):
    """Сохраняет только изображение страницы урока (JPG, PNG, WebP, GIF) в media/lesson_pages/... и возвращает URL."""
    _ensure_media_root()
    root = _get_media_root()
    subdir = _lesson_media_subdir(course_id, lesson_id)
    dest_dir = os.path.join(root, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    name = _sanitize_filename(uploaded_file.name)
    ext = (os.path.splitext(name)[-1] or '').lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
        name = (name or f'img_{slot_index}') + '.jpg'
    path = os.path.join(dest_dir, name)
    with open(path, 'wb') as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    media_url = (getattr(settings, 'MEDIA_URL', '/media/') or '/media/').rstrip('/')
    return (media_url + '/' + subdir.replace('\\', '/') + '/' + name).replace('\\', '/')


def save_lesson_page_pdf_file(uploaded_file, course_id, lesson_id, slot_index=0):
    """Сохраняет только PDF-файл страницы урока в media/lesson_pages/... и возвращает URL."""
    _ensure_media_root()
    root = _get_media_root()
    subdir = _lesson_media_subdir(course_id, lesson_id)
    dest_dir = os.path.join(root, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    name = _sanitize_filename(uploaded_file.name)
    if not name or not name.lower().endswith('.pdf'):
        name = (name or f'page_{slot_index}').rstrip('.') + '.pdf'
    path = os.path.join(dest_dir, name)
    with open(path, 'wb') as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    media_url = (getattr(settings, 'MEDIA_URL', '/media/') or '/media/').rstrip('/')
    return (media_url + '/' + subdir.replace('\\', '/') + '/' + name).replace('\\', '/')


def save_lesson_page_file(uploaded_file, course_id, lesson_id, slot_index=0):
    """Сохраняет файл страницы урока (изображение или PDF) в media/lesson_pages/... — для обратной совместимости; предпочтительно использовать save_lesson_page_image / save_lesson_page_pdf_file."""
    _ensure_media_root()
    root = _get_media_root()
    subdir = _lesson_media_subdir(course_id, lesson_id)
    dest_dir = os.path.join(root, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    name = _sanitize_filename(uploaded_file.name)
    if not name:
        name = f'page_{slot_index}' + os.path.splitext(uploaded_file.name)[-1].lower() or '.bin'
    path = os.path.join(dest_dir, name)
    with open(path, 'wb') as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    media_url = (getattr(settings, 'MEDIA_URL', '/media/') or '/media/').rstrip('/')
    return (media_url + '/' + subdir.replace('\\', '/') + '/' + name).replace('\\', '/')


def save_course_cover(uploaded_file, course_id):
    """Сохраняет главное фото курса в media/course_covers/<course_id>/ и возвращает URL. В БД хранится только путь (cover_image_path)."""
    _ensure_media_root()
    root = _get_media_root()
    subdir = os.path.join('course_covers', str(course_id))
    dest_dir = os.path.join(root, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    name = _sanitize_filename(uploaded_file.name)
    if not name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
        name = name + '.jpg'
    path = os.path.join(dest_dir, name)
    with open(path, 'wb') as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    media_url = (getattr(settings, 'MEDIA_URL', '/media/') or '/media/').rstrip('/')
    return (media_url + '/' + subdir.replace('\\', '/') + '/' + name).replace('\\', '/')


def _google_drive_file_id(url):
    """Из ссылки Google Drive извлекает file_id. Иначе возвращает None."""
    if not url or not isinstance(url, str):
        return None
    s = url.strip()
    # https://drive.google.com/file/d/FILE_ID/view...
    m = re.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', s)
    if m:
        return m.group(1)
    # https://drive.google.com/open?id=FILE_ID
    m = re.search(r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)', s)
    if m:
        return m.group(1)
    m = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', s)
    if m:
        return m.group(1)
    return None


def _download_url_to_bytes(url, timeout=60, max_size=100 * 1024 * 1024):
    """
    Скачивает файл по URL (поддержка Google Drive: конвертация ссылки в прямую).
    Возвращает (bytes, suggested_filename или None). При ошибке бросает ValueError.
    """
    import urllib.request
    url = (url or '').strip()
    if not url:
        raise ValueError('Пустой URL')
    # Конвертация ссылки Google Drive в прямую загрузку
    file_id = _google_drive_file_id(url)
    if file_id:
        url = f'https://drive.google.com/uc?export=download&id={file_id}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; MptCourse/1.0)'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read(max_size + 1)
            if len(content) > max_size:
                raise ValueError(f'Файл слишком большой (макс. {max_size // (1024*1024)} МБ)')
            # Google Drive часто отдаёт HTML вместо файла: «Нет доступа», страница подтверждения и т.д.
            if content[:500].strip().lower().startswith(b'<!'):
                sample = content[:2000].decode('utf-8', errors='ignore').lower()
                if 'нет доступа' in sample or 'access denied' in sample or 'drive.google.com' in sample:
                    raise ValueError(
                        'Google Drive вернул страницу «Нет доступа»: файл для сервера недоступен. '
                        'Сделайте доступ «Всем, у кого есть ссылка» (правый клик по файлу → Настройки доступа). '
                        'Если вы в организации — политики могут запрещать такие ссылки; тогда загрузите PDF файлом.'
                    )
                raise ValueError(
                    'По ссылке пришла веб-страница, а не файл. Загрузите PDF файлом или откройте доступ по ссылке.'
                )
            filename = None
            cd = resp.headers.get('Content-Disposition')
            if cd and 'filename=' in cd:
                m = re.search(r'filename[*]?=(?:UTF-8\'\')?["\']?([^"\';]+)', cd, re.I)
                if m:
                    filename = m.group(1).strip()
            return (content, filename)
    except urllib.error.HTTPError as e:
        raise ValueError(f'Ошибка загрузки: {e.code} {e.reason}')
    except urllib.error.URLError as e:
        raise ValueError(f'Не удалось открыть ссылку: {e.reason}')
    except OSError as e:
        raise ValueError(f'Ошибка загрузки: {e}')


def download_pdf_from_url(url, course_id, lesson_id, slot_index=0):
    """
    Скачивает PDF по ссылке (прямая или Google Drive) и сохраняет в media/lesson_pages/...
    Возвращает URL сохранённого файла (/media/...). При ошибке бросает ValueError.
    """
    content, suggested_name = _download_url_to_bytes(url)
    if not content:
        raise ValueError('По ссылке ничего не получено')
    # Проверка, что это похоже на PDF
    if not content.strip()[:20].startswith(b'%PDF'):
        sample = content[:3000].decode('utf-8', errors='ignore').lower()
        if 'нет доступа' in sample or 'access denied' in sample:
            raise ValueError(
                'Google Drive отдал страницу «Нет доступа». Выдайте доступ «Всем, у кого есть ссылка» или загрузите PDF файлом.'
            )
        raise ValueError('По ссылке получен не PDF (ссылка ведёт на страницу). Используйте прямую ссылку на PDF или загрузите файл.')
    _ensure_media_root()
    root = _get_media_root()
    subdir = _lesson_media_subdir(course_id, lesson_id)
    dest_dir = os.path.join(root, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    name = _sanitize_filename(suggested_name) if suggested_name else f'from_url_{slot_index}.pdf'
    if not name.lower().endswith('.pdf'):
        name = name + '.pdf'
    path = os.path.join(dest_dir, name)
    with open(path, 'wb') as f:
        f.write(content)
    media_url = (getattr(settings, 'MEDIA_URL', '/media/') or '/media/').rstrip('/')
    return (media_url + '/' + subdir.replace('\\', '/') + '/' + name).replace('\\', '/')


def get_pdf_page_count(file_path):
    """Возвращает количество страниц PDF."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError('Установите pypdf: pip install pypdf')
    try:
        with open(file_path, 'rb') as f:
            return len(PdfReader(f).pages)
    except Exception as e:
        raise ValueError(f'Не удалось прочитать PDF: {e}')


def get_pptx_slide_count(file_path):
    """Возвращает количество слайдов PowerPoint."""
    try:
        from pptx import Presentation
        return len(Presentation(file_path).slides)
    except Exception:
        return 1


def process_uploaded_course_file(uploaded_file, course_id):
    """
    Сохраняет загруженный файл, определяет тип (PDF/PPTX/DOCX) и возвращает список
    страниц контента: каждая страница/слайд = одно модальное окно.
    Возвращает: list of dicts с ключами content_type, file_path, page_number, title
    """
    if not uploaded_file or not uploaded_file.name:
        return []
    name_lower = uploaded_file.name.lower()
    file_url = _save_upload(uploaded_file, course_id)
    # физический путь для подсчёта страниц
    subdir = os.path.join('course_content', str(course_id))
    dest_dir = os.path.join(settings.MEDIA_ROOT, subdir)
    physical_path = os.path.join(dest_dir, _sanitize_filename(uploaded_file.name))
    base_title = os.path.splitext(os.path.basename(uploaded_file.name))[0][:50]

    if name_lower.endswith('.pdf'):
        n = get_pdf_page_count(physical_path)
        if n == 0:
            raise ValueError('В PDF не найдено ни одной страницы (пустой или повреждённый файл).')
        return [
            {
                'content_type': 'pdf_page',
                'file_path': file_url,
                'page_number': i + 1,
                'title': f'{base_title} — стр. {i + 1}',
            }
            for i in range(n)
        ]
    if name_lower.endswith('.pptx'):
        n = get_pptx_slide_count(physical_path)
        return [
            {
                'content_type': 'pptx_slide',
                'file_path': file_url,
                'page_number': i + 1,
                'title': f'{base_title} — слайд {i + 1}',
            }
            for i in range(n)
        ]
    if name_lower.endswith('.docx'):
        # Word — один документ = одно модальное окно (открыть файл)
        return [
            {
                'content_type': 'docx',
                'file_path': file_url,
                'page_number': 1,
                'title': base_title,
            }
        ]
    raise ValueError('Файл не распознан. Используйте PDF, PPTX или DOCX.')


def create_content_pages_from_upload(course, uploaded_file, start_sort_order):
    """
    Обрабатывает загруженный файл и создаёт записи CourseContentPage.
    Возвращает количество созданных страниц.
    """
    from .models import CourseContentPage
    items = process_uploaded_course_file(uploaded_file, course.id)
    for i, item in enumerate(items):
        CourseContentPage.objects.create(
            course=course,
            sort_order=start_sort_order + i,
            content_type=item['content_type'],
            file_path=item['file_path'],
            title=item.get('title'),
            page_number=item.get('page_number'),
        )
    return len(items)
