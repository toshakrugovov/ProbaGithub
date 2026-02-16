from django.shortcuts import render, get_object_or_404, redirect
import os
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash, logout
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Avg, F, Exists, OuterRef, Q, Count, Sum
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django import forms
from django.core.paginator import Paginator
from django.utils import timezone
from django.conf import settings
from decimal import Decimal, InvalidOperation
import json
from datetime import timedelta
from django.utils.safestring import mark_safe

from .models import (
    Role, UserProfile, UserAddress, Promotion, PromoUsage, UserSettings,
    CourseCategory, Course, CourseContentPage, CoursePurchase, CourseContentView, CourseSurvey, CourseReview, CourseFavorite,
    Lesson, LessonPage, LessonCompletion, UserNotification,
    Cart, CartItem, Order, OrderItem, Payment, Receipt, ReceiptItem, ReceiptConfig,
    SavedPaymentMethod, BalanceTransaction, CardTransaction, SupportTicket,
    ActivityLog, DatabaseBackup, OrganizationAccount, OrganizationTransaction,
    CourseRefundRequest,
)

import re

def _normalize_video_file_path(value):
    """Из вставленного кода iframe извлекает src (URL плеера). Иначе возвращает value как есть."""
    if not value or not isinstance(value, str):
        return value
    s = value.strip()
    if '<iframe' in s.lower() and 'src=' in s.lower():
        m = re.search(r'src\s*=\s*["\']([^"\']+)["\']', s, re.I)
        if m:
            return m.group(1).strip()
    return value


def _lesson_page_file_path(request, i, course_id, lesson_id, page_type):
    """
    Для страницы урока возвращает URL/путь к медиа.
    Изображение: page_i_image_file (файл) или page_i_file_path (URL).
    PDF: page_i_pdf_file (файл) или page_i_pdf_url (ссылка, в т.ч. Google Drive) или page_i_file_path.
    Видео: page_i_file_path.
    """
    import logging
    log = logging.getLogger(__name__)
    if page_type == 'image':
        uploaded = request.FILES.get(f'page_{i}_image_file') or request.FILES.get(f'page_{i}_file')
        if uploaded and uploaded.name:
            try:
                from main.course_content_upload import save_lesson_page_image
                return save_lesson_page_image(uploaded, course_id, lesson_id, i)
            except Exception as e:
                log.warning('Не удалось сохранить изображение страницы урока: %s', e)
        path = (request.POST.get(f'page_{i}_file_path') or '').strip() or None
        return path
    if page_type == 'pdf_page':
        uploaded = request.FILES.get(f'page_{i}_pdf_file') or request.FILES.get(f'page_{i}_file')
        if uploaded and uploaded.name:
            try:
                from main.course_content_upload import save_lesson_page_pdf_file
                return save_lesson_page_pdf_file(uploaded, course_id, lesson_id, i)
            except Exception as e:
                log.warning('Не удалось сохранить PDF страницы урока: %s', e)
        pdf_url = (request.POST.get(f'page_{i}_pdf_url') or '').strip() or None
        if pdf_url:
            try:
                from main.course_content_upload import download_pdf_from_url
                return download_pdf_from_url(pdf_url, course_id, lesson_id, i)
            except ValueError as e:
                log.warning('Не удалось загрузить PDF по ссылке: %s', e)
            except Exception as e:
                log.warning('Ошибка загрузки PDF по ссылке: %s', e)
        path = (request.POST.get(f'page_{i}_file_path') or '').strip() or None
        return path
    # video или fallback
    path = (request.POST.get(f'page_{i}_file_path') or '').strip() or None
    if path and page_type == 'video':
        path = _normalize_video_file_path(path) or path
    return path

# =================== Форма для профиля (3НФ: full_name не в модели — пишем в user) ===================
class UserProfileForm(forms.ModelForm):
    full_name = forms.CharField(max_length=255, required=False, label='ФИО')

    class Meta:
        model = UserProfile
        fields = ['phone_number', 'birth_date', 'secret_word']
        widgets = {
            'secret_word': forms.TextInput(attrs={'type': 'password', 'placeholder': 'Введите секретное слово'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user_id:
            self.fields['full_name'].initial = self.instance.full_name

    def save(self, commit=True):
        profile = super().save(commit=commit)
        fn = (self.cleaned_data.get('full_name') or '').strip()
        if fn and profile.user_id:
            parts = fn.split(None, 1)
            profile.user.first_name = parts[0]
            profile.user.last_name = parts[1] if len(parts) > 1 else ''
            if commit:
                profile.user.save()
        return profile

# =================== Главная страница ===================
def handler404(request, exception=None):
    """Кастомная обработка ошибки 404"""
    from django.shortcuts import render
    return render(request, '404.html', status=404)

def favicon_view(request):
    """Простейшая заглушка для /favicon.ico, чтобы не сыпались 500-ошибки."""
    from django.http import HttpResponse
    return HttpResponse(b'', content_type='image/x-icon', status=200)

def handler500(request, *args, **kwargs):
    """
    Кастомная обработка ошибки 500.
    Всегда показывает кастомную страницу, даже в DEBUG режиме.
    """
    from django.shortcuts import render
    from django.db import connection
    from django.http import HttpResponse
    
    # Проверяем, доступна ли база данных
    db_available = False
    try:
        connection.ensure_connection()
        db_available = True
    except Exception:
        db_available = False
    
    if not db_available:
        # База данных недоступна - показываем страницу восстановления
        try:
            return render(request, '500_restore.html', status=500)
        except Exception:
            # Если даже шаблон не работает, возвращаем простой HTML
            try:
                return HttpResponse(get_restore_html(), content_type='text/html', status=500)
            except Exception:
                # Если даже get_restore_html не работает, возвращаем простой HTML
                return HttpResponse(
                    '<html><body><h1>Ошибка 500</h1><p>База данных недоступна. <a href="/admin-secret-check/">Восстановить</a></p></body></html>',
                    content_type='text/html',
                    status=500
                )
    
    # Если БД доступна, показываем обычную страницу ошибки 500
    try:
        return render(request, '500.html', status=500)
    except Exception:
        # Если даже рендеринг не работает, возвращаем простой HTML
        return HttpResponse(
            '<html><body><h1>Ошибка 500</h1><p>Произошла внутренняя ошибка сервера.</p><p><a href="/">Вернуться на главную</a></p></body></html>',
            content_type='text/html',
            status=500
        )

def _get_admin_restore_secret():
    """Получает секретное слово напрямую из файла settings.py (без кэша Django)"""
    try:
        from django.conf import settings
        from pathlib import Path
        import re
        
        settings_file = Path(settings.BASE_DIR) / 'mptcourse' / 'settings.py'
        
        if settings_file.exists():
            with open(settings_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Ищем значение ADMIN_RESTORE_SECRET в файле
            pattern = r"ADMIN_RESTORE_SECRET\s*=\s*os\.environ\.get\('ADMIN_RESTORE_SECRET',\s*'([^']*)'\)"
            match = re.search(pattern, content)
            if match:
                return match.group(1)
        
        # Если не найдено в файле, пробуем из settings (кэш)
        return getattr(settings, 'ADMIN_RESTORE_SECRET', 'RUYAZHOP')
    except Exception:
        # В случае ошибки используем значение по умолчанию
        try:
            from django.conf import settings
            return getattr(settings, 'ADMIN_RESTORE_SECRET', 'RUYAZHOP')
        except:
            return 'RUYAZHOP'

@csrf_exempt
def admin_secret_check(request):
    """Проверка секретного слова администратора для доступа к восстановлению"""
    try:
        if request.method == 'POST':
            secret_word = request.POST.get('secret_word', '').strip()
            
            # Получаем секретное слово напрямую из файла settings.py (без кэша Django)
            # Это позволяет менять его без перезапуска сервера
            correct_secret = _get_admin_restore_secret()
            
            if secret_word == correct_secret:
                # Сохраняем в cookie, что администратор прошел проверку (работает без БД)
                from django.http import HttpResponse
                response = JsonResponse({'success': True, 'redirect': '/emergency-restore/'})
                # Устанавливаем cookie на 1 час
                response.set_cookie('admin_restore_access', 'true', max_age=3600, httponly=True, samesite='Lax')
                return response
            else:
                return JsonResponse({'success': False, 'error': 'Неверное секретное слово'}, status=400)
        
        # GET запрос - показываем форму ввода секретного слова
        # Используем простой HTML без шаблонов (работает без БД)
        from django.http import HttpResponse
        return HttpResponse(get_secret_check_html(), content_type='text/html')
    except Exception as e:
        # Если что-то пошло не так, возвращаем простой HTML
        from django.http import HttpResponse
        return HttpResponse(get_secret_check_html(), content_type='text/html')

def get_secret_check_html():
    """Возвращает HTML для страницы проверки секретного слова (без использования шаблонов)"""
    return '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Проверка доступа - MPTCOURSE</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background: #ffffff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: #1a1a1a;
        }
        .dark-theme { background: #0f0f10; color: #e6e6e6; }
        .container {
            background: #ffffff;
            border: 1px solid #eaeaea;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            max-width: 500px;
            width: 100%;
            padding: 40px;
            text-align: center;
        }
        .dark-theme .container { background: #151519; border-color: #1c1c21; }
        .icon { font-size: 48px; margin-bottom: 20px; }
        .title { font-size: 28px; font-weight: 700; margin-bottom: 16px; }
        .message { font-size: 14px; margin-bottom: 30px; color: #666666; }
        .dark-theme .message { color: #9a9aa0; }
        .form-group { margin-bottom: 24px; text-align: left; }
        .form-group label { display: block; font-weight: 600; margin-bottom: 8px; font-size: 14px; }
        .form-group input {
            width: 100%;
            padding: 12px;
            border: 1px solid #eaeaea;
            border-radius: 8px;
            font-size: 16px;
            background: #ffffff;
            color: #1a1a1a;
            font-family: inherit;
        }
        .dark-theme .form-group input { background: #0f0f10; border-color: #1c1c21; color: #e6e6e6; }
        .submit-button {
            width: 100%;
            padding: 16px;
            background: #000000;
            color: #ffffff;
            border: 1px solid #000000;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 20px;
        }
        .dark-theme .submit-button { background: #ffffff; color: #000000; border-color: #ffffff; }
        .error-message {
            background: #f8d7da;
            color: #721c24;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 20px;
            display: none;
            text-align: left;
            font-size: 14px;
        }
        .back-link {
            display: inline-block;
            margin-top: 16px;
            color: #666666;
            text-decoration: none;
            font-size: 14px;
        }
        .dark-theme .back-link { color: #9a9aa0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🔐</div>
        <h1 class="title">Проверка доступа</h1>
        <p class="message">Для доступа к восстановлению базы данных введите секретное слово администратора.</p>
        <div class="error-message" id="errorMessage"></div>
        <form id="secretForm">
            <div class="form-group">
                <label for="secret_word">Секретное слово</label>
                <input type="password" id="secret_word" name="secret_word" placeholder="Введите секретное слово" required autofocus>
            </div>
            <button type="submit" class="submit-button">Проверить</button>
        </form>
        <a href="/" class="back-link">← Вернуться на главную</a>
    </div>
    <script>
        document.getElementById('secretForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            var secretWord = document.getElementById('secret_word').value.trim();
            var errorMsg = document.getElementById('errorMessage');
            var submitBtn = e.target.querySelector('button[type="submit"]');
            
            if (!secretWord) {
                errorMsg.textContent = '❌ Пожалуйста, введите секретное слово';
                errorMsg.style.display = 'block';
                return;
            }
            
            submitBtn.disabled = true;
            submitBtn.textContent = 'Проверка...';
            errorMsg.style.display = 'none';
            
            try {
                var formData = new FormData();
                formData.append('secret_word', secretWord);
                var response = await fetch('/admin-secret-check/', { method: 'POST', body: formData });
                var data = await response.json();
                
                if (data.success) {
                    window.location.href = data.redirect || '/emergency-restore/';
                } else {
                    errorMsg.textContent = '❌ ' + (data.error || 'Неверное секретное слово');
                    errorMsg.style.display = 'block';
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Проверить';
                }
            } catch (error) {
                errorMsg.textContent = '❌ Ошибка соединения: ' + error.message;
                errorMsg.style.display = 'block';
                submitBtn.disabled = false;
                submitBtn.textContent = 'Проверить';
            }
        });
    </script>
    </body>
</html>'''

def get_restore_html():
    """Возвращает HTML для страницы восстановления БД (без использования шаблонов)"""
    return '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Восстановление базы данных - MPTCOURSE</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background: #ffffff;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: #1a1a1a;
        }
        .dark-theme { background: #0f0f10; color: #e6e6e6; }
        .container {
            background: #ffffff;
            border: 1px solid #eaeaea;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            max-width: 600px;
            width: 100%;
            padding: 40px;
            text-align: center;
        }
        .dark-theme .container { background: #151519; border-color: #1c1c21; }
        .icon { font-size: 64px; margin-bottom: 20px; }
        .title { font-size: 32px; font-weight: 700; margin-bottom: 16px; }
        .message { font-size: 16px; margin-bottom: 30px; color: #666666; line-height: 1.6; }
        .dark-theme .message { color: #9a9aa0; }
        .info-box {
            background: #f8f9fa;
            border: 1px solid #eaeaea;
            padding: 16px;
            border-radius: 8px;
            margin-bottom: 24px;
            text-align: left;
            font-size: 14px;
            line-height: 1.6;
        }
        .dark-theme .info-box { background: #1c1c21; border-color: #2a2a31; }
        .info-box strong { display: block; margin-bottom: 8px; font-size: 16px; }
        .info-box ul { margin: 8px 0 0 20px; padding: 0; }
        .form-group { margin-bottom: 24px; text-align: left; }
        .form-group label { display: block; font-weight: 600; margin-bottom: 8px; font-size: 14px; }
        .file-input-wrapper { position: relative; width: 100%; }
        .file-input { display: none; }
        .file-input-label {
            display: block;
            padding: 20px;
            border: 2px dashed #eaeaea;
            border-radius: 8px;
            background: #f8f9fa;
            cursor: pointer;
            text-align: center;
        }
        .dark-theme .file-input-label { background: #1c1c21; border-color: #2a2a31; }
        .file-input-label:hover { border-color: #1a1a1a; }
        .file-input-label.has-file { border-color: #28a745; background: rgba(40,167,69,0.1); }
        .file-name { margin-top: 12px; font-size: 14px; color: #28a745; font-weight: 500; text-align: center; }
        .submit-button {
            width: 100%;
            padding: 16px;
            background: #000000;
            color: #ffffff;
            border: 1px solid #000000;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 20px;
        }
        .dark-theme .submit-button { background: #ffffff; color: #000000; border-color: #ffffff; }
        .submit-button:disabled { opacity: 0.6; cursor: not-allowed; }
        .error-message, .success-message {
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 20px;
            display: none;
            text-align: left;
            font-size: 14px;
        }
        .error-message { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .success-message { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .loading { display: none; margin-top: 20px; text-align: center; }
        .loading-spinner {
            border: 3px solid #eaeaea;
            border-top: 3px solid #1a1a1a;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🔧</div>
        <h1 class="title">База данных не найдена</h1>
        <p class="message">Произошла ошибка: база данных была удалена или повреждена. Для восстановления работы сайта загрузите файл бэкапа базы данных.</p>
        <div class="info-box">
            <strong>ℹ️ Информация:</strong>
            <ul>
                <li>Загрузите файл бэкапа базы данных (любой формат)</li>
                <li>Файл должен быть создан через систему бэкапов сайта</li>
                <li>После восстановления необходимо перезапустить сервер</li>
            </ul>
        </div>
        <div class="error-message" id="errorMessage"></div>
        <div class="success-message" id="successMessage"></div>
        <form id="restoreForm" enctype="multipart/form-data">
            <div class="form-group">
                <label for="backup_file">Выберите файл бэкапа</label>
                <div class="file-input-wrapper">
                    <input type="file" id="backup_file" name="backup_file" class="file-input" accept=".sqlite3,.db,.bak,.sqlite,*" required>
                    <label for="backup_file" class="file-input-label" id="fileLabel">📁 Нажмите для выбора файла или перетащите файл сюда</label>
                    <div class="file-name" id="fileName" style="display: none;"></div>
                </div>
            </div>
            <button type="submit" class="submit-button" id="restoreButton">🔄 Восстановить базу данных</button>
        </form>
        <div class="loading" id="loading">
            <div class="loading-spinner"></div>
            <p style="margin-top: 16px; color: #666666;">Восстановление базы данных...</p>
        </div>
    </div>
    <script>
        var form = document.getElementById('restoreForm');
        var fileInput = document.getElementById('backup_file');
        var fileLabel = document.getElementById('fileLabel');
        var fileName = document.getElementById('fileName');
        var restoreButton = document.getElementById('restoreButton');
        var errorMessage = document.getElementById('errorMessage');
        var successMessage = document.getElementById('successMessage');
        var loading = document.getElementById('loading');
        
        fileInput.addEventListener('change', function(e) {
            var file = e.target.files[0];
            if (file) {
                // Принимаем любые файлы бэкапов
                fileLabel.textContent = '✓ Файл выбран';
                fileLabel.classList.add('has-file');
                fileName.textContent = file.name;
                fileName.style.display = 'block';
                hideError();
            }
        });
        
        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            var file = fileInput.files[0];
            if (!file) {
                showError('Пожалуйста, выберите файл бэкапа');
                return;
            }
            // Принимаем любые файлы бэкапов
            restoreButton.disabled = true;
            loading.style.display = 'block';
            form.style.display = 'none';
            hideError();
            hideSuccess();
            var formData = new FormData();
            formData.append('backup_file', file);
            try {
                var response = await fetch('/emergency-restore/', { method: 'POST', body: formData });
                var data = await response.json();
                if (data.success) {
                    showSuccess(data.message || 'База данных успешно восстановлена!');
                    // Перенаправляем на главную страницу через 1 секунду
                    setTimeout(function() {
                        window.location.href = data.redirect || '/';
                    }, 1000);
                } else {
                    showError(data.error || 'Ошибка при восстановлении базы данных');
                    form.style.display = 'block';
                    restoreButton.disabled = false;
                }
            } catch (error) {
                showError('Ошибка соединения: ' + error.message);
                form.style.display = 'block';
                restoreButton.disabled = false;
            } finally {
                loading.style.display = 'none';
            }
        });
        function showError(msg) {
            errorMessage.textContent = '❌ ' + msg;
            errorMessage.style.display = 'block';
            successMessage.style.display = 'none';
        }
        function hideError() { errorMessage.style.display = 'none'; }
        function showSuccess(msg) {
            successMessage.textContent = '✅ ' + msg;
            successMessage.style.display = 'block';
            errorMessage.style.display = 'none';
        }
        function hideSuccess() { successMessage.style.display = 'none'; }
    </script>
</body>
</html>'''

@csrf_exempt
def emergency_restore(request):
    """
    Экстренное восстановление БД из загруженного файла (работает без подключения к БД)
    ВАЖНО: POST запросы всегда возвращают JSON, GET запросы возвращают HTML
    """
    from django.conf import settings
    import shutil
    import os
    import time
    from django.http import JsonResponse, HttpResponse
    from django.utils import timezone
    
    # Проверяем доступ администратора через cookie (работает без БД)
    if request.COOKIES.get('admin_restore_access') != 'true':
        # Если нет доступа и это POST запрос, возвращаем JSON ошибку
        if request.method == 'POST':
            response = JsonResponse({
                'success': False,
                'error': 'Доступ запрещен. Пожалуйста, сначала введите секретное слово.'
            }, status=403)
            response['Content-Type'] = 'application/json'
            return response
        # Если это GET запрос, показываем страницу проверки секретного слова
        return HttpResponse(get_secret_check_html(), content_type='text/html')
    
    # ОБРАБОТКА POST ЗАПРОСОВ - ВСЕГДА ВОЗВРАЩАЕМ JSON
    if request.method == 'POST':
        try:
            # Проверяем наличие загруженного файла
            if 'backup_file' not in request.FILES:
                response = JsonResponse({'success': False, 'error': 'Файл бэкапа не загружен'}, status=400)
                response['Content-Type'] = 'application/json'
                return response
            
            uploaded_file = request.FILES['backup_file']
            
            # Определяем тип БД
            db_config = settings.DATABASES['default']
            engine = db_config.get('ENGINE', '')
            
            # Закрываем все соединения с БД (если они есть)
            try:
                from django.db import connections
                for conn in connections.all():
                    conn.close()
            except:
                pass
            
            if 'sqlite' in engine:
                # Для SQLite просто копируем файл
                db_path = db_config['NAME']
                from pathlib import Path as PathLib
                if isinstance(db_path, PathLib):
                    db_path = str(db_path)
                elif not isinstance(db_path, str):
                    db_path = str(db_path)
                
                # Создаем резервную копию текущей БД перед восстановлением (если она существует)
                if os.path.exists(db_path):
                    backup_current_path = f"{db_path}.before_emergency_restore_{int(timezone.now().timestamp())}"
                    try:
                        shutil.copy2(db_path, backup_current_path)
                    except:
                        pass
                
                # Сохраняем загруженный файл как новую БД
                with open(db_path, 'wb+') as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)
            
            elif 'postgresql' in engine:
                # Для PostgreSQL используем psql для восстановления SQL дампа
                import tempfile
                import subprocess
                
                # Сохраняем загруженный файл во временный файл
                with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.sql') as tmp_file:
                    for chunk in uploaded_file.chunks():
                        tmp_file.write(chunk)
                    tmp_file_path = tmp_file.name
                
                try:
                    # Получаем параметры подключения
                    db_name = db_config['NAME']
                    db_user = db_config.get('USER', 'postgres')
                    db_password = db_config.get('PASSWORD', '')
                    db_host = db_config.get('HOST', 'localhost')
                    db_port = db_config.get('PORT', '5432')
                    
                    # Устанавливаем переменную окружения для пароля
                    env = os.environ.copy()
                    if db_password:
                        env['PGPASSWORD'] = db_password
                    
                    # Проверяем, есть ли таблицы в БД (если БД пустая, применяем миграции)
                    try:
                        from django.db import connection
                        with connection.cursor() as cursor:
                            cursor.execute("""
                                SELECT EXISTS (
                                    SELECT FROM information_schema.tables 
                                    WHERE table_schema = 'public' 
                                    AND table_name = 'django_migrations'
                                );
                            """)
                            has_tables = cursor.fetchone()[0]
                        
                        if not has_tables:
                            # БД пустая, применяем миграции перед восстановлением
                            from django.core.management import call_command
                            call_command('migrate', verbosity=0, interactive=False)
                    except Exception as migrate_error:
                        # Если не удалось проверить или применить миграции, продолжаем восстановление
                        # Возможно, в дампе есть структура
                        pass
                    
                    # Формируем команду psql
                    cmd = ['psql']
                    if db_host:
                        cmd.extend(['-h', db_host])
                    if db_port:
                        cmd.extend(['-p', str(db_port)])
                    if db_user:
                        cmd.extend(['-U', db_user])
                    cmd.extend(['-d', db_name, '-f', tmp_file_path])
                    
                    # Восстанавливаем дамп
                    result = subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env=env
                    )
                    
                    if result.returncode != 0:
                        # Если ошибка про отсутствие таблиц, пробуем применить миграции и восстановить снова
                        if 'не существует' in result.stderr or 'does not exist' in result.stderr.lower():
                            try:
                                from django.core.management import call_command
                                call_command('migrate', verbosity=0, interactive=False)
                                # Пробуем восстановить снова
                                result = subprocess.run(
                                    cmd,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    text=True,
                                    env=env
                                )
                            except:
                                pass
                        
                        if result.returncode != 0:
                            raise Exception(f'Ошибка при восстановлении: {result.stderr}')
                
                finally:
                    # Удаляем временный файл
                    try:
                        os.unlink(tmp_file_path)
                    except:
                        pass
            
            else:
                response = JsonResponse({
                    'success': False,
                    'error': f'Неподдерживаемый тип БД: {engine}'
                }, status=400)
                response['Content-Type'] = 'application/json'
                return response
            
            # Инициализируем обязательные записи после восстановления
            from main.utils import initialize_required_records
            initialize_required_records()
            
            # Очищаем cookie после успешного восстановления и перенаправляем на главную
            response = JsonResponse({
                'success': True,
                'message': 'База данных успешно восстановлена!',
                'redirect': '/'
            })
            response['Content-Type'] = 'application/json'
            response.delete_cookie('admin_restore_access')
            return response
        except Exception as e:
            # ВАЖНО: всегда возвращаем JSON для POST запросов
            import traceback
            error_details = str(e)
            # Логируем полную ошибку для отладки
            try:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f'Ошибка при восстановлении БД: {error_details}\n{traceback.format_exc()}')
            except:
                pass
            
            response = JsonResponse({
                'success': False,
                'error': f'Ошибка при восстановлении БД: {error_details}'
            }, status=500)
            response['Content-Type'] = 'application/json'
            return response
    
    # GET запрос - показываем форму восстановления
    # Используем простой HTML без шаблонов (работает без БД)
    try:
        # Пытаемся использовать шаблон, если БД доступна
        from django.shortcuts import render
        from django.http import HttpResponse
        return render(request, '500_restore.html')
    except Exception:
        # Если шаблон не работает (БД недоступна), используем простой HTML
        return HttpResponse(get_restore_html(), content_type='text/html')


def _serialize_course_images(course):
    """Курсы: одна обложка (cover_image_path). Для API при необходимости."""
    if not course or not getattr(course, 'cover_image_path', None):
        return []
    return [{'url': course.cover_image_path, 'is_primary': True}]

def home(request):
    base_query = Course.objects.filter(is_available=True)
    new_courses = base_query.order_by('-added_at')[:12]
    popular_courses = base_query.order_by('-added_at')[:12]
    promotions = Promotion.objects.filter(is_active=True).order_by('-start_date')[:5]
    categories = CourseCategory.objects.all()[:10]

    return render(request, 'home.html', {
        'new_products': new_courses,
        'popular_products': popular_courses,
        'promotions': promotions,
        'tags': [],
        'categories': categories
    })

# =================== Авторизация и регистрация ===================
def login_view(request):
    # Очищаем все сообщения, которые не относятся к странице входа
    # Оставляем только сообщения об ошибках блокировки
    storage = messages.get_messages(request)
    messages_to_keep = []
    for message in storage:
        msg_text = str(message).lower()
        # Оставляем только сообщения о блокировке аккаунта
        if 'заблокирован' in msg_text or 'https://t.me/toshaplenka' in str(message):
            messages_to_keep.append(str(message))
    # Очищаем все сообщения (включая success messages типа "Пользователь обновлен")
    storage.used = True
    # Добавляем обратно только нужные сообщения об ошибках
    for msg in messages_to_keep:
        messages.error(request, msg)
    return render(request, 'login.html')

def register_view(request):
    return render(request, 'register.html')

# =================== Информационные страницы ===================
def contacts(request):
    return render(request, 'contacts.html')

def refund(request):
    return render(request, 'refund.html')

def bonus(request):
    return render(request, 'bonus.html')

def delivery(request):
    return render(request, 'delivery.html')

def about(request):
    return render(request, 'about.html')

def brand_book(request):
    return render(request, 'brand_book.html')

# =================== Каталог (курсы) — данные через API, view только рендер ===================
def catalog(request):
    categories = CourseCategory.objects.all().order_by('category_name')
    # Товары загружаются на клиенте через GET /api/catalog/
    return render(request, 'catalog.html', {
        'categories': categories,
        'brands': [],
        'tags': [],
    })

# =================== Избранное (курсы) ===================
def favorites(request):
    if not request.user.is_authenticated:
        return redirect('login')
    favorites = CourseFavorite.objects.filter(user=request.user).select_related('course', 'course__category')
    return render(request, 'favorites.html', {'favorites': favorites})

@login_required
@require_POST
def add_to_favorites(request):
    data = json.loads(request.body)
    product_id = data.get('product') or data.get('course_id')
    try:
        course = Course.objects.get(id=product_id)
        CourseFavorite.objects.get_or_create(user=request.user, course=course)
        return JsonResponse({'status': 'ok'})
    except Course.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Продукт не найден'}, status=404)

@login_required
@require_POST
def remove_from_favorites(request, product_id):
    course = get_object_or_404(Course, id=product_id)
    CourseFavorite.objects.filter(user=request.user, course=course).delete()
    return JsonResponse({'status': 'ok'})

def check_product_status(request, product_id):
    """Проверяет, находится ли курс в избранном, в корзине и куплен ли уже."""
    product = get_object_or_404(Course, id=product_id)
    
    if not request.user.is_authenticated:
        return JsonResponse({
            'is_favorite': False,
            'is_in_cart': False,
            'is_purchased': False,
        })
    
    is_favorite = CourseFavorite.objects.filter(user=request.user, course=product).exists()
    cart, _ = Cart.objects.get_or_create(user=request.user)
    is_in_cart = CartItem.objects.filter(cart=cart, course=product).exists()
    is_purchased = CoursePurchase.objects.filter(user=request.user, course=product, status='paid').exists()
    
    return JsonResponse({
        'is_favorite': is_favorite,
        'is_in_cart': is_in_cart,
        'is_purchased': is_purchased,
    })

@login_required
@require_POST
def remove_from_cart_by_product(request, product_id):
    """Удаляет курс из корзины по course_id"""
    course = get_object_or_404(Course, id=product_id)
    cart, _ = Cart.objects.get_or_create(user=request.user)
    CartItem.objects.filter(cart=cart, course=course).delete()
    return JsonResponse({'success': True, 'cart_count': cart.items.count()})

def cart_view(request):
    """Корзина загружается на клиенте через GET /api/cart/"""
    return render(request, 'cart.html', {})


from django.http import JsonResponse
from .models import CartItem, Cart

# =================== Профиль пользователя ===================
@login_required
def profile_view(request):
    # Получаем профиль или создаем, чтобы существовал объект UserProfile
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    
    # Формируем full_name из встроенного пользователя
    full_name = f"{request.user.first_name} {request.user.last_name}".strip()
    role_name = ''
    if profile.role and profile.role.role_name:
        role_name = profile.role.role_name.strip().lower()
    # Нормализованные роли: ADMIN / MANAGER / USER
    show_admin_panel = request.user.is_superuser or role_name.upper() == 'ADMIN'
    show_manager_panel = request.user.is_superuser or role_name in ('manager', 'менеджер')

    orders = Order.objects.filter(user=request.user).order_by('-created_at')[:5]

    # Собираем уведомления для профиля: из БД (UserNotification) + заказы, возвраты, промо
    notifications = []
    try:
        for n in UserNotification.objects.filter(user=request.user).order_by('-created_at')[:15]:
            notifications.append({
                'id': f'notif-{n.id}',
                'type': 'admin_comment',
                'text': n.message,
                'url': '',
            })
        # 1) Изменение статуса заказов (последние)
        recent_orders = Order.objects.filter(user=request.user).order_by('-updated_at' if hasattr(Order, 'updated_at') else '-created_at')[:10]
        for o in recent_orders:
            status_label = {
                'processing': 'В обработке',
                'paid': 'Оплачен',
                'shipped': 'Отправлен',
                'delivered': 'Доставлен',
                'cancelled': 'Отменен',
            }.get(o.order_status, o.order_status)
            notifications.append({
                'id': f'order-status-{o.id}',
                'type': 'order',
                'text': f'Статус вашего заказа #{o.id} изменился: {status_label}',
                'url': request.build_absolute_uri(
                    request.path.replace('profile/', f'profile/orders/{o.id}/')
                ) if 'profile/' in request.path else '',
            })
        # 2) Возвраты на баланс
        refunds = BalanceTransaction.objects.filter(user=request.user, transaction_type='order_refund').order_by('-created_at')[:5]
        for r in refunds:
            order_id = r.order_id if hasattr(r, 'order_id') else (r.order.id if getattr(r, 'order', None) else '')
            notifications.append({
                'id': f'refund-{r.id}',
                'type': 'refund',
                'text': f'Вам возвращены деньги {r.amount} ₽ за заказ #{order_id}',
                'url': '',
            })
        # 3) Новые активные промокоды (последние активированные по дате начала)
        from django.utils import timezone
        today = timezone.now().date()
        promos = Promotion.objects.filter(is_active=True).order_by('-start_date')[:5]
        for p in promos:
            # Показываем только относительно свежие промо (за последние 30 дней)
            if not p.start_date or (today - p.start_date).days <= 30:
                notifications.append({
                    'id': f'promo-{p.id}',
                    'type': 'promo',
                    'text': f'Новый промокод: {p.promo_code} — скидка {p.discount}%',
                    'url': '',
                })
    except Exception:
        # Если что-то пошло не так, просто не показываем уведомления
        notifications = []

    return render(request, 'profile/profile.html', {
        'profile': profile,
        'full_name': full_name,
        'orders': orders,
        'notifications': notifications[:8],  # ограничим количество
        'show_admin_panel': show_admin_panel,
        'show_manager_panel': show_manager_panel,
        'role_name': role_name,
    })

@login_required
def notifications_view(request):
    """Страница уведомлений: из БД (UserNotification) и при необходимости объединение с localStorage на клиенте."""
    db_notifications = list(
        UserNotification.objects.filter(user=request.user).order_by('-created_at')[:100]
    )
    return render(request, 'profile/notifications.html', {
        'notifications': db_notifications,
    })


@login_required
def edit_profile(request):
    user = request.user

    # Получаем существующий профиль, не создаём новый автоматически
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile(user=user)  # создаём только если реально нет

    if request.method == 'POST':
        # Определяем, это JSON-запрос (AJAX) или обычная форма
        is_json = request.headers.get('Content-Type', '').startswith('application/json')
        if is_json:
            try:
                payload = json.loads(request.body.decode('utf-8') or '{}')
                first_name = str(payload.get('first_name', '')).strip()
                last_name = str(payload.get('last_name', '')).strip()
                phone_number = str(payload.get('phone_number', '')).strip()
                birth_date_str = str(payload.get('birth_date', '')).strip()
                secret_word = str(payload.get('secret_word', '')).strip()
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'error': 'Некорректный формат данных'}, status=400)
        else:
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            phone_number = request.POST.get('phone_number', '').strip()
            birth_date_str = request.POST.get('birth_date', '').strip()  # YYYY-MM-DD
            secret_word = request.POST.get('secret_word', '').strip()

        # Валидация
        if not first_name or not last_name:
            if is_json:
                return JsonResponse({'success': False, 'error': 'Имя и Фамилия обязательны'}, status=400)
            messages.error(request, 'Имя и Фамилия обязательны.')
        else:
            # Обновляем User
            user.first_name = first_name
            user.last_name = last_name
            user.save()

            # Обновляем профиль
            profile.phone_number = phone_number
            if birth_date_str:
                try:
                    from datetime import datetime as _dt
                    profile.birth_date = _dt.strptime(birth_date_str, '%Y-%m-%d').date()
                except ValueError:
                    if is_json:
                        return JsonResponse({'success': False, 'error': 'Неверный формат даты рождения. Используйте ГГГГ-ММ-ДД.'}, status=400)
                    messages.error(request, 'Неверный формат даты рождения. Используйте ГГГГ-ММ-ДД.')
            # Обновляем секретное слово только если оно указано
            if secret_word:
                profile.secret_word = secret_word
            profile.save()

            if is_json:
                return JsonResponse({'success': True})
            messages.success(request, 'Профиль успешно обновлён!')
            return redirect('profile')

    # Контекст для шаблона
    context = {
        'user': user,
        'profile': profile,  # подтягиваем существующие значения
    }

    return render(request, 'edit_profile.html', context)

@login_required
def delete_account(request):
    if request.method == "POST":
        user = request.user
        logout(request)
        user.delete()
        messages.success(request, "Ваш аккаунт удален.")
        return redirect('home')
    return redirect('profile')

# =================== Мои курсы ===================
def _purchase_has_pending_refund(purchase):
    """Заявление на возврат по этой покупке подано и на рассмотрении — курс недоступен."""
    return CourseRefundRequest.objects.filter(
        course_purchase=purchase, status='pending'
    ).exists()


@login_required
def my_courses_view(request):
    purchases = CoursePurchase.objects.filter(
        user=request.user, status='paid'
    ).select_related('course', 'course__category').order_by('-id')
    pending_refund_ids = set(
        CourseRefundRequest.objects.filter(
            course_purchase__user=request.user, status='pending'
        ).values_list('course_purchase_id', flat=True)
    )
    actual = [p for p in purchases if p.completed_at is None and p.id not in pending_refund_ids]
    refund_pending = [p for p in purchases if p.completed_at is None and p.id in pending_refund_ids]
    archived = [p for p in purchases if p.completed_at is not None]
    return render(request, 'profile/my_courses.html', {
        'actual': actual,
        'refund_pending': refund_pending,
        'archived': archived,
    })


@login_required
def course_view(request, purchase_id):
    """Вход в курс: если есть уроки (новая структура) — список уроков; иначе старый контент по модалкам."""
    purchase = get_object_or_404(
        CoursePurchase,
        id=purchase_id,
        user=request.user,
        status='paid',
    )
    if _purchase_has_pending_refund(purchase):
        messages.warning(request, 'Заявление на возврат по этому курсу уже подано и находится на рассмотрении. Курс недоступен.')
        return redirect('my_courses')
    course = purchase.course
    if course.lessons.exists():
        return redirect('course_lessons_list', purchase_id=purchase_id)
    content_pages = list(course.content_pages.order_by('sort_order'))
    viewed_page_ids = set(
        purchase.content_views.values_list('content_page_id', flat=True)
    )
    has_survey = purchase.has_survey()
    has_review = purchase.has_review()
    all_viewed = purchase.all_content_viewed()
    can_archive = purchase.can_mark_archived()
    return render(request, 'profile/course_view.html', {
        'purchase': purchase,
        'course': course,
        'content_pages': content_pages,
        'viewed_page_ids': viewed_page_ids,
        'has_survey': has_survey,
        'has_review': has_review,
        'all_viewed': all_viewed,
        'can_archive': can_archive,
    })


@login_required
def course_lessons_list(request, purchase_id):
    """Список уроков курса (новая логика: как GetCourse)."""
    purchase = get_object_or_404(
        CoursePurchase,
        id=purchase_id,
        user=request.user,
        status='paid',
    )
    if _purchase_has_pending_refund(purchase):
        messages.warning(request, 'Заявление на возврат по этому курсу уже подано и находится на рассмотрении. Курс недоступен.')
        return redirect('my_courses')
    course = purchase.course
    lessons = list(course.lessons.prefetch_related('pages').order_by('sort_order', 'id'))
    completed_lesson_ids = set(
        purchase.lesson_completions.values_list('lesson_id', flat=True)
    )
    all_lessons_completed = len(lessons) > 0 and completed_lesson_ids >= {l.id for l in lessons}
    has_review = purchase.has_review()
    # Возврат: можно подать заявление только если ни один урок не пройден
    has_any_lesson_completed = len(completed_lesson_ids) > 0
    has_pending_refund = CourseRefundRequest.objects.filter(
        course_purchase=purchase, status='pending'
    ).exists()
    can_request_refund = not has_any_lesson_completed and not has_pending_refund
    return render(request, 'profile/course_lessons_list.html', {
        'purchase': purchase,
        'course': course,
        'lessons': lessons,
        'completed_lesson_ids': completed_lesson_ids,
        'all_lessons_completed': all_lessons_completed,
        'has_review': has_review,
        'can_request_refund': can_request_refund,
        'has_pending_refund': has_pending_refund,
    })


@login_required
def lesson_view(request, purchase_id, lesson_id):
    """Просмотр урока: страницы (до 10), навигация, кнопка «Я усвоил»."""
    purchase = get_object_or_404(
        CoursePurchase,
        id=purchase_id,
        user=request.user,
        status='paid',
    )
    if _purchase_has_pending_refund(purchase):
        messages.warning(request, 'Заявление на возврат по этому курсу уже подано и находится на рассмотрении. Курс недоступен.')
        return redirect('my_courses')
    lesson = get_object_or_404(Lesson, id=lesson_id, course=purchase.course)
    all_pages = list(lesson.pages.order_by('sort_order', 'id'))
    pages = [p for p in all_pages if (p.file_path or '').strip() or (p.text or '').strip()]
    is_completed = purchase.lesson_completions.filter(lesson=lesson).exists()
    return render(request, 'profile/lesson_view.html', {
        'purchase': purchase,
        'course': purchase.course,
        'lesson': lesson,
        'pages': pages,
        'is_completed': is_completed,
    })


@login_required
def serve_course_media(request, purchase_id):
    """
    Раздаёт файлы курса/урока (PDF, картинки) с проверкой доступа.
    GET ?path=lesson_pages/<course_id>/<lesson_id>/file.pdf или path=course_content/<course_id>/file.pdf
    Не бросает необработанных исключений — при ошибке возвращает 403/404.
    """
    from django.http import FileResponse, HttpResponseForbidden, Http404
    try:
        purchase = get_object_or_404(
            CoursePurchase,
            id=purchase_id,
            user=request.user,
            status='paid',
        )
        if _purchase_has_pending_refund(purchase):
            return HttpResponseForbidden('Курс недоступен: заявление на возврат на рассмотрении.')
        rel = (request.GET.get('path') or '').strip()
        if not rel or '..' in rel:
            return HttpResponseForbidden('Неверный путь')
        rel = rel.lstrip('/')
        media_prefix = (getattr(settings, 'MEDIA_URL', '/media/') or '/media/').strip('/')
        if rel.startswith(media_prefix + '/'):
            rel = rel[len(media_prefix):].lstrip('/')
        course_id = str(purchase.course_id)
        if rel.startswith('lesson_pages/'):
            parts = rel.split('/')
            if len(parts) < 4:
                return HttpResponseForbidden('Неверный путь урока')
            if parts[0] != 'lesson_pages' or parts[1] != course_id:
                return HttpResponseForbidden('Доступ запрещён')
        elif rel.startswith('course_content/'):
            parts = rel.split('/')
            if len(parts) < 3:
                return HttpResponseForbidden('Неверный путь контента')
            if parts[0] != 'course_content' or parts[1] != course_id:
                return HttpResponseForbidden('Доступ запрещён')
        else:
            return HttpResponseForbidden('Разрешены только lesson_pages и course_content')
        root = getattr(settings, 'MEDIA_ROOT', None)
        if not root:
            return HttpResponseForbidden('Медиа не настроено')
        root = os.path.normpath(os.path.abspath(str(root)))
        file_path = os.path.normpath(os.path.join(root, rel))
        if not file_path.startswith(root) or not os.path.isfile(file_path):
            raise Http404('Файл не найден')
        ext = os.path.splitext(file_path)[1].lower()
        content_type = 'application/octet-stream'
        if ext == '.pdf':
            content_type = 'application/pdf'
        elif ext in ('.jpg', '.jpeg'):
            content_type = 'image/jpeg'
        elif ext == '.png':
            content_type = 'image/png'
        elif ext == '.webp':
            content_type = 'image/webp'
        elif ext == '.gif':
            content_type = 'image/gif'
        try:
            f = open(file_path, 'rb')
        except OSError:
            raise Http404('Файл недоступен')
        response = FileResponse(f, content_type=content_type)
        response['Content-Disposition'] = 'inline; filename="' + os.path.basename(file_path) + '"'
        return response
    except Http404:
        raise
    except Exception:
        raise Http404('Файл недоступен')


@login_required
def lesson_feedback(request, purchase_id, lesson_id):
    """После «Я усвоил»: понравился ли урок? 👍 / 👎, необязательный отзыв. POST — сохранить и вернуться к списку уроков."""
    purchase = get_object_or_404(
        CoursePurchase,
        id=purchase_id,
        user=request.user,
        status='paid',
    )
    if _purchase_has_pending_refund(purchase):
        messages.warning(request, 'Заявление на возврат по этому курсу уже подано и находится на рассмотрении. Курс недоступен.')
        return redirect('my_courses')
    lesson = get_object_or_404(Lesson, id=lesson_id, course=purchase.course)
    if request.method == 'POST':
        review_text = (request.POST.get('review_text') or '').strip() or None
        liked = None
        if request.POST.get('liked') == '1':
            liked = True
        elif request.POST.get('liked') == '0':
            liked = False
        completion, _ = LessonCompletion.objects.get_or_create(
            course_purchase=purchase,
            lesson=lesson,
            defaults={'liked': None, 'review_text': None},
        )
        if liked is not None:
            completion.liked = liked
        completion.review_text = review_text
        update_fields = ['review_text']
        if liked is not None:
            update_fields.append('liked')
        completion.save(update_fields=update_fields)
        # Если в курсе один урок и он пройден — переводим покупку в архив
        if purchase.course.lessons.count() == 1 and purchase.completed_at is None:
            from django.utils import timezone
            purchase.completed_at = timezone.now()
            purchase.save(update_fields=['completed_at'])
        messages.success(request, 'Спасибо за оценку! Урок отмечен как пройденный.')
        return redirect('course_lessons_list', purchase_id=purchase_id)
    # GET: при открытии страницы «Я усвоил» сразу отмечаем урок как пройденный
    completion, _ = LessonCompletion.objects.get_or_create(
        course_purchase=purchase,
        lesson=lesson,
        defaults={'liked': None},
    )
    return render(request, 'profile/lesson_feedback.html', {
        'purchase': purchase,
        'course': purchase.course,
        'lesson': lesson,
        'completion': completion,
    })


@login_required
@require_POST
def course_content_view_record(request, purchase_id):
    """Записать просмотр страницы контента (для учёта «долистал до конца»)."""
    purchase = get_object_or_404(CoursePurchase, id=purchase_id, user=request.user, status='paid')
    if _purchase_has_pending_refund(purchase):
        return JsonResponse({'success': False, 'message': 'Курс недоступен: заявление на возврат на рассмотрении.'}, status=403)
    try:
        data = json.loads(request.body)
        page_id = data.get('content_page_id')
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'success': False, 'message': 'Неверные данные'}, status=400)
    if not page_id:
        return JsonResponse({'success': False, 'message': 'content_page_id обязателен'}, status=400)
    content_page = get_object_or_404(CourseContentPage, id=page_id, course=purchase.course)
    CourseContentView.objects.get_or_create(course_purchase=purchase, content_page=content_page)
    return JsonResponse({'success': True})


@login_required
@require_POST
def course_survey_submit(request, purchase_id):
    """Отправить опрос в конце курса (5 баллов)."""
    purchase = get_object_or_404(CoursePurchase, id=purchase_id, user=request.user, status='paid')
    if _purchase_has_pending_refund(purchase):
        return JsonResponse({'success': False, 'message': 'Курс недоступен: заявление на возврат на рассмотрении.'}, status=403)
    if purchase.has_survey():
        return JsonResponse({'success': True, 'already': True})
    try:
        data = json.loads(request.body)
        rating = int(data.get('rating', 0))
        if not (1 <= rating <= 5):
            return JsonResponse({'success': False, 'message': 'Оценка от 1 до 5'}, status=400)
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Неверные данные'}, status=400)
    CourseSurvey.objects.create(
        course=purchase.course,
        user=request.user,
        course_purchase=purchase,
        answers={'rating': rating},
    )
    purchase.mark_completed_if_ready()
    return JsonResponse({'success': True})


@login_required
@require_POST
def course_review_submit(request, purchase_id):
    """Отправить отзыв о курсе."""
    purchase = get_object_or_404(CoursePurchase, id=purchase_id, user=request.user, status='paid')
    if _purchase_has_pending_refund(purchase):
        return JsonResponse({'success': False, 'message': 'Курс недоступен: заявление на возврат на рассмотрении.'}, status=403)
    try:
        data = json.loads(request.body)
        rating = int(data.get('rating', 0))
        text = (data.get('text') or '').strip()
        if not (1 <= rating <= 5):
            return JsonResponse({'success': False, 'message': 'Оценка от 1 до 5'}, status=400)
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Неверные данные'}, status=400)
    rev = CourseReview.objects.filter(course_purchase=purchase).first()
    if rev:
        rev.rating = rating
        rev.review_text = text
        rev.save()
    else:
        CourseReview.objects.create(
            course=purchase.course,
            user=request.user,
            course_purchase=purchase,
            rating=rating,
            review_text=text,
        )
    purchase.mark_completed_if_ready()
    return JsonResponse({'success': True})


@login_required
@require_POST
def course_refund_request_create(request, purchase_id):
    """Создать заявление на возврат курса (только если уроки не пройдены)."""
    purchase = get_object_or_404(
        CoursePurchase,
        id=purchase_id,
        user=request.user,
        status='paid',
    )
    if CourseRefundRequest.objects.filter(course_purchase=purchase, status='pending').exists():
        messages.info(request, 'У вас уже есть заявление на возврат по этому курсу.')
        return redirect('course_lessons_list', purchase_id=purchase_id)
    if purchase.lesson_completions.exists():
        messages.error(request, 'Возврат невозможен: вы уже прошли уроки курса.')
        return redirect('course_lessons_list', purchase_id=purchase_id)
    amount = purchase.amount
    refund = CourseRefundRequest.objects.create(
        user=request.user,
        course_purchase=purchase,
        amount=amount,
        status='pending',
    )
    messages.success(request, f'Заявление на возврат создано. Номер заявления: {refund.refund_number}. Ожидайте рассмотрения.')
    return redirect('course_lessons_list', purchase_id=purchase_id)


# =================== История заказов ===================
@login_required
def order_history_view(request):
    orders = Order.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "profile/order_history.html", {"orders": orders})

@login_required
def order_detail_view(request, pk):
    """
    Детали заказа: данные подгружаются на клиенте через API /api/orders/<id>/.
    View только рендерит шаблон и передает ID заказа.
    """
    return render(request, "profile/order_detail.html", {"order_id": pk})

@login_required
@require_POST
def cancel_order(request, pk):
    """Отмена заказа с возвратом денег и товара на склад"""
    order = get_object_or_404(Order, pk=pk, user=request.user)
    
    if not order.can_cancel():
        messages.error(request, "Этот заказ нельзя отменить.")
        return redirect('order_detail', pk=order.pk)
    
    # Проверяем, были ли средства переведены на счет организации
    # Ищем транзакцию order_payment для этого заказа
    org_payment_transaction = OrganizationTransaction.objects.filter(
        order=order,
        transaction_type='order_payment'
    ).first()
    
    # Если заказ был в статусе "processing" (в обработке) и средства НЕ были переведены на счет организации
    # (т.е. оплата была наличными и заказ не был доставлен) - ничего не начисляется и не списывается
    if order.order_status == 'processing' and not org_payment_transaction:
        # Просто отменяем заказ, не трогая счет организации (средства не были переведены)
        order.order_status = 'cancelled'
        order.can_be_cancelled = False
        order.save()
        
        # Возврат на склад только для товаров (для курсов не требуется; модели Product/ProductSize удалены)
        for item in order.items.all():
            pass  # курсы — возврат на склад не нужен
        
        # Возвращаем деньги клиенту (если заказ был оплачен НЕ наличными)
        # Для наличных платежей при отмене в статусе "processing" ничего не возвращаем
        payment = Payment.objects.filter(order=order).first()
        is_cash = payment and (payment.payment_method == 'cash' or (payment.payment_status == 'pending' and payment.payment_method not in ['balance', 'card', 'visa', 'mastercard']))
        was_paid = order.paid_from_balance or (payment and payment.payment_status == 'paid')
        
        # Если оплата была наличными - ничего не возвращаем (наличные не списывались)
        if not is_cash and was_paid:
            if order.paid_from_balance:
                profile, _ = UserProfile.objects.get_or_create(user=order.user)
                balance_before = profile.balance
                profile.balance += order.total_amount
                profile.save()
                BalanceTransaction.objects.create(
                    user=order.user,
                    transaction_type='order_refund',
                    amount=order.total_amount,
                    description=f'Возврат за отмененный заказ #{order.id}',
                    order=order,
                    status='completed'
                )
            elif payment and payment.saved_payment_method:
                try:
                    card = payment.saved_payment_method
                    card.balance += order.total_amount
                    card.save()
                    CardTransaction.objects.create(
                        saved_payment_method=card,
                        transaction_type='deposit',
                        amount=order.total_amount,
                        description=f'Возврат за отмененный заказ #{order.id}',
                        status='completed'
                    )
                except Exception:
                    profile, _ = UserProfile.objects.get_or_create(user=order.user)
                    balance_before = profile.balance
                    profile.balance += order.total_amount
                    profile.save()
                    BalanceTransaction.objects.create(
                        user=order.user,
                        transaction_type='order_refund',
                        amount=order.total_amount,
                        description=f'Возврат за отмененный заказ #{order.id} (карта недоступна)',
                        order=order,
                        status='completed'
                    )
            else:
                profile, _ = UserProfile.objects.get_or_create(user=order.user)
                balance_before = profile.balance
                profile.balance += order.total_amount
                profile.save()
                BalanceTransaction.objects.create(
                    user=order.user,
                    transaction_type='order_refund',
                    amount=order.total_amount,
                    description=f'Возврат за отмененный заказ #{order.id}',
                    order=order,
                    status='completed'
                )
        
        # Аннулируем чек, если есть
        try:
            if hasattr(order, 'receipt') and order.receipt:
                order.receipt.status = 'annulled'
                order.receipt.save()
        except Exception:
            pass
        
        _log_activity(request.user, 'update', f'order_{order.id}', 'Заказ отменен пользователем', request)
        messages.success(request, "Заказ отменен. Деньги возвращены на баланс, товар возвращен на склад.")
        return redirect('order_detail', pk=order.pk)
    
    # Возвращаем товар на склад (только для товаров; для курсов не требуется — модели Product/ProductSize удалены)
    for item in order.items.all():
        pass
    
    # Проверяем, был ли заказ оплачен (не наличными)
    payment = Payment.objects.filter(order=order).first()
    is_cash = payment and (payment.payment_method == 'cash' or (payment.payment_status == 'pending' and payment.payment_method not in ['balance', 'card', 'visa', 'mastercard']))
    was_paid = order.paid_from_balance or (payment and payment.payment_status == 'paid')
    
    with transaction.atomic():
        # Проверяем, был ли заказ доставлен
        # Если заказ был доставлен - средства остаются на счете организации, даже при отмене
        was_delivered = order.order_status == 'delivered'
        
        # Возвращаем средства со счета организации только если:
        # 1. Средства были переведены на счет организации
        # 2. Заказ НЕ был доставлен (если был доставлен - деньги остаются на счете)
        if org_payment_transaction and not was_delivered:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"ОТМЕНА ЗАКАЗА #{order.id}: Найдена транзакция order_payment, возвращаем средства")
            logger.error(f"Сумма заказа: {order.total_amount}, налог: {order.tax_amount}")
            
            org_account = OrganizationAccount.get_account()
            org_balance_before = org_account.balance
            org_tax_reserve_before = org_account.tax_reserve
            
            logger.error(f"Баланс организации до возврата: {org_balance_before}, резерв: {org_tax_reserve_before}")
            
            # Проверяем, что на счете достаточно средств для возврата
            if org_account.balance < order.total_amount:
                logger.error(f"ОШИБКА: Недостаточно средств на счете организации для возврата. Баланс: {org_account.balance}, требуется: {order.total_amount}")
                messages.error(request, "Недостаточно средств на счете организации для возврата.")
                return redirect('order_detail', pk=order.pk)
            
            # Возвращаем сумму заказа
            org_account.balance -= order.total_amount
            
            # Возвращаем налог из резерва при возврате заказа (3НФ: balance_* не храним)
            if org_account.tax_reserve >= order.tax_amount:
                org_account.tax_reserve -= order.tax_amount
            else:
                org_account.tax_reserve = Decimal('0.00')
            
            org_account.save()
            OrganizationTransaction.objects.create(
                organization_account=org_account,
                transaction_type='order_refund',
                amount=order.total_amount,
                description=f'Возврат по отмене заказа #{order.id}',
                order=order,
                created_by=request.user,
                balance_before=org_balance_before,
                balance_after=org_account.balance,
                tax_reserve_before=org_tax_reserve_before,
                tax_reserve_after=org_account.tax_reserve,
            )
            logger.error(f"✅ Транзакция возврата создана для заказа #{order.id}")
        
        # Возвращаем деньги клиенту если:
        # 1. Заказ был оплачен НЕ наличными И средства были переведены на счет организации И заказ НЕ был доставлен
        # 2. Если заказ был доставлен - деньги остаются на счете организации (не возвращаем)
        should_refund = False
        if was_paid and not is_cash:
            # Не наличные - возвращаем если средства были переведены и заказ не был доставлен
            should_refund = org_payment_transaction and not was_delivered
        # Наличные - не возвращаем, деньги остаются на счете организации
        
        if should_refund:
            # Если оплата была с баланса - возвращаем на баланс
            if order.paid_from_balance:
                profile, _ = UserProfile.objects.get_or_create(user=order.user)
                balance_before = profile.balance
                profile.balance += order.total_amount
                profile.save()
                
                # Создаем транзакцию возврата
                BalanceTransaction.objects.create(
                    user=order.user,
                    transaction_type='order_refund',
                    amount=order.total_amount,
                    description=f'Возврат за отмененный заказ #{order.id}',
                    order=order,
                    status='completed'
                )
            # Если оплата была картой - возвращаем на карту
            elif payment and payment.saved_payment_method:
                try:
                    card = payment.saved_payment_method
                    card.balance += order.total_amount
                    card.save()
                    
                    # Создаем транзакцию по карте
                    CardTransaction.objects.create(
                        saved_payment_method=card,
                        transaction_type='deposit',
                        amount=order.total_amount,
                        description=f'Возврат за отмененный заказ #{order.id}',
                        status='completed'
                    )
                except Exception:
                    # Если не удалось вернуть на карту, возвращаем на баланс
                    profile, _ = UserProfile.objects.get_or_create(user=order.user)
                    balance_before = profile.balance
                    profile.balance += order.total_amount
                    profile.save()
                    
                    BalanceTransaction.objects.create(
                        user=order.user,
                        transaction_type='order_refund',
                        amount=order.total_amount,
                        description=f'Возврат за отмененный заказ #{order.id} (карта недоступна)',
                        order=order,
                        status='completed'
                    )
            # Если оплата была наличными или другим способом - возвращаем на баланс
            else:
                profile, _ = UserProfile.objects.get_or_create(user=order.user)
                balance_before = profile.balance
                profile.balance += order.total_amount
                profile.save()
                
                BalanceTransaction.objects.create(
                    user=order.user,
                    transaction_type='order_refund',
                    amount=order.total_amount,
                    description=f'Возврат за отмененный заказ #{order.id}',
                    order=order,
                    status='completed'
                )
    
    # Обновляем статус заказа
    order.order_status = 'cancelled'
    order.can_be_cancelled = False
    order.save()

    # Аннулируем чек, если есть
    try:
        if hasattr(order, 'receipt') and order.receipt:
            order.receipt.status = 'annulled'
            order.receipt.save()
    except Exception:
        pass
    
    _log_activity(request.user, 'update', f'order_{order.id}', 'Заказ отменен пользователем', request)
    messages.success(request, "Заказ отменен. Деньги возвращены на баланс, товар возвращен на склад.")
    return redirect('order_detail', pk=order.pk)


def _process_order_cancellation(order, cancelled_by_user):
    """
    Вспомогательная функция для обработки отмены заказа.
    Возвращает товары на склад, возвращает деньги со счета организации и клиенту.
    
    Args:
        order: Order объект
        cancelled_by_user: User объект, который отменил заказ
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Проверяем, были ли средства переведены на счет организации
    org_payment_transaction = OrganizationTransaction.objects.filter(
        order=order,
        transaction_type='order_payment'
    ).first()
    
    # Возвращаем товары на склад (для курсов не требуется)
    for item in order.items.all():
        pass
    
    # Проверяем, был ли заказ оплачен
    payment = Payment.objects.filter(order=order).first()
    is_cash = payment and (payment.payment_method == 'cash' or (payment.payment_status == 'pending' and payment.payment_method not in ['balance', 'card', 'visa', 'mastercard']))
    was_paid = order.paid_from_balance or (payment and payment.payment_status == 'paid')
    
    # Проверяем, был ли заказ доставлен
    was_delivered = order.order_status == 'delivered'
    
    with transaction.atomic():
        # Возвращаем средства со счета организации только если:
        # 1. Средства были переведены на счет организации
        # 2. Заказ НЕ был доставлен (если был доставлен - деньги остаются на счете)
        if org_payment_transaction and not was_delivered:
            logger.info(f"ОТМЕНА ЗАКАЗА #{order.id}: Найдена транзакция order_payment, возвращаем средства")
            
            org_account = OrganizationAccount.get_account()
            org_balance_before = org_account.balance
            org_tax_reserve_before = org_account.tax_reserve
            
            # Проверяем, что на счете достаточно средств для возврата
            if org_account.balance < order.total_amount:
                logger.error(f"ОШИБКА: Недостаточно средств на счете организации для возврата. Баланс: {org_account.balance}, требуется: {order.total_amount}")
                raise ValueError(f"Недостаточно средств на счете организации для возврата. Баланс: {org_account.balance} ₽, требуется: {order.total_amount} ₽")
            
            # Возвращаем сумму заказа
            org_account.balance -= order.total_amount
            
            # Возвращаем налог из резерва при возврате заказа
            if org_account.tax_reserve >= order.tax_amount:
                org_account.tax_reserve -= order.tax_amount
            else:
                org_account.tax_reserve = Decimal('0.00')
            org_account.save()
            OrganizationTransaction.objects.create(
                organization_account=org_account,
                transaction_type='order_refund',
                amount=order.total_amount,
                description=f'Возврат по отмене заказа #{order.id}',
                order=order,
                created_by=cancelled_by_user,
                balance_before=org_balance_before,
                balance_after=org_account.balance,
                tax_reserve_before=org_tax_reserve_before,
                tax_reserve_after=org_account.tax_reserve,
            )
            logger.info(f"✅ Транзакция возврата создана для заказа #{order.id}")
        
        # Возвращаем деньги клиенту если:
        # 1. Заказ был оплачен НЕ наличными И средства были переведены на счет организации И заказ НЕ был доставлен
        # 2. Если заказ был доставлен - деньги остаются на счете организации (не возвращаем)
        should_refund = False
        if was_paid and not is_cash:
            # Не наличные - возвращаем если средства были переведены и заказ не был доставлен
            should_refund = org_payment_transaction and not was_delivered
        
        if should_refund:
            # Если оплата была с баланса - возвращаем на баланс
            if order.paid_from_balance:
                profile, _ = UserProfile.objects.select_for_update().get_or_create(user=order.user)
                balance_before = profile.balance
                profile.balance += order.total_amount
                profile.save()
                
                BalanceTransaction.objects.create(
                    user=order.user,
                    transaction_type='order_refund',
                    amount=order.total_amount,
                    description=f'Возврат за отмененный заказ #{order.id}',
                    order=order,
                    status='completed'
                )
            # Если оплата была картой - возвращаем на карту
            elif payment and payment.saved_payment_method:
                try:
                    card = payment.saved_payment_method
                    card.balance += order.total_amount
                    card.save()
                    
                    # Создаем транзакцию по карте
                    CardTransaction.objects.create(
                        saved_payment_method=card,
                        transaction_type='deposit',
                        amount=order.total_amount,
                        description=f'Возврат за отмененный заказ #{order.id}',
                        status='completed'
                    )
                except Exception as e:
                    logger.error(f"Ошибка при возврате на карту для заказа #{order.id}: {str(e)}")
                    # Если не удалось вернуть на карту, возвращаем на баланс
                    profile, _ = UserProfile.objects.select_for_update().get_or_create(user=order.user)
                    balance_before = profile.balance
                    profile.balance += order.total_amount
                    profile.save()
                    
                    BalanceTransaction.objects.create(
                        user=order.user,
                        transaction_type='order_refund',
                        amount=order.total_amount,
                        description=f'Возврат за отмененный заказ #{order.id} (карта недоступна)',
                        order=order,
                        status='completed'
                    )
            # Если оплата была другим способом - возвращаем на баланс
            else:
                profile, _ = UserProfile.objects.select_for_update().get_or_create(user=order.user)
                balance_before = profile.balance
                profile.balance += order.total_amount
                profile.save()
                
                BalanceTransaction.objects.create(
                    user=order.user,
                    transaction_type='order_refund',
                    amount=order.total_amount,
                    description=f'Возврат за отмененный заказ #{order.id}',
                    order=order,
                    status='completed'
                )
    
    # Обновляем статус заказа
    order.order_status = 'cancelled'
    order.can_be_cancelled = False
    order.save()
    
    # Аннулируем чек, если есть
    try:
        if hasattr(order, 'receipt') and order.receipt:
            order.receipt.status = 'annulled'
            order.receipt.save()
    except Exception:
        pass

# =================== Способы оплаты ===================
@login_required
def payment_methods_view(request):
    payment_methods = SavedPaymentMethod.objects.filter(user=request.user).prefetch_related('transactions')
    return render(request, 'profile/payment_methods.html', {'payment_methods': payment_methods})

@login_required
@require_POST
def add_payment_method(request):
    card_number = request.POST.get('card_number', '').strip().replace(' ', '')
    card_holder_name = request.POST.get('card_holder_name', '').strip()
    expiry_month = request.POST.get('expiry_month', '').strip()
    expiry_year = request.POST.get('expiry_year', '').strip()
    is_default = request.POST.get('is_default') == 'on'
    
    if not all([card_number, card_holder_name, expiry_month, expiry_year]):
        messages.error(request, "Пожалуйста, заполните все поля.")
        return redirect('payment_methods')
    
    # Определяем тип карты
    card_type = 'visa' if card_number.startswith('4') else 'mastercard' if card_number.startswith('5') else 'card'
    
    # Сохраняем только последние 4 цифры
    card_last_4 = card_number[-4:] if len(card_number) >= 4 else card_number
    
    # Если это основная карта, снимаем флаг с других
    if is_default:
        SavedPaymentMethod.objects.filter(user=request.user).update(is_default=False)
    
    SavedPaymentMethod.objects.create(
        user=request.user,
        card_number=card_last_4,
        card_holder_name=card_holder_name,
        expiry_month=expiry_month,
        expiry_year=expiry_year,
        card_type=card_type,
        is_default=is_default
    )
    
    messages.success(request, "Способ оплаты добавлен.")
    return redirect('payment_methods')

@login_required
@require_POST
def delete_payment_method(request, payment_id):
    payment = get_object_or_404(SavedPaymentMethod, id=payment_id, user=request.user)
    payment.delete()
    messages.success(request, "Способ оплаты удален.")
    return redirect('payment_methods')

@login_required
@require_POST
def set_default_payment_method(request, payment_id):
    SavedPaymentMethod.objects.filter(user=request.user).update(is_default=False)
    payment = get_object_or_404(SavedPaymentMethod, id=payment_id, user=request.user)
    payment.is_default = True
    payment.save()
    messages.success(request, "Основной способ оплаты изменен.")
    return redirect('payment_methods')

# =================== Баланс ===================
@login_required
def balance_view(request):
    """Страница управления балансом"""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    transactions = BalanceTransaction.objects.filter(user=request.user)[:20]
    saved_payments = SavedPaymentMethod.objects.filter(user=request.user)
    
    return render(request, 'profile/balance.html', {
        'profile': profile,
        'transactions': transactions,
        'saved_payments': saved_payments
    })

@login_required
@require_POST
def deposit_balance(request):
    """Пополнение баланса с карты"""
    try:
        amount = Decimal(request.POST.get('amount', '0'))
        card_id = request.POST.get('card_id')
        
        if amount <= 0:
            messages.error(request, "Сумма пополнения должна быть больше нуля.")
            return redirect('balance')
        
        if not card_id:
            messages.error(request, "Пожалуйста, выберите карту для пополнения.")
            return redirect('balance')
        
        # Проверяем, что карта принадлежит пользователю
        card = get_object_or_404(SavedPaymentMethod, id=card_id, user=request.user)
        with transaction.atomic():
            # Блокируем строку карты для корректного списания
            card = SavedPaymentMethod.objects.select_for_update().get(id=card.id)
            profile, _ = UserProfile.objects.select_for_update().get_or_create(user=request.user)
            if card.balance < amount:
                messages.error(request, f"Недостаточно средств на карте. Баланс карты: {card.balance} ₽")
                return redirect('balance')
            balance_before = profile.balance
            # Списание с карты (проверяем, что баланс не станет отрицательным)
            new_card_balance = card.balance - amount
            if new_card_balance < 0:
                messages.error(request, f"Недостаточно средств на карте. Баланс карты: {card.balance} ₽")
                return redirect('balance')
            card.balance = new_card_balance
            card.save()
            # Пополнение баланса пользователя
            profile.balance += amount
            profile.save()
            
            # Создаем транзакцию баланса
            BalanceTransaction.objects.create(
                user=request.user,
                transaction_type='deposit',
                amount=amount,
                description=f'Пополнение баланса с карты {card.mask_card_number()}',
                status='completed'
            )
            
            # Создаем транзакцию по карте (списание)
            CardTransaction.objects.create(
                saved_payment_method=card,
                transaction_type='withdrawal',
                amount=amount,
                description=f'Перевод на баланс пользователя {amount} ₽',
                status='completed'
            )
        messages.success(request, f"Баланс пополнен на {amount} ₽ с карты {card.mask_card_number()}. Текущий баланс: {profile.balance} ₽")
    except (ValueError, TypeError):
        messages.error(request, "Неверная сумма.")
    
    return redirect('balance')

@login_required
@require_POST
def withdraw_balance(request):
    """Вывод средств с баланса на карту"""
    try:
        amount = Decimal(request.POST.get('amount', '0'))
        card_id = request.POST.get('card_id')
        
        if amount <= 0:
            messages.error(request, "Сумма вывода должна быть больше нуля.")
            return redirect('balance')
        
        if not card_id:
            messages.error(request, "Пожалуйста, выберите карту для вывода.")
            return redirect('balance')
        
        # Проверяем, что карта принадлежит пользователю
        card = get_object_or_404(SavedPaymentMethod, id=card_id, user=request.user)
        
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        
        if profile.balance < amount:
            messages.error(request, f"Недостаточно средств на балансе. Текущий баланс: {profile.balance} ₽")
            return redirect('balance')
        
        with transaction.atomic():
            # блокируем профиль и карту
            profile = UserProfile.objects.select_for_update().get(user=request.user)
            card = SavedPaymentMethod.objects.select_for_update().get(id=card.id)
            balance_before = profile.balance
            # Списываем с баланса пользователя
            profile.balance -= amount
            profile.save()
            # Пополняем баланс карты
            card.balance += amount
            card.save()
            
            # Создаем транзакцию баланса
            BalanceTransaction.objects.create(
                user=request.user,
                transaction_type='withdrawal',
                amount=amount,
                description=f'Вывод средств на карту {card.mask_card_number()}',
                status='completed'
            )
            
            # Создаем транзакцию по карте (пополнение)
            CardTransaction.objects.create(
                saved_payment_method=card,
                transaction_type='deposit',
                amount=amount,
                description=f'Пополнение карты на {amount} ₽ с внутреннего баланса',
                status='completed'
            )
        
        messages.success(request, f"Средства выведены: {amount} ₽ на карту {card.mask_card_number()}. Текущий баланс: {profile.balance} ₽")
    except (ValueError, TypeError):
        messages.error(request, "Неверная сумма.")
    
    return redirect('balance')

@login_required
def get_card_transactions(request, card_id):
    """Получить транзакции по карте (AJAX)"""
    card = get_object_or_404(SavedPaymentMethod, id=card_id, user=request.user)
    transactions = CardTransaction.objects.filter(saved_payment_method=card)[:20]
    
    transactions_data = [{
        'id': t.id,
        'type': t.get_transaction_type_display(),
        'amount': float(t.amount),
        'description': t.description,
        'date': t.created_at.strftime('%d.%m.%Y %H:%M'),
        'status': t.status
    } for t in transactions]
    
    return JsonResponse({
        'card': {
            'id': card.id,
            'mask': card.mask_card_number(),
            'type': card.card_type or 'CARD',
            'holder': card.card_holder_name,
            'balance': float(card.balance)
        },
        'transactions': transactions_data
    })

@login_required
@require_POST
def deposit_from_card(request, card_id):
    """Пополнение баланса с конкретной карты"""
    try:
        amount = Decimal(request.POST.get('amount', '0'))
        if amount <= 0:
            return JsonResponse({'success': False, 'message': 'Сумма должна быть больше нуля'}, status=400)
        
        card = get_object_or_404(SavedPaymentMethod, id=card_id, user=request.user)
        with transaction.atomic():
            card = SavedPaymentMethod.objects.select_for_update().get(id=card.id)
            profile, _ = UserProfile.objects.select_for_update().get_or_create(user=request.user)
            if card.balance < amount:
                return JsonResponse({'success': False, 'message': 'Недостаточно средств на карте'}, status=400)
            # Списываем с карты (проверяем, что баланс не станет отрицательным)
            new_card_balance = card.balance - amount
            if new_card_balance < 0:
                return JsonResponse({'success': False, 'message': 'Недостаточно средств на карте'}, status=400)
            card.balance = new_card_balance
            card.save()
            # Пополняем баланс пользователя
            balance_before = profile.balance
            profile.balance += amount
            profile.save()
            
            # Создаем транзакции
            BalanceTransaction.objects.create(
                user=request.user,
                transaction_type='deposit',
                amount=amount,
                description=f'Пополнение баланса с карты {card.mask_card_number()}',
                status='completed'
            )
            
            CardTransaction.objects.create(
                saved_payment_method=card,
                transaction_type='withdrawal',  # списание с карты при переводе на счет
                amount=amount,
                description=f'Перевод на счет пользователя {amount} ₽',
                status='completed'
            )
        
        return JsonResponse({
            'success': True,
            'message': f'Баланс пополнен на {amount} ₽',
            'new_balance': float(profile.balance),
            'card_balance': float(card.balance)
        })
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Неверная сумма'}, status=400)

@login_required
@require_POST
def withdraw_to_card(request, card_id):
    """Вывод средств на конкретную карту"""
    try:
        amount = Decimal(request.POST.get('amount', '0'))
        if amount <= 0:
            return JsonResponse({'success': False, 'message': 'Сумма должна быть больше нуля'}, status=400)
        
        card = get_object_or_404(SavedPaymentMethod, id=card_id, user=request.user)
        with transaction.atomic():
            profile, _ = UserProfile.objects.select_for_update().get_or_create(user=request.user)
            if profile.balance < amount:
                return JsonResponse({'success': False, 'message': 'Недостаточно средств на внутреннем балансе'}, status=400)
            # блокируем карту
            card = SavedPaymentMethod.objects.select_for_update().get(id=card.id)
            balance_before = profile.balance
            # списываем с баланса профиля
            profile.balance -= amount
            profile.save()
            # пополняем карту
            card.balance += amount
            card.save()
            # транзакция баланса
            BalanceTransaction.objects.create(
                user=request.user,
                transaction_type='withdrawal',
                amount=amount,
                description=f'Вывод средств на карту {card.mask_card_number()}',
                status='completed'
            )
            # транзакция по карте
            CardTransaction.objects.create(
                saved_payment_method=card,
                transaction_type='deposit',
                amount=amount,
                description=f'Пополнение карты на {amount} ₽',
                status='completed'
            )
        
        return JsonResponse({
            'success': True,
            'message': f'Карта пополнена на {amount} ₽',
            'new_balance': float(profile.balance),
            'card_balance': float(card.balance)
        })
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Неверная сумма'}, status=400)


@login_required
@require_POST
def topup_card_balance(request, card_id):
    """Прямое пополнение баланса конкретной карты (без списания откуда-либо)"""
    try:
        amount = Decimal(request.POST.get('amount', '0'))
        if amount <= 0:
            return JsonResponse({'success': False, 'message': 'Сумма должна быть больше нуля'}, status=400)
        
        card = get_object_or_404(SavedPaymentMethod, id=card_id, user=request.user)
        card.balance += amount
        card.save()
        
        # Лог транзакции по карте
        CardTransaction.objects.create(
            saved_payment_method=card,
            transaction_type='deposit',
            amount=amount,
            description=f'Пополнение карты на {amount} ₽',
            status='completed'
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Карта пополнена на {amount} ₽',
            'card_balance': float(card.balance)
        })
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': 'Неверная сумма'}, status=400)

# =================== Адреса ===================
@login_required
def addresses_view(request):
    addresses = UserAddress.objects.filter(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            UserAddress.objects.create(
                user=request.user,
                address_title=request.POST.get("address_title", ""),
                city_name=request.POST.get("city_name"),
                street_name=request.POST.get("street_name"),
                house_number=request.POST.get("house_number"),
                apartment_number=request.POST.get("apartment_number", ""),
                postal_code=request.POST.get("postal_code"),
                is_primary=request.POST.get("is_primary") == "on"
            )
            messages.success(request, "Адрес добавлен.")
        elif action == "edit":
            addr_id = request.POST.get("address_id")
            try:
                address = UserAddress.objects.get(id=addr_id, user=request.user)
                address.address_title = request.POST.get("address_title", "")
                address.city_name = request.POST.get("city_name")
                address.street_name = request.POST.get("street_name")
                address.house_number = request.POST.get("house_number")
                address.apartment_number = request.POST.get("apartment_number", "")
                address.postal_code = request.POST.get("postal_code")
                address.is_primary = request.POST.get("is_primary") == "on"
                address.save()
                messages.success(request, "Адрес обновлен.")
            except UserAddress.DoesNotExist:
                messages.error(request, "Адрес не найден.")
        elif action == "delete":
            addr_id = request.POST.get("address_id")
            UserAddress.objects.filter(id=addr_id, user=request.user).delete()
            messages.success(request, "Адрес удален.")
        elif action == "set_primary":
            addr_id = request.POST.get("address_id")
            UserAddress.objects.filter(user=request.user).update(is_primary=False)
            UserAddress.objects.filter(id=addr_id, user=request.user).update(is_primary=True)
            messages.success(request, "Основной адрес изменен.")
        return redirect("addresses")

    return render(request, "profile/addresses.html", {"addresses": addresses})

@login_required
def delete_account(request):
    if request.method == "POST":
        user = request.user
        logout(request)  # разлогиниваем пользователя
        user.delete()    # удаляем аккаунт
        messages.success(request, "Ваш аккаунт был удален.")
        return redirect('home')
    return render(request, 'profile/delete_account.html')

ADMIN_SECRET_MESSAGE = 'privet yaz'
ADMIN_SECRET_CODE = '23051967'

def custom_admin_login(request):
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()
        code = request.POST.get('secret_code', '').strip()

        if message == ADMIN_SECRET_MESSAGE and code == ADMIN_SECRET_CODE:
            # Сохраняем сессию, чтобы открыть стандартный admin
            request.session['admin_access_granted'] = True
            return redirect('/admin/')  # перенаправляем в стандартный admin
        else:
            messages.error(request, 'Неверное сообщение или секретный код')

    return render(request, 'main/custom_admin_login.html')

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.forms import modelform_factory

def _format_money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))} ₽"

# Импорт вспомогательных функций из helpers.py
from .helpers import _user_is_admin, _user_is_manager, _log_activity


def admin_redirect_to_dashboard(request):
    """Редирект для отключённых разделов админки (товары/категории/бренды/поставщики). Остались только курсы."""
    messages.info(request, "Раздел отключён. В системе только курсы.")
    return redirect('admin_dashboard')


@login_required
def management_dashboard(request):
    """Расширенная панель администратора"""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен. Требуется роль администратора.")
        return redirect('profile')
    
    _log_activity(request.user, 'view', 'admin_dashboard', 'Просмотр панели администратора', request)
    
    from django.db.models import Count, Sum
    from django.utils import timezone
    from datetime import timedelta
    
    # Статистика для дашборда
    total_users = User.objects.count()
    total_courses = Course.objects.count()
    total_orders = Order.objects.count()
    total_tickets = SupportTicket.objects.count()
    new_tickets = SupportTicket.objects.filter(ticket_status='new').count()
    recent_logs = ActivityLog.objects.select_related('user').order_by('-created_at')[:10]
    
    # Активность за последние 7 дней
    week_ago = timezone.now() - timedelta(days=7)
    recent_activity = ActivityLog.objects.filter(created_at__gte=week_ago).count()
    
    # Счет организации
    org_account = OrganizationAccount.get_account()
    
    stats = {
        'total_users': total_users,
        'total_courses': total_courses,
        'total_orders': total_orders,
        'total_tickets': total_tickets,
        'new_tickets': new_tickets,
        'recent_activity': recent_activity,
        'recent_logs': recent_logs,
        'org_balance': org_account.balance,
        'org_tax_reserve': org_account.tax_reserve,
    }
    
    blocks = [
        {'title': 'Пользователи и роли', 'desc': 'Создание, редактирование, назначение ролей', 'url': 'admin_users_list', 'icon': '👥'},
        {'title': 'Курсы', 'desc': 'Список курсов, добавление и редактирование (страницы контента, категории)', 'url': 'admin_courses_list', 'icon': '📚'},
        {'title': 'Оценки уроков', 'desc': 'Статистика: сколько уроков понравилось / не понравилось по каждому курсу, отзывы и комментарии', 'url': 'admin_lesson_feedback_stats', 'icon': '👍'},
        {'title': 'Заказы', 'desc': 'Управление заказами и назначение курьеров', 'url': 'admin_orders_list', 'icon': '📋'},
        {'title': 'Возвраты', 'desc': 'Заявления на возврат курсов: вернуть средства с баланса организации на баланс пользователя', 'url': 'admin_refund_list', 'icon': '↩️'},
        {'title': 'Поддержка', 'desc': 'Управление обращениями и назначение ответственных', 'url': 'admin_support_list', 'icon': '💬'},
        {'title': 'Промокоды', 'desc': 'Создание и управление промокодами', 'url': 'admin_promotions_list', 'icon': '🎫'},
        {'title': 'Аналитика и отчёты', 'desc': 'Расширенная аналитика и экспорт данных', 'url': 'admin_analytics', 'icon': '📊'},
        {'title': 'Счет организации', 'desc': 'Управление счетом организации, вывод средств, оплата налогов', 'url': 'admin_org_account', 'icon': '💰'},
        {'title': 'Логи активности', 'desc': 'Просмотр действий пользователей и аудит', 'url': 'admin_activity_logs', 'icon': '📝'},
        {'title': 'Бэкапы БД', 'desc': 'Создание и управление бэкапами базы данных', 'url': 'admin_backups_list', 'icon': '💾'},
        {'title': 'API Root', 'desc': 'Просмотр всех доступных API эндпоинтов и документации', 'url': '/api/', 'icon': '🔌', 'external': True, 'direct_url': True},
        {'title': 'Swagger UI', 'desc': 'Интерактивная документация API с возможностью тестирования', 'url': 'schema-swagger-ui', 'icon': '📚', 'external': True},
        {'title': 'Настройки администратора', 'desc': 'Настройка секретного слова для восстановления БД', 'url': 'admin_settings', 'icon': '⚙️'},
    ]
    
    return render(request, 'main/admin/dashboard.html', {
        'blocks': blocks,
        'stats': stats
    })


@login_required
def admin_lesson_feedback_stats(request):
    """Статистика по оценкам уроков по курсам: сколько 👍, 👎, без оценки, с отзывами."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен.")
        return redirect('profile')
    from django.db.models import Count
    courses = Course.objects.annotate(
        liked_count=Count('lessons__completions', filter=Q(lessons__completions__liked=True)),
        disliked_count=Count('lessons__completions', filter=Q(lessons__completions__liked=False)),
        no_rating_count=Count('lessons__completions', filter=Q(lessons__completions__liked__isnull=True)),
        with_review_count=Count('lessons__completions', filter=Q(lessons__completions__review_text__isnull=False) & ~Q(lessons__completions__review_text='')),
    ).order_by('title')
    return render(request, 'main/admin/lesson_feedback_stats.html', {
        'courses': courses,
    })


@login_required
def admin_course_lesson_feedback_list(request, course_id):
    """Отзывы по урокам курса: список с возможностью ответить (комментарий администратора) здесь, без Django Admin."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен.")
        return redirect('profile')
    course = get_object_or_404(Course, pk=course_id)
    completions = (
        LessonCompletion.objects
        .filter(lesson__course_id=course_id)
        .select_related('course_purchase__user', 'lesson')
        .order_by('course_purchase__user__username', 'lesson__sort_order', 'completed_at')
    )
    return render(request, 'main/admin/course_lesson_feedback_list.html', {
        'course': course,
        'completions': completions,
    })


@login_required
@require_POST
def admin_lesson_completion_comment(request, completion_id):
    """Сохранить комментарий администратора к отзыву урока и отправить уведомление пользователю."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен.")
        return redirect('profile')
    completion = get_object_or_404(
        LessonCompletion.objects.select_related('lesson', 'course_purchase'),
        pk=completion_id,
    )
    course_id = completion.lesson.course_id
    new_comment = (request.POST.get('admin_comment') or '').strip() or None
    old_comment = (completion.admin_comment or '').strip()
    completion.admin_comment = new_comment
    if new_comment:
        completion.admin_comment_at = timezone.now()
    else:
        completion.admin_comment_at = None
    completion.save(update_fields=['admin_comment', 'admin_comment_at'])
    if new_comment and new_comment != old_comment:
        user = completion.course_purchase.user
        lesson_title = completion.lesson.title or 'Урок'
        msg = f'Администратор ответил на ваш отзыв к уроку «{lesson_title}»: {new_comment[:300]}{"…" if len(new_comment) > 300 else ""}'
        UserNotification.objects.create(user=user, message=msg, lesson_completion=completion)
        messages.success(request, 'Комментарий сохранён, пользователю отправлено уведомление.')
    else:
        messages.success(request, 'Комментарий сохранён.')
    return redirect('admin_course_lesson_feedback_list', course_id=course_id)


@login_required
def admin_refund_list(request):
    """Список заявлений на возврат: на рассмотрении + история (все со статусом и PDF)."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен.")
        return redirect('profile')
    pending = CourseRefundRequest.objects.filter(
        status='pending'
    ).select_related('user', 'course_purchase', 'course_purchase__course').order_by('created_at')
    all_refunds = CourseRefundRequest.objects.filter(
    ).select_related('user', 'course_purchase', 'course_purchase__course', 'processed_by').order_by('-created_at')
    return render(request, 'main/admin/refund_list.html', {
        'refunds': pending,
        'all_refunds': all_refunds,
    })


@login_required
@require_POST
def admin_refund_approve(request, refund_id):
    """Одобрить возврат: списать с баланса организации, зачислить пользователю, снять доступ к курсу, уведомление."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен.")
        return redirect('profile')
    refund = get_object_or_404(
        CourseRefundRequest.objects.select_related('user', 'user__profile', 'course_purchase', 'course_purchase__course'),
        pk=refund_id,
        status='pending',
    )
    amount = refund.amount
    org = OrganizationAccount.get_account()
    if org.balance < amount:
        messages.error(request, f'Недостаточно средств на счёте организации. Требуется {amount} ₽.')
        return redirect('admin_refund_list')
    from django.db import transaction
    refund_number = refund.refund_number
    with transaction.atomic():
        balance_before = org.balance
        tax_reserve_before = org.tax_reserve
        org.balance -= amount
        org.save(update_fields=['balance'])
        OrganizationTransaction.objects.create(
            organization_account=org,
            transaction_type='course_refund',
            amount=amount,
            description=f'Возврат за курс. Заявление {refund_number}',
            course_purchase=refund.course_purchase,
            created_by=request.user,
            balance_before=balance_before,
            balance_after=org.balance,
            tax_reserve_before=tax_reserve_before,
            tax_reserve_after=tax_reserve_before,
        )
        profile, _ = UserProfile.objects.get_or_create(user=refund.user, defaults={'balance': Decimal('0.00')})
        profile.balance += amount
        profile.save(update_fields=['balance'])
        BalanceTransaction.objects.create(
            user=refund.user,
            transaction_type='course_refund',
            amount=amount,
            description=f'Возврат за курс. Заявление {refund_number}',
            course_purchase=refund.course_purchase,
        )
        refund.course_purchase.status = 'refunded'
        refund.course_purchase.save(update_fields=['status'])
        refund.status = 'approved'
        refund.processed_at = timezone.now()
        refund.processed_by = request.user
        refund.save(update_fields=['status', 'processed_at', 'processed_by'])
        course_title = refund.course_purchase.course.title
        UserNotification.objects.create(
            user=refund.user,
            message=f'Деньги за курс «{course_title}» возвращены на ваш баланс. Номер заявления: {refund_number}.',
        )
        _log_activity(
            request.user, 'update', f'refund_{refund.id}',
            f'Одобрен возврат за курс. Заявление {refund_number}, сумма {amount} ₽, пользователь {refund.user.username}',
            request,
        )
    messages.success(request, f'Возврат по заявлению {refund_number} выполнен. Средства зачислены на баланс пользователя.')
    return redirect('admin_refund_list')


@login_required
def admin_refund_pdf(request, refund_id: int):
    """Скачать заявление на возврат в PDF (для администратора — любое заявление)."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен.")
        return redirect('profile')
    refund = get_object_or_404(
        CourseRefundRequest.objects.select_related('user', 'user__profile', 'course_purchase', 'course_purchase__course', 'processed_by'),
        pk=refund_id,
    )
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import io
        import platform
        import os

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        font_name = "Helvetica"
        font_bold = "Helvetica-Bold"
        system = platform.system()
        if system == 'Windows':
            font_dir = r'C:\Windows\Fonts'
            for name in ['arial.ttf', 'Arial.ttf', 'arialuni.ttf']:
                path = os.path.join(font_dir, name)
                if os.path.exists(path):
                    try:
                        pdfmetrics.registerFont(TTFont('Arial', path))
                        font_name = font_bold = 'Arial'
                    except Exception:
                        pass
                    break
        elif system == 'Linux':
            for path in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/TTF/DejaVuSans.ttf']:
                if os.path.exists(path):
                    try:
                        pdfmetrics.registerFont(TTFont('DejaVuSans', path))
                        font_name = font_bold = 'DejaVuSans'
                    except Exception:
                        pass
                    break

        y = height - 20 * mm
        line_height = 6 * mm
        left_margin = 15 * mm

        def draw(text, bold=False, font_size=10):
            nonlocal y
            text_str = str(text)[:90]
            c.setFont(font_bold if bold else font_name, font_size)
            c.drawString(left_margin, y, text_str)
            y -= line_height

        draw('Заявление на возврат средств за курс', bold=True, font_size=14)
        y -= 4 * mm
        draw('—' * 40)
        draw(f'Номер заявления: {refund.refund_number}')
        draw(f'Дата подачи: {refund.created_at.strftime("%d.%m.%Y %H:%M")}')
        applicant_name = refund.user.username
        try:
            if refund.user.profile and getattr(refund.user.profile, 'full_name', None):
                applicant_name = refund.user.profile.full_name
        except Exception:
            pass
        draw(f'Заявитель: {applicant_name}')
        if refund.user.email:
            draw(f'Email: {refund.user.email}')
        draw(f'Курс: {refund.course_purchase.course.title}')
        draw(f'Сумма к возврату: {refund.amount} ₽')
        status_display = dict(CourseRefundRequest.STATUS_CHOICES).get(refund.status, refund.status)
        draw(f'Статус: {status_display}')
        if refund.processed_at:
            draw(f'Дата рассмотрения: {refund.processed_at.strftime("%d.%m.%Y %H:%M")}')
        if refund.processed_by:
            draw(f'Рассмотрено: {refund.processed_by.username}')
        draw('—' * 40)
        y -= 4 * mm
        draw('Документ сформирован в системе MPTCOURSE (панель администратора).', font_size=9)

        c.showPage()
        c.save()
        buffer.seek(0)
        pdf_content = buffer.getvalue()
        buffer.close()

        response = HttpResponse(pdf_content, content_type='application/pdf')
        filename = f"zayavlenie_{refund.refund_number}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("admin_refund_pdf: %s", e)
        messages.error(request, "Не удалось сформировать PDF.")
        return redirect('admin_refund_list')


@login_required
def refund_requests_list(request):
    """Список заявлений на возврат курсов текущего пользователя (история)."""
    refunds = CourseRefundRequest.objects.filter(
        user=request.user
    ).select_related('course_purchase', 'course_purchase__course').order_by('-created_at')
    return render(request, 'profile/refund_requests.html', {
        'refunds': refunds,
    })


@login_required
def refund_request_pdf(request, refund_id: int):
    """Скачать заявление на возврат в PDF (на русском)."""
    refund = get_object_or_404(
        CourseRefundRequest.objects.select_related('user', 'user__profile', 'course_purchase', 'course_purchase__course'),
        pk=refund_id,
        user=request.user,
    )
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import io
        import platform
        import os

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        font_name = "Helvetica"
        font_bold = "Helvetica-Bold"
        system = platform.system()
        if system == 'Windows':
            font_dir = r'C:\Windows\Fonts'
            for name in ['arial.ttf', 'Arial.ttf', 'arialuni.ttf']:
                path = os.path.join(font_dir, name)
                if os.path.exists(path):
                    try:
                        pdfmetrics.registerFont(TTFont('Arial', path))
                        font_name = font_bold = 'Arial'
                    except Exception:
                        pass
                    break
        elif system == 'Linux':
            for path in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/TTF/DejaVuSans.ttf']:
                if os.path.exists(path):
                    try:
                        pdfmetrics.registerFont(TTFont('DejaVuSans', path))
                        font_name = font_bold = 'DejaVuSans'
                    except Exception:
                        pass
                    break

        y = height - 20 * mm
        line_height = 6 * mm
        left_margin = 15 * mm

        def draw(text, bold=False, font_size=10):
            nonlocal y
            text_str = str(text)[:90]
            c.setFont(font_bold if bold else font_name, font_size)
            c.drawString(left_margin, y, text_str)
            y -= line_height

        draw('Заявление на возврат средств за курс', bold=True, font_size=14)
        y -= 4 * mm
        draw('—' * 40)
        draw(f'Номер заявления: {refund.refund_number}')
        draw(f'Дата подачи: {refund.created_at.strftime("%d.%m.%Y %H:%M")}')
        applicant_name = refund.user.username
        try:
            if refund.user.profile and getattr(refund.user.profile, 'full_name', None):
                applicant_name = refund.user.profile.full_name
        except Exception:
            pass
        draw(f'Заявитель: {applicant_name}')
        if refund.user.email:
            draw(f'Email: {refund.user.email}')
        draw(f'Курс: {refund.course_purchase.course.title}')
        draw(f'Сумма к возврату: {refund.amount} ₽')
        status_display = dict(CourseRefundRequest.STATUS_CHOICES).get(refund.status, refund.status)
        draw(f'Статус: {status_display}')
        if refund.processed_at:
            draw(f'Дата рассмотрения: {refund.processed_at.strftime("%d.%m.%Y %H:%M")}')
        if refund.processed_by:
            draw(f'Рассмотрено: {refund.processed_by.username}')
        draw('—' * 40)
        y -= 4 * mm
        draw('Документ сформирован в системе MPTCOURSE.', font_size=9)

        c.showPage()
        c.save()
        buffer.seek(0)
        pdf_content = buffer.getvalue()
        buffer.close()

        response = HttpResponse(pdf_content, content_type='application/pdf')
        filename = f"zayavlenie_{refund.refund_number}.pdf"
        if request.GET.get('download') == '1':
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
        else:
            response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("refund_request_pdf: %s", e)
        messages.error(request, "Не удалось сформировать PDF.")
        return redirect('refund_requests_list')


# =================== АДМИН: КУРСЫ (отдельно от менеджера) ===================

@login_required
def admin_courses_list(request):
    """Список курсов — только панель администратора (доступ: только админ)."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен. Требуется роль администратора.")
        return redirect('profile')
    q = (request.GET.get('q') or '').strip()
    category_id = request.GET.get('category')
    available_filter = request.GET.get('available')
    qs = Course.objects.select_related('category').prefetch_related('images').all()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if category_id:
        qs = qs.filter(category_id=category_id)
    if available_filter == 'yes':
        qs = qs.filter(is_available=True)
    elif available_filter == 'no':
        qs = qs.filter(is_available=False)
    qs = qs.order_by('-added_at')
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    categories = CourseCategory.objects.all()
    return render(request, 'main/admin/courses_list.html', {
        'page_obj': page_obj,
        'q': q,
        'categories': categories,
        'category_id': category_id,
        'available_filter': available_filter,
    })


def _course_add_form_context(categories, request_post=None):
    """Контекст для формы добавления курса (при ошибке — данные из POST)."""
    choices = _content_type_choices()
    form_data = {}
    if request_post:
        for key in request_post:
            val = request_post.get(key)
            if isinstance(val, list) and val:
                form_data[key] = val[0]
            else:
                form_data[key] = val or ''
    return {
        'course': None,
        'categories': categories,
        'content_pages': [],
        'content_type_choices': choices,
        'content_type_choices_json': json.dumps([[str(v), str(l)] for v, l in choices]),
        'form_data': form_data,
    }


@login_required
def admin_course_add(request):
    """Добавление курса — только панель администратора (доступ: только админ)."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен. Требуется роль администратора.")
        return redirect('profile')
    categories = CourseCategory.objects.all()
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        slug = (request.POST.get('slug') or '').strip()
        if not title:
            messages.error(request, 'Введите название курса.')
            return render(request, 'main/admin/course_edit.html', _course_add_form_context(categories, request.POST))
        if not slug:
            from django.utils.text import slugify
            slug = slugify(title)
        if Course.objects.filter(slug=slug).exists():
            messages.error(request, f'Курс с таким slug уже есть: {slug}')
            return render(request, 'main/admin/course_edit.html', _course_add_form_context(categories, request.POST))
        try:
            course = Course.objects.create(
                title=title,
                slug=slug,
                category_id=request.POST.get('category_id') or None,
                description=request.POST.get('description', '').strip() or None,
                included_content=request.POST.get('included_content', '').strip() or None,
                price=Decimal(request.POST.get('price', 0) or 0),
                discount=Decimal(request.POST.get('discount', 0) or 0),
                is_available=request.POST.get('is_available') == 'on',
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception('Ошибка создания курса: %s', e)
            messages.error(request, f'Ошибка при сохранении курса: {e}')
            return render(request, 'main/admin/course_edit.html', _course_add_form_context(categories, request.POST))
        _log_activity(request.user, 'create', f'course_{course.id}', f'Создан курс: {course.title}', request)
        messages.success(request, 'Курс создан. Добавьте уроки ниже.')
        return redirect('admin_course_edit', course_id=course.id)
    return render(request, 'main/admin/course_edit.html', _course_add_form_context(categories))


@login_required
def admin_course_edit(request, course_id):
    """Редактирование курса — только панель администратора (доступ: только админ)."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен. Требуется роль администратора.")
        return redirect('profile')
    course = get_object_or_404(Course, pk=course_id)
    categories = CourseCategory.objects.all()
    content_pages = list(course.content_pages.order_by('sort_order', 'id'))
    content_type_choices = _content_type_choices()
    if request.method == 'POST':
        course.title = request.POST.get('title', '').strip() or course.title
        slug = request.POST.get('slug', '').strip()
        if slug:
            course.slug = slug
        course.category_id = request.POST.get('category_id') or None
        course.description = request.POST.get('description', '').strip() or None
        course.included_content = request.POST.get('included_content', '').strip() or None
        try:
            course.price = Decimal(request.POST.get('price', 0) or 0)
            course.discount = Decimal(request.POST.get('discount', 0) or 0)
        except Exception:
            pass
        course.is_available = request.POST.get('is_available') == 'on'
        course.cover_image_path = request.POST.get('cover_image_path', '').strip() or None
        course.save()
        main_photo = request.FILES.get('main_photo')
        if main_photo:
            try:
                from main.course_content_upload import save_course_cover
                course.cover_image_path = save_course_cover(main_photo, course.id)
                course.save(update_fields=['cover_image_path'])
            except Exception as e:
                messages.error(request, f'Ошибка загрузки главного фото: {e}')
        add_mode = (request.POST.get('add_content_mode') or '').strip()
        next_sort = max([p.sort_order for p in content_pages], default=0) + 1
        content_file = request.FILES.get('content_file')
        if content_file:
            try:
                from main.course_content_upload import create_content_pages_from_upload
                n = create_content_pages_from_upload(course, content_file, next_sort)
                if n > 0:
                    messages.success(request, f'Добавлено страниц контента: {n} (каждая страница/слайд — отдельное модальное окно).')
                else:
                    messages.warning(request, 'Файл загружен, но страниц не создано. Используйте PDF, PPTX или DOCX.')
            except Exception as e:
                messages.error(request, f'Ошибка обработки файла: {getattr(e, "message", str(e))}')
            next_sort += 100
        elif add_mode == 'file':
            messages.warning(request, 'Файл не получен. Выберите файл (PDF, PPTX или DOCX) и нажмите «Сохранить» снова. Если файл большой — проверьте лимит загрузки на сервере.')
        elif add_mode == 'url':
            url = (request.POST.get('content_url') or '').strip()
            video_type = (request.POST.get('add_video_type') or 'youtube').strip().lower()
            if url and video_type in ('youtube', 'rutube'):
                CourseContentPage.objects.create(
                    course=course,
                    sort_order=next_sort,
                    content_type=video_type,
                    file_path=url,
                    title=(request.POST.get('content_url_title') or '').strip() or None,
                )
                messages.success(request, 'Видео добавлено. В курсе оно откроется в модальном окне.')
        content_pages = list(course.content_pages.order_by('sort_order', 'id'))
        for page in content_pages:
            key = str(page.id)
            if request.POST.get('cp_%s_delete' % key):
                page.delete()
                continue
            try:
                sort_order = int(request.POST.get('cp_%s_sort_order' % key, page.sort_order) or 0)
            except (TypeError, ValueError):
                sort_order = page.sort_order or 0
            content_type = (request.POST.get('cp_%s_content_type' % key) or page.content_type or 'pdf_page').strip()
            file_path = (request.POST.get('cp_%s_file_path' % key) or '').strip() or page.file_path
            title = (request.POST.get('cp_%s_title' % key) or '').strip() or None
            page_number = request.POST.get('cp_%s_page_number' % key)
            try:
                page_number = int(page_number) if page_number and str(page_number).strip() else None
            except (TypeError, ValueError):
                page_number = page.page_number
            page.sort_order = sort_order
            page.content_type = content_type
            page.file_path = file_path
            page.title = title or None
            page.page_number = page_number
            page.save()
        try:
            new_count = int(request.POST.get('cp_new_count', 0) or 0)
        except (TypeError, ValueError):
            new_count = 0
        for i in range(new_count):
            content_type = (request.POST.get('cp_new_%s_content_type' % i) or 'pdf_page').strip()
            file_path = (request.POST.get('cp_new_%s_file_path' % i) or '').strip()
            title = (request.POST.get('cp_new_%s_title' % i) or '').strip() or None
            try:
                sort_order = int(request.POST.get('cp_new_%s_sort_order' % i, 999 + i) or 999 + i)
            except (TypeError, ValueError):
                sort_order = 999 + i
            page_number = request.POST.get('cp_new_%s_page_number' % i)
            try:
                page_number = int(page_number) if page_number and str(page_number).strip() else None
            except (TypeError, ValueError):
                page_number = None
            if content_type or file_path or title:
                CourseContentPage.objects.create(
                    course=course,
                    sort_order=sort_order,
                    content_type=content_type or 'pdf_page',
                    file_path=file_path or '',
                    title=title,
                    page_number=page_number,
                )
        _log_activity(request.user, 'update', f'course_{course_id}', f'Обновлен курс: {course.title}', request)
        messages.success(request, 'Курс обновлен.')
        return redirect('admin_course_edit', course_id=course_id)
    return render(request, 'main/admin/course_edit.html', {
        'course': course,
        'categories': categories,
        'content_pages': content_pages,
        'content_type_choices': content_type_choices,
        'content_type_choices_json': json.dumps([[str(v), str(l)] for v, l in content_type_choices]),
        'form_data': {},
    })


@login_required
def admin_course_delete(request, course_id):
    """Удаление курса — только панель администратора (доступ: только админ)."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен. Требуется роль администратора.")
        return redirect('profile')
    course = get_object_or_404(Course, pk=course_id)
    if request.method == 'POST':
        title = course.title
        course.delete()
        _log_activity(request.user, 'delete', f'course_{course_id}', f'Удален курс: {title}', request)
        messages.success(request, f'Курс "{title}" удален.')
        return redirect('admin_courses_list')
    return render(request, 'main/admin/course_delete.html', {'course': course})


@login_required
def admin_lesson_add(request, course_id):
    """Добавить урок (админ)."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен.")
        return redirect('profile')
    course = get_object_or_404(Course, pk=course_id)
    next_order = course.lessons.count() + 1
    if request.method == 'POST':
        title = (request.POST.get('lesson_title') or '').strip() or None
        lesson = Lesson.objects.create(course=course, sort_order=next_order, title=title or f'Урок {next_order}')
        for i in range(LessonPage.MAX_PAGES_PER_LESSON):
            page_type = (request.POST.get(f'page_{i}_type') or 'image').strip()
            file_path = _lesson_page_file_path(request, i, course_id, lesson.id, page_type)
            text = (request.POST.get(f'page_{i}_text') or '').strip() or None
            page_num = request.POST.get(f'page_{i}_page_number')
            page_number = int(page_num) if page_num and str(page_num).strip().isdigit() else None
            page_num_end = request.POST.get(f'page_{i}_page_number_end')
            page_number_end = int(page_num_end) if page_num_end and str(page_num_end).strip().isdigit() else None
            if file_path or text:
                LessonPage.objects.create(
                    lesson=lesson,
                    sort_order=i + 1,
                    page_type=page_type if page_type in ('image', 'video', 'pdf_page') else 'image',
                    file_path=file_path,
                    page_number=page_number,
                    page_number_end=page_number_end,
                    text=text,
                )
        messages.success(request, 'Урок добавлен.')
        return redirect('admin_course_edit', course_id=course_id)
    return render(request, 'main/manager/lesson_edit.html', {
        'course': course,
        'lesson': None,
        'page_slots': [],
        'is_add': True,
        'back_url_name': 'admin_course_edit',
        'back_kwargs': {'course_id': course_id},
    })


@login_required
def admin_lesson_edit(request, course_id, lesson_id):
    """Редактировать урок (админ)."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен.")
        return redirect('profile')
    course = get_object_or_404(Course, pk=course_id)
    lesson = get_object_or_404(Lesson, pk=lesson_id, course=course)
    pages = list(lesson.pages.order_by('sort_order', 'id'))
    if request.method == 'POST':
        lesson.title = (request.POST.get('lesson_title') or '').strip() or None
        lesson.save()
        lesson.pages.all().delete()
        for i in range(LessonPage.MAX_PAGES_PER_LESSON):
            page_type = (request.POST.get(f'page_{i}_type') or 'image').strip()
            file_path = _lesson_page_file_path(request, i, course_id, lesson.id, page_type)
            text = (request.POST.get(f'page_{i}_text') or '').strip() or None
            page_num = request.POST.get(f'page_{i}_page_number')
            page_number = int(page_num) if page_num and str(page_num).strip().isdigit() else None
            page_num_end = request.POST.get(f'page_{i}_page_number_end')
            page_number_end = int(page_num_end) if page_num_end and str(page_num_end).strip().isdigit() else None
            if file_path or text:
                LessonPage.objects.create(
                    lesson=lesson,
                    sort_order=i + 1,
                    page_type=page_type if page_type in ('image', 'video', 'pdf_page') else 'image',
                    file_path=file_path,
                    page_number=page_number,
                    page_number_end=page_number_end,
                    text=text,
                )
        messages.success(request, 'Урок сохранён.')
        return redirect('admin_course_edit', course_id=course_id)
    page_slots = [p for p in pages if p.file_path or p.text]
    return render(request, 'main/manager/lesson_edit.html', {
        'course': course,
        'lesson': lesson,
        'page_slots': page_slots,
        'is_add': False,
        'back_url_name': 'admin_course_edit',
        'back_kwargs': {'course_id': course_id},
    })


@login_required
def admin_course_categories_list(request):
    """Категории курсов — только панель администратора (доступ: только админ)."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен. Требуется роль администратора.")
        return redirect('profile')
    categories = CourseCategory.objects.all().order_by('category_name')
    return render(request, 'main/admin/course_categories_list.html', {'categories': categories})


@login_required
def admin_course_category_add(request):
    """Добавление категории курсов — только панель администратора."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен. Требуется роль администратора.")
        return redirect('profile')
    if request.method == 'POST':
        name = request.POST.get('category_name', '').strip()
        if not name:
            messages.error(request, 'Введите название категории.')
            return redirect('admin_course_category_add')
        category = CourseCategory.objects.create(category_name=name)
        _log_activity(request.user, 'create', f'course_category_{category.id}', f'Создана категория: {category.category_name}', request)
        messages.success(request, 'Категория добавлена.')
        return redirect('admin_course_categories_list')
    return render(request, 'main/admin/course_category_edit.html', {'category': None})


@login_required
def admin_course_category_edit(request, category_id):
    """Редактирование категории курсов — только панель администратора."""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен. Требуется роль администратора.")
        return redirect('profile')
    category = get_object_or_404(CourseCategory, pk=category_id)
    if request.method == 'POST':
        old_name = category.category_name
        category.category_name = request.POST.get('category_name', '').strip() or old_name
        category.save()
        _log_activity(request.user, 'update', f'course_category_{category_id}', f'Обновлена категория: {old_name} -> {category.category_name}', request)
        messages.success(request, 'Категория обновлена.')
        return redirect('admin_course_categories_list')
    return render(request, 'main/admin/course_category_edit.html', {'category': category})


@login_required
def admin_settings(request):
    """Настройки администратора (секретное слово для восстановления БД)"""
    if not _user_is_admin(request.user):
        messages.error(request, "Доступ запрещен. Требуется роль администратора.")
        return redirect('profile')
    
    from django.conf import settings
    import os
    from pathlib import Path
    
    # Получаем текущее значение напрямую из файла (без кэша)
    current_secret = _get_admin_restore_secret()
    
    if request.method == 'POST':
        try:
            new_secret = request.POST.get('admin_restore_secret', '').strip()
            
            if not new_secret:
                messages.error(request, 'Секретное слово не может быть пустым')
                return redirect('admin_settings')
            
            # Обновляем секретное слово в settings.py
            settings_file = Path(settings.BASE_DIR) / 'mptcourse' / 'settings.py'
            
            if not settings_file.exists():
                messages.error(request, 'Файл settings.py не найден')
                return redirect('admin_settings')
            
            # Читаем файл
            with open(settings_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Заменяем значение ADMIN_RESTORE_SECRET
            import re
            # Ищем строку с ADMIN_RESTORE_SECRET
            pattern = r"ADMIN_RESTORE_SECRET\s*=\s*os\.environ\.get\('ADMIN_RESTORE_SECRET',\s*'[^']*'\)"
            replacement = f"ADMIN_RESTORE_SECRET = os.environ.get('ADMIN_RESTORE_SECRET', '{new_secret}')"
            
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
            else:
                # Если паттерн не найден, ищем место для вставки (после комментария о настройках администратора)
                if 'ADMIN_RESTORE_SECRET' not in content:
                    # Ищем место после комментария "# ================== Настройки администратора =================="
                    admin_settings_pattern = r"(# ================== Настройки администратора ==================.*?\n)"
                    if re.search(admin_settings_pattern, content, re.DOTALL):
                        content = re.sub(
                            admin_settings_pattern,
                            r"\1# Секретное слово для восстановления БД (можно изменить через переменную окружения)\nADMIN_RESTORE_SECRET = os.environ.get('ADMIN_RESTORE_SECRET', '" + new_secret + "')\n",
                            content,
                            flags=re.DOTALL
                        )
                    else:
                        # Если секция не найдена, добавляем в конец файла
                        content += f"\n# ================== Настройки администратора ==================\n# Секретное слово для восстановления БД (можно изменить через переменную окружения)\nADMIN_RESTORE_SECRET = os.environ.get('ADMIN_RESTORE_SECRET', '{new_secret}')\n"
            
            # Записываем обратно
            with open(settings_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Значение будет читаться напрямую из файла при следующей проверке
            # Не нужно обновлять settings, так как мы читаем из файла
            
            _log_activity(request.user, 'update', 'admin_settings', f'Обновлено секретное слово для восстановления БД', request)
            messages.success(request, 'Секретное слово успешно обновлено. Изменения применяются сразу, без перезапуска сервера.')
            return redirect('admin_settings')
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении настроек: {str(e)}')
            return redirect('admin_settings')
    
    _log_activity(request.user, 'view', 'admin_settings', 'Просмотр настроек администратора', request)
    
    return render(request, 'main/admin/settings.html', {
        'current_secret': current_secret
    })

@login_required
def management_users_list(request):
    if not _user_is_admin(request.user):
        return redirect('profile')
    from django.contrib.auth.models import User as AuthUser
    q = (request.GET.get('q') or '').strip()
    qs = AuthUser.objects.select_related('profile').all().order_by('-date_joined')
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    roles = Role.objects.all().order_by('role_name')
    return render(request, 'main/management/users_list.html', {
        'page_obj': page_obj, 'q': q, 'roles': roles
    })

@login_required
def management_user_edit(request, user_id: int):
    if not _user_is_admin(request.user):
        return redirect('profile')
    from django.contrib.auth.models import User as AuthUser
    from django.contrib.auth.hashers import make_password
    user = get_object_or_404(AuthUser, pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if request.method == 'POST':
        # Обновление базовых данных пользователя
        user.username = request.POST.get('username', '').strip()
        user.email = request.POST.get('email', '').strip()
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        
        # Обновление пароля (если указан)
        new_password = request.POST.get('password', '').strip()
        if new_password:
            user.set_password(new_password)
        
        user.is_active = request.POST.get('is_active') == 'on'
        user.is_staff = request.POST.get('is_staff') == 'on'
        user.is_superuser = request.POST.get('is_superuser') == 'on'
        user.save()
        
        # Обновление профиля (3НФ: full_name хранится в user.first_name, last_name)
        profile.phone_number = request.POST.get('phone_number', '').strip()
        birth_date_str = request.POST.get('birth_date', '').strip()
        if birth_date_str:
            try:
                from datetime import datetime
                profile.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        balance_str = request.POST.get('balance', '').strip()
        if balance_str:
            try:
                profile.balance = Decimal(balance_str)
            except (ValueError, InvalidOperation):
                pass
        
        # Обновление секретного слова (только если указано)
        secret_word = request.POST.get('secret_word', '').strip()
        if secret_word:
            profile.secret_word = secret_word
        
        role_id = request.POST.get('role_id')
        if role_id:
            try:
                profile.role = Role.objects.get(pk=role_id)
            except Role.DoesNotExist:
                profile.role = None
        else:
            profile.role = None
        
        old_status = profile.user_status
        profile.user_status = 'blocked' if request.POST.get('blocked') == 'on' else 'active'
        profile.save()
        # Также устанавливаем is_active для дополнительной защиты
        user.is_active = (profile.user_status == 'active')
        user.save()
        if old_status != profile.user_status:
            _log_activity(request.user, 'update', f'user_{user_id}', f'Изменен статус пользователя: {old_status} -> {profile.user_status}', request)
        messages.success(request, 'Пользователь обновлен')
        return redirect('management_users_list')
    roles = Role.objects.all().order_by('role_name')
    return render(request, 'main/management/user_edit.html', {'user_obj': user, 'profile': profile, 'roles': roles})

@login_required
def management_user_toggle_block(request, user_id: int):
    if not _user_is_admin(request.user):
        return redirect('profile')
    from django.contrib.auth.models import User as AuthUser
    user = get_object_or_404(AuthUser, pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    old_status = profile.user_status
    profile.user_status = 'active' if profile.user_status == 'blocked' else 'blocked'
    profile.save()
    # Также устанавливаем is_active для дополнительной защиты
    user.is_active = (profile.user_status == 'active')
    user.save()
    _log_activity(request.user, 'update', f'user_{user_id}', f'Изменен статус пользователя: {old_status} -> {profile.user_status}', request)
    messages.success(request, f'Пользователь {"разблокирован" if profile.user_status == "active" else "заблокирован"}')
    return redirect('management_users_list')

@login_required
def management_orders_list(request):
    if not _user_is_admin(request.user):
        return redirect('profile')
    q = (request.GET.get('q') or '').strip()
    qs = Order.objects.select_related('user').all().order_by('-created_at')
    if q:
        qs = qs.filter(Q(id__icontains=q) | Q(user__username__icontains=q) | Q(user__email__icontains=q))
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    return render(request, 'main/management/orders_list.html', {'page_obj': page_obj})

@login_required
def management_order_change_status(request, order_id: int):
    if not _user_is_admin(request.user):
        return redirect('profile')
    order = get_object_or_404(Order, pk=order_id)
    if request.method == 'POST':
        old_status = order.order_status
        new_status = request.POST.get('order_status')
        if new_status in dict(Order.ORDER_STATUSES):
            order.order_status = new_status
            order.save(update_fields=['order_status'])
            
            # Если статус меняется на "доставлен" и оплата была наличными - начисляем на счет организации БЕЗ налога
            if new_status == 'delivered' and old_status != 'delivered':
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"СТАТУС ИЗМЕНЕН НА 'delivered' для заказа #{order.id} (management)")
                
                payment = Payment.objects.filter(order=order).first()
                logger.error(f"Payment для заказа #{order.id}: payment_method={payment.payment_method if payment else 'None'}, payment_status={payment.payment_status if payment else 'None'}, paid_from_balance={order.paid_from_balance}")
                
                # Проверяем, что оплата была наличными (cash) или pending (наличные в обработке)
                # и средства еще не были переведены на счет организации
                is_cash_payment = False
                if payment:
                    if payment.payment_method == 'cash':
                        is_cash_payment = True
                    elif payment.payment_method == 'pending' and not order.paid_from_balance:
                        is_cash_payment = True
                    elif payment.payment_status == 'pending' and payment.payment_method not in ['balance', 'card', 'visa', 'mastercard']:
                        is_cash_payment = True
                
                if is_cash_payment:
                    logger.error(f"Оплата наличными обнаружена для заказа #{order.id}")
                    
                    # Проверяем, не были ли уже переведены средства
                    org_payment_exists = OrganizationTransaction.objects.filter(
                        order=order,
                        transaction_type='order_payment'
                    ).exists()
                    
                    logger.error(f"Транзакция order_payment существует: {org_payment_exists}")
                    
                    if not org_payment_exists:
                        # Начисляем сумму заказа на счет организации, но БЕЗ налога
                        try:
                            org_account = OrganizationAccount.get_account()
                            balance_before = org_account.balance
                            tax_reserve_before = org_account.tax_reserve
                            
                            logger.error(f"Баланс организации до начисления: {balance_before}, сумма заказа: {order.total_amount}")
                            
                            org_account.balance += order.total_amount
                            # НЕ добавляем налог в резерв, так как оплата была наличными
                            org_account.save()
                            
                            logger.error(f"Баланс организации после начисления: {org_account.balance}")
                            
                            OrganizationTransaction.objects.create(
                                organization_account=org_account,
                                transaction_type='order_payment',
                                amount=order.total_amount,
                                description=f'Поступление от заказа #{order.id} (наличные, доставлен)',
                                order=order,
                                created_by=request.user,
                                balance_before=balance_before,
                                balance_after=org_account.balance,
                                tax_reserve_before=tax_reserve_before,
                                tax_reserve_after=tax_reserve_before,
                            )
                            logger.error(f"✅ Транзакция создана для заказа #{order.id}")
                        except Exception as e:
                            import traceback
                            logger.error(f"Ошибка при начислении средств на счет организации для заказа #{order.id}: {str(e)}")
                            logger.error(traceback.format_exc())
                    else:
                        logger.error(f"Транзакция уже существует для заказа #{order.id}, пропускаем начисление")
                else:
                    logger.error(f"Оплата не наличными для заказа #{order.id}: payment_method={payment.payment_method if payment else 'None'}")
            
            # Если статус меняется на "отменен" - обрабатываем отмену заказа
            if new_status == 'cancelled' and old_status != 'cancelled':
                try:
                    _process_order_cancellation(order, request.user)
                    messages.success(request, 'Заказ отменен. Деньги возвращены, товар возвращен на склад.')
                except ValueError as e:
                    messages.error(request, str(e))
                except Exception as e:
                    import traceback
                    logger.error(f"Ошибка при отмене заказа #{order.id}: {str(e)}")
                    logger.error(traceback.format_exc())
                    messages.error(request, f'Ошибка при отмене заказа: {str(e)}')
            
            messages.success(request, 'Статус заказа обновлен')
    return redirect('management_orders_list')

@login_required
def management_analytics_export_csv(request):
    if not _user_is_admin(request.user):
        return redirect('profile')
    import csv
    from django.http import HttpResponse
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sales_report.csv"'
    writer = csv.writer(response)
    writer.writerow(['OrderID', 'User', 'Amount', 'Status', 'Created'])
    for o in Order.objects.select_related('user').all().order_by('-created_at')[:1000]:
        writer.writerow([o.id, o.user.username if o.user else '', o.total_amount, o.order_status, o.created_at.strftime('%Y-%m-%d %H:%M')])
    return response

# ========== Управление промокодами ==========
@login_required
def management_promotions_list(request):
    if not _user_is_admin(request.user):
        return redirect('profile')
    q = (request.GET.get('q') or '').strip()
    qs = Promotion.objects.all().order_by('-start_date', 'promo_code')
    if q:
        qs = qs.filter(Q(promo_code__icontains=q) | Q(promo_description__icontains=q))
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    return render(request, 'main/management/promotions_list.html', {'page_obj': page_obj, 'q': q})

@login_required
def management_promotion_add(request):
    if not _user_is_admin(request.user):
        return redirect('profile')
    if request.method == 'POST':
        promo_code = request.POST.get('promo_code', '').strip().upper()
        promo_description = request.POST.get('promo_description', '').strip()
        discount_str = request.POST.get('discount', '').strip()
        start_date_str = request.POST.get('start_date', '').strip()
        end_date_str = request.POST.get('end_date', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        
        if not promo_code:
            messages.error(request, 'Код промокода обязателен')
            return redirect('management_promotion_add')
        
        try:
            discount = Decimal(discount_str) if discount_str else Decimal('0')
        except (ValueError, InvalidOperation):
            discount = Decimal('0')
        
        start_date = None
        end_date = None
        if start_date_str:
            try:
                from datetime import datetime
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if end_date_str:
            try:
                from datetime import datetime
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        Promotion.objects.create(
            promo_code=promo_code,
            promo_description=promo_description,
            discount=discount,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active
        )
        messages.success(request, 'Промокод создан')
        return redirect('management_promotions_list')
    return render(request, 'main/management/promotion_edit.html', {'promotion': None})

@login_required
def management_promotion_edit(request, promo_id: int):
    if not _user_is_admin(request.user):
        return redirect('profile')
    promotion = get_object_or_404(Promotion, pk=promo_id)
    if request.method == 'POST':
        promotion.promo_code = request.POST.get('promo_code', '').strip().upper()
        promotion.promo_description = request.POST.get('promo_description', '').strip()
        discount_str = request.POST.get('discount', '').strip()
        start_date_str = request.POST.get('start_date', '').strip()
        end_date_str = request.POST.get('end_date', '').strip()
        promotion.is_active = request.POST.get('is_active') == 'on'
        
        try:
            promotion.discount = Decimal(discount_str) if discount_str else Decimal('0')
        except (ValueError, InvalidOperation):
            pass
        
        promotion.start_date = None
        promotion.end_date = None
        if start_date_str:
            try:
                from datetime import datetime
                promotion.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if end_date_str:
            try:
                from datetime import datetime
                promotion.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        
        promotion.save()
        messages.success(request, 'Промокод обновлен')
        return redirect('management_promotions_list')
    return render(request, 'main/management/promotion_edit.html', {'promotion': promotion})

@login_required
def management_promotion_delete(request, promo_id: int):
    if not _user_is_admin(request.user):
        return redirect('profile')
    promotion = get_object_or_404(Promotion, pk=promo_id)
    if request.method == 'POST':
        promotion.delete()
        messages.success(request, 'Промокод удален')
        return redirect('management_promotions_list')
    return render(request, 'main/management/promotion_delete.html', {'promotion': promotion})
@login_required
def receipts_list(request):
    receipts = Receipt.objects.filter(user=request.user).select_related('order').order_by('-created_at')
    return render(request, 'profile/receipts.html', {'receipts': receipts})

@login_required
@require_POST
def validate_promo(request):
    """AJAX: проверить промокод и вернуть сумму скидки и итоги"""
    code = (request.POST.get('promo_code') or '').strip().upper()
    if not code:
        return JsonResponse({'success': False, 'error': 'Укажите промокод'}, status=400)
    cart = Cart.objects.filter(user=request.user).first()
    # УДАЛЕНО: проверка пустой корзины
    try:
        promo = Promotion.objects.get(promo_code=code)
        # Проверяем активность промокода
        if not promo.is_active:
            return JsonResponse({'success': False, 'error': 'Промокод неактивен'}, status=400)
        from django.utils import timezone
        today = timezone.now().date()
        if promo.start_date and promo.start_date > today:
            return JsonResponse({'success': False, 'error': 'Промокод еще не действует'}, status=400)
        if promo.end_date and promo.end_date < today:
            return JsonResponse({'success': False, 'error': 'Промокод истек'}, status=400)
        
        # Проверяем, использовал ли пользователь уже этот промокод
        if PromoUsage.objects.filter(user=request.user, promotion=promo).exists():
            return JsonResponse({'success': False, 'error': 'Вы уже использовали этот промокод'}, status=400)
        
        cart_total = cart.total_price()
        delivery_cost = Decimal('1000.00')
        discount_amount = (cart_total * (promo.discount / Decimal('100'))).quantize(Decimal('0.01'))
        subtotal_after_discount = cart_total - discount_amount
        pre_vat = subtotal_after_discount + delivery_cost  # Товары - скидка + доставка
        vat_rate = Decimal('20.00')
        vat_amount = (pre_vat * vat_rate / Decimal('100')).quantize(Decimal('0.01'))
        total = (pre_vat + vat_amount).quantize(Decimal('0.01'))
        return JsonResponse({
            'success': True,
            'promo': {'code': promo.promo_code, 'discount_percent': str(promo.discount)},
            'discount': float(discount_amount),
            'discount_percent': str(promo.discount),
            'vat_amount': float(vat_amount),
            'total': float(total),
            'delivery': float(delivery_cost)
        })
    except Promotion.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Неверный промокод'}, status=404)

@login_required
def receipt_view(request, receipt_id: int):
    """Редирект на PDF чека — открывается в стандартном просмотрщике браузера (как на скрине)."""
    get_object_or_404(Receipt, id=receipt_id, user=request.user)
    from django.urls import reverse
    return redirect(reverse('receipt_pdf', args=[receipt_id]))


@login_required
def receipt_pdf(request, receipt_id: int):
    receipt = get_object_or_404(Receipt, id=receipt_id, user=request.user)
    config = ReceiptConfig.objects.first() or ReceiptConfig.objects.create()

    # Генерируем PDF через reportlab
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.colors import black
        import io

        # Создаем буфер для PDF
        buffer = io.BytesIO()

        # Создаем PDF canvas
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # Используем TTF шрифт с поддержкой кириллицы
        # Пытаемся использовать системные шрифты Windows или загрузить TTF
        font_name = "Helvetica"
        font_bold = "Helvetica-Bold"
        
        # Пытаемся использовать системные шрифты с поддержкой кириллицы
        try:
            import platform
            import os
            
            system = platform.system()
            arial_found = False
            
            # Для Windows используем системные шрифты
            if system == 'Windows':
                font_dir = r'C:\Windows\Fonts'
                
                # Список возможных путей к Arial (разные версии Windows могут иметь разные имена)
                arial_variants = [
                    'arial.ttf',
                    'Arial.ttf',
                    'ARIAL.TTF',
                    'arialuni.ttf',  # Arial Unicode MS (полная поддержка Unicode)
                ]
                
                arial_bold_variants = [
                    'arialbd.ttf',
                    'Arialbd.ttf',
                    'ARIALBD.TTF',
                    'arialbi.ttf',  # Arial Bold Italic
                ]
                
                # Пробуем найти и зарегистрировать Arial
                for variant in arial_variants:
                    arial_path = os.path.join(font_dir, variant)
                    if os.path.exists(arial_path):
                        try:
                            pdfmetrics.registerFont(TTFont('Arial', arial_path))
                            font_name = 'Arial'
                            arial_found = True
                            break
                        except Exception:
                            continue
                
                # Пробуем найти и зарегистрировать Arial Bold
                if arial_found:
                    for variant in arial_bold_variants:
                        arial_bold_path = os.path.join(font_dir, variant)
                        if os.path.exists(arial_bold_path):
                            try:
                                pdfmetrics.registerFont(TTFont('Arial-Bold', arial_bold_path))
                                font_bold = 'Arial-Bold'
                                break
                            except Exception:
                                pass
                    # Если не нашли жирный, используем обычный Arial
                    if font_bold == 'Helvetica-Bold':
                        font_bold = 'Arial'
            
            # Для Linux пробуем использовать системные шрифты
            elif system == 'Linux':
                # Список возможных путей к DejaVu шрифтам
                dejavu_fonts = [
                    ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
                    ('/usr/share/fonts/TTF/DejaVuSans.ttf', '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf'),
                    ('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'),
                ]
                
                for regular_path, bold_path in dejavu_fonts:
                    if os.path.exists(regular_path):
                        try:
                            pdfmetrics.registerFont(TTFont('DejaVuSans', regular_path))
                            font_name = 'DejaVuSans'
                            arial_found = True
                            
                            # Пробуем загрузить жирный шрифт
                            if os.path.exists(bold_path):
                                try:
                                    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', bold_path))
                                    font_bold = 'DejaVuSans-Bold'
                                except Exception:
                                    font_bold = 'DejaVuSans'
                            else:
                                font_bold = 'DejaVuSans'
                            break
                        except Exception as e:
                            continue
            
            # Для macOS пробуем использовать системные шрифты
            elif system == 'Darwin':
                font_dirs = [
                    '/System/Library/Fonts/Helvetica.ttc',
                    '/Library/Fonts/Arial.ttf',
                ]
                for font_path in font_dirs:
                    if os.path.exists(font_path):
                        try:
                            pdfmetrics.registerFont(TTFont('Arial', font_path))
                            font_name = 'Arial'
                            font_bold = 'Arial'
                            arial_found = True
                            break
                        except Exception:
                            continue
                            
        except Exception as e:
            # Если не получилось, используем стандартные шрифты
            # В этом случае кириллица может не отображаться
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Не удалось загрузить шрифт с поддержкой кириллицы: {e}")
            arial_found = False
        
        # Проверяем, что шрифт загружен правильно
        try:
            if not arial_found:
                import logging
                logger = logging.getLogger(__name__)
                logger.error("Не удалось загрузить шрифт с поддержкой кириллицы! PDF может содержать некорректные символы.")
                # Пробуем принудительно загрузить DejaVu для Linux
                if platform.system() == 'Linux':
                    try:
                        dejavu_paths = [
                            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                            '/usr/share/fonts/TTF/DejaVuSans.ttf',
                        ]
                        for path in dejavu_paths:
                            if os.path.exists(path):
                                pdfmetrics.registerFont(TTFont('DejaVuSans', path))
                                font_name = 'DejaVuSans'
                                font_bold = 'DejaVuSans'
                                arial_found = True
                                logger.info(f"Успешно загружен шрифт: {path}")
                                break
                    except Exception as e2:
                        logger.error(f"Критическая ошибка загрузки шрифта: {e2}")
        except NameError:
            # Если arial_found не определена, пробуем загрузить шрифт
            import platform
            import os
            if platform.system() == 'Linux':
                try:
                    dejavu_paths = [
                        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                        '/usr/share/fonts/TTF/DejaVuSans.ttf',
                    ]
                    for path in dejavu_paths:
                        if os.path.exists(path):
                            pdfmetrics.registerFont(TTFont('DejaVuSans', path))
                            font_name = 'DejaVuSans'
                            font_bold = 'DejaVuSans'
                            break
                except Exception:
                    pass

        y = height - 20 * mm
        line_height = 6 * mm
        left_margin = 15 * mm

        def draw(text: str, bold: bool = False, font_size: int = 10):
            nonlocal y
            try:
                # Преобразуем текст в строку и убеждаемся что это Unicode
                text_str = str(text)
                
                # Устанавливаем шрифт с поддержкой кириллицы
                current_font = font_bold if bold else font_name
                c.setFont(current_font, font_size)
                
                # Проверяем длину строки и разбиваем если нужно
                max_width = width - (left_margin * 2)
                # Простая проверка - если текст слишком длинный, обрезаем
                if len(text_str) > 80:
                    text_str = text_str[:77] + "..."
                
                # Используем drawString - он поддерживает Unicode при правильном шрифте
                c.drawString(left_margin, y, text_str)
                y -= line_height
            except Exception as e:
                # Если ошибка, пробуем использовать стандартный шрифт
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Ошибка при отрисовке текста '{text_str[:50]}': {e}")
                try:
                    # Пробуем с обычным шрифтом
                    c.setFont(font_name, font_size)
                    c.drawString(left_margin, y, str(text)[:50])
                    y -= line_height
                except:
                    # В крайнем случае просто пропускаем
                    y -= line_height

        # Заголовок
        draw(str(config.company_name or "Магазин"), bold=True, font_size=14)
        draw(f"ИНН: {str(config.company_inn or '')}")
        draw(f"Адрес: {str(config.company_address or '')}")
        draw(f"Кассир: {str(config.cashier_name or '')}")
        draw(f"Смена № {str(config.shift_number or '')}")
        
        y -= 3 * mm
        draw("─" * 50)
        y -= 2 * mm
        
        draw(f"Чек № {receipt.number or receipt.id}", bold=True)
        draw(f"Дата: {receipt.created_at.strftime('%d.%m.%Y')}")
        draw(f"Время: {receipt.created_at.strftime('%H:%M')}")

        y -= 3 * mm
        draw("Товары:", bold=True)
        draw("─" * 50)

        # Товары
        for item in receipt.items.all():
            product_name = str(item.product_name or 'Товар')
            # Обрезаем длинные названия
            if len(product_name) > 40:
                product_name = product_name[:37] + "..."
            
            draw(f"{product_name}")
            draw(f"  {item.quantity} шт. x {item.unit_price} ₽ = {item.line_total} ₽")
            if item.vat_amount:
                draw(f"  НДС {receipt.vat_rate}%: {item.vat_amount} ₽")
        y -= 2 * mm

        y -= 2 * mm
        draw("─" * 50)
        
        # Показываем промокод, если есть
        if receipt.order and receipt.order.promo_code:
            draw(f"Промокод: {receipt.order.promo_code.promo_code} (-{receipt.discount_amount} ₽)", bold=True)
            y -= 2 * mm
        
        # Показываем суммы
        if receipt.subtotal:
            draw(f"Товары: {receipt.subtotal} ₽")
        if receipt.delivery_cost:
            draw(f"Доставка: {receipt.delivery_cost} ₽")
        if receipt.discount_amount:
            draw(f"Скидка: -{receipt.discount_amount} ₽")
        
        # Рассчитываем итоговую сумму
        total = Decimal('0.00')
        if receipt.subtotal:
            total += Decimal(str(receipt.subtotal))
        if receipt.delivery_cost:
            total += Decimal(str(receipt.delivery_cost))
        if receipt.discount_amount:
            total -= Decimal(str(receipt.discount_amount))
        
        draw("─" * 50)
        draw(f"Итого: {total} ₽", bold=True, font_size=12)
        draw(f"В том числе НДС {receipt.vat_rate}%: {receipt.vat_amount} ₽")
        
        y -= 3 * mm
        payment_label = "Наличные" if receipt.payment_method == 'cash' else ("СБП" if receipt.payment_method == 'sbp' else ("С баланса" if receipt.payment_method == 'balance' else "Банковская карта"))
        draw("Оплата:", bold=True)
        draw(f"{payment_label}: {receipt.total_amount} ₽")

        y -= 3 * mm
        draw("Спасибо за покупку!", bold=True)
        
        if config.site_fns:
            draw(f"Сайт ФНС: {str(config.site_fns)}")
        if config.kkt_rn:
            draw(f"РН ККТ: {str(config.kkt_rn)}")
        if config.kkt_sn:
            draw(f"ЗН ККТ: {str(config.kkt_sn)}")
        if config.fn_number:
            draw(f"ФН: {str(config.fn_number)}")

        # Завершаем страницу
        c.showPage()
        c.save()
        
        # Получаем PDF из буфера
        buffer.seek(0)
        pdf_content = buffer.getvalue()
        buffer.close()

        # Создаем HTTP ответ с правильными заголовками
        response = HttpResponse(pdf_content, content_type='application/pdf')
        filename = f"receipt_{receipt.id}.pdf"
        # Используем inline для просмотра в браузере, attachment для скачивания
        # Можно добавить параметр ?download=1 для принудительного скачивания
        if request.GET.get('download') == '1':
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
        else:
            response['Content-Disposition'] = f'inline; filename="{filename}"'
        
        return response
        
    except ImportError:
        # Если reportlab не установлен в виртуальном окружении,
        # возвращаем HTML-версию чека (как fallback), чтобы пользователь всё равно мог его открыть/распечатать.
        html = render_to_string('profile/receipt_fallback.html', {
            'receipt': receipt,
            'config': config,
        })
        return HttpResponse(html, content_type='text/html')
    except Exception as e:
        # Логируем ошибку для отладки
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка генерации PDF: {str(e)}")
        
        # Fallback: возвращаем HTML с возможностью печати
        html = render_to_string('profile/receipt_fallback.html', {
            'receipt': receipt,
            'config': config,
        })
        response = HttpResponse(html, content_type='text/html')
        return response

@login_required
def add_to_cart_course(request, course_id):
    """Добавить курс в корзину (MPTCOURSE). Курс в корзине только в одном экземпляре. Нельзя добавить уже купленный курс."""
    if request.method != "POST":
        return JsonResponse({'success': False, 'message': 'Метод не поддерживается'}, status=405)
    course = get_object_or_404(Course, id=course_id, is_available=True)
    if CoursePurchase.objects.filter(user=request.user, course=course, status='paid').exists():
        return JsonResponse({'success': False, 'message': 'Вы уже купили этот курс. Нельзя купить его повторно.'}, status=400)
    cart, _ = Cart.objects.get_or_create(user=request.user)
    item, created = CartItem.objects.get_or_create(
        cart=cart,
        course=course,
        defaults={'unit_price': course.final_price, 'quantity': 1}
    )
    if not created:
        # Курс уже в корзине — оставляем количество 1, только обновляем цену
        item.quantity = 1
        item.unit_price = course.final_price
        item.save()
    return JsonResponse({
        'success': True,
        'cart_count': cart.items.count(),
        'course': {
            'id': course.id,
            'title': course.title,
            'price': str(course.final_price),
        }
    })


@login_required
def add_to_cart(request, product_id):
    """Добавить в корзину по course_id (URL по-прежнему product_id для совместимости с каталогом)."""
    return add_to_cart_course(request, product_id)


@login_required
def remove_from_cart(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    item.delete()
    return redirect('cart')


@login_required
def update_cart_quantity(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    # Курсы — всегда 1 шт в корзине, количество менять нельзя
    if item.course_id:
        new_qty = 1
    else:
        new_qty = max(1, int(request.POST.get('quantity', 1)))
        if getattr(item, 'size', None):
            if item.size.size_stock < new_qty:
                error_msg = f'Недостаточно на складе. Доступно: {item.size.size_stock}'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': error_msg}, status=400)
                messages.error(request, error_msg)
                return redirect('cart')
        elif getattr(item, 'product', None) and item.product.stock_quantity < new_qty:
            error_msg = f'Недостаточно на складе. Доступно: {item.product.stock_quantity}'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('cart')
    
    item.quantity = new_qty
    item.save()
    
    # Если это AJAX запрос, возвращаем JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True, 
            'subtotal': float(item.subtotal()), 
            'total': float(item.cart.total_price())
        })
    
    # Иначе редирект
    messages.success(request, "Количество обновлено.")
    return redirect('cart')

@login_required
def checkout(request):
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        cart = Cart.objects.filter(user=request.user).prefetch_related('items', 'items__course').first()
        logger.info(f'Checkout: пользователь {request.user.id} ({request.user.username}), корзина найдена: {cart is not None}')
        
        if not cart:
            logger.warning(f'Checkout: корзина не найдена для пользователя {request.user.id} ({request.user.username})')
            messages.warning(request, "Ваша корзина пуста.")
            return redirect('cart')
        
        items = list(cart.items.select_related('course', 'course__category').all())
        items_count = len(items)
        logger.info(f'Checkout: количество позиций в корзине: {items_count} для пользователя {request.user.username}')
        
        for item in items:
            logger.info(f'  - Позиция ID {item.id}: course_id={item.course_id}, course={item.course.title if item.course else "None"}, quantity={item.quantity}')
        
        invalid_items = [item.id for item in items if not item.course]
        if invalid_items:
            logger.error(f'Checkout: найдены невалидные позиции: {invalid_items}')
            messages.error(request, "В корзине есть удалённые курсы. Пожалуйста, очистите корзину.")
            return redirect('cart')
        
        logger.info(f'Checkout: все проверки пройдены, отображаем страницу для пользователя {request.user.id} ({request.user.username})')
    except Exception as e:
        import traceback
        logger.error(f'Ошибка при загрузке корзины в checkout для пользователя {request.user.id}: {str(e)}\n{traceback.format_exc()}')
        messages.error(request, "Ошибка при загрузке корзины. Пожалуйста, попробуйте позже.")
        return redirect('cart')

    # Если форма оформления заказа отправлена
    # ВАЖНО: Заказы создаются через API (/api/orders/), а не через обычный POST
    # Поэтому игнорируем POST запросы, которые не являются реальной отправкой формы
    # (например, при изменении способа оплаты форма не должна отправляться)
    if request.method == 'POST':
        # Проверяем, что это реальная отправка формы для создания заказа
        # Если есть только payment_method без других данных - это просто изменение способа оплаты
        payment_method = request.POST.get('payment_method')
        address_id = request.POST.get('address_id')
        submit_button = request.POST.get('submit') or request.POST.get('create_order')
        
        # Если это просто изменение способа оплаты (есть только payment_method, нет address_id и submit)
        if payment_method and not address_id and not submit_button:
            # Это просто изменение способа оплаты, не обрабатываем как POST запрос
            # Просто редиректим обратно на страницу checkout
            return redirect('checkout')
        
        # Это реальная отправка формы для создания заказа (старый способ, через обычный POST)
        # Но лучше использовать API, поэтому просто редиректим обратно
        # Оставляем эту логику для обратной совместимости, но она не должна использоваться
        address_id = request.POST.get('address_id')
        saved_payment_id = request.POST.get('saved_payment_id')
        promo_code = request.POST.get('promo_code', '').strip()
        
        # Данные новой карты (если не используется сохраненная)
        card_number = request.POST.get('card_number', '').strip()
        card_holder_name = request.POST.get('card_holder_name', '').strip()
        expiry_month = request.POST.get('expiry_month', '').strip()
        expiry_year = request.POST.get('expiry_year', '').strip()
        save_card = request.POST.get('save_card') == 'on'

        # Онлайн-курсы: адрес доставки не нужен
        address = None
        if address_id:
            try:
                address = UserAddress.objects.get(id=address_id, user=request.user)
            except UserAddress.DoesNotExist:
                pass

        cart_items = list(cart.items.select_related('course').all())
        if not cart_items:
            logger.error(f'Checkout POST: попытка создать заказ без позиций для пользователя {request.user.id}')
            messages.error(request, "Невозможно создать заказ: корзина пуста.")
            return redirect('checkout')
        
        valid_cart_items = [item for item in cart_items if item.course]
        if not valid_cart_items:
            logger.error(f'Checkout POST: в корзине нет валидных курсов для пользователя {request.user.id}')
            messages.error(request, "Невозможно создать заказ: в корзине нет валидных курсов.")
            return redirect('checkout')
        
        cart_items = valid_cart_items

        # Проверка промокода
        promo = None
        discount_amount = Decimal('0')
        if promo_code:
            try:
                promo = Promotion.objects.get(promo_code=promo_code.upper(), is_active=True)
                # Проверяем даты действия промокода
                from django.utils import timezone
                today = timezone.now().date()
                if promo.start_date and promo.start_date > today:
                    messages.error(request, "Промокод еще не действует.")
                    return redirect('checkout')
                if promo.end_date and promo.end_date < today:
                    messages.error(request, "Промокод истек.")
                    return redirect('checkout')
                # Вычисляем скидку
                cart_total = cart.total_price()
                discount_amount = cart_total * (promo.discount / Decimal('100'))
            except Promotion.DoesNotExist:
                messages.error(request, "Неверный промокод.")
                return redirect('checkout')

        # Итог: курсы без доставки
        cart_total = cart.total_price()
        delivery_cost = Decimal('0.00')
        subtotal_after_discount = cart_total - discount_amount
        pre_vat_amount = subtotal_after_discount + delivery_cost
        vat_rate = Decimal('20.00')
        vat_amount = (pre_vat_amount * vat_rate / Decimal('100')).quantize(Decimal('0.01'))
        
        # Налог на прибыль 13% рассчитывается с суммы после НДС
        amount_after_vat = pre_vat_amount + vat_amount
        tax_rate = Decimal('13.00')
        tax_amount = (amount_after_vat * tax_rate / Decimal('100')).quantize(Decimal('0.01'))
        
        final_amount = amount_after_vat.quantize(Decimal('0.01'))

        # Проверяем способ оплаты
        payment_method = request.POST.get('payment_method', 'sbp')  # sbp, card или balance
        paid_from_balance = False
        
        # Если оплата с баланса
        if payment_method == 'balance':
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            if profile.balance < final_amount:
                messages.error(request, f"Недостаточно средств на балансе. Текущий баланс: {profile.balance} ₽, требуется: {final_amount} ₽")
                return redirect('checkout')
            paid_from_balance = True

        # ЖЕСТКАЯ ПРОВЕРКА ПЕРЕД СОЗДАНИЕМ ЗАКАЗА: товары должны быть
        if not cart_items or len(cart_items) == 0:
            logger.error(f'Checkout POST: КРИТИЧЕСКАЯ ОШИБКА - попытка создать заказ без товаров!')
            messages.error(request, "Невозможно создать заказ: нет товаров в корзине.")
            return redirect('checkout')
        
        # Проверяем пользователя
        if not request.user or not request.user.is_authenticated:
            logger.error(f'Checkout POST: КРИТИЧЕСКАЯ ОШИБКА - пользователь не авторизован!')
            messages.error(request, "Вы должны быть авторизованы для создания заказа.")
            return redirect('login')

        # Вся логика оформления в транзакции
        with transaction.atomic():
            # ЖЕСТКАЯ ПРОВЕРКА: товары должны быть перед созданием заказа
            if not cart_items or len(cart_items) == 0:
                logger.error(f'Checkout POST: 🚨 КРИТИЧЕСКАЯ ОШИБКА - нет товаров перед созданием заказа!')
                messages.error(request, "Невозможно создать заказ: нет товаров в корзине.")
                return redirect('checkout')
            
            prepared_items = []
            for item in cart_items:
                if not item.course:
                    continue
                prepared_items.append({
                    'course': item.course,
                    'quantity': item.quantity,
                    'unit_price': item.unit_price,
                })
            
            if not prepared_items:
                logger.error(f'Checkout POST: нет подготовленных позиций.')
                messages.error(request, "Невозможно создать заказ: нет курсов в корзине.")
                return redirect('checkout')
            
            logger.info(f'Checkout POST: Подготовлено {len(prepared_items)} курсов, создаем заказ...')
            
            # ТОЛЬКО ТЕПЕРЬ создаем заказ - после проверки всех товаров
            order = None
            try:
                order = Order.objects.create(
                user=request.user,
                address=address,
                total_amount=final_amount,
                delivery_cost=delivery_cost,
                promo_code=promo,
                discount_amount=discount_amount,
                vat_rate=vat_rate,
                tax_rate=tax_rate,
                paid_from_balance=paid_from_balance,
                order_status='delivered'
            )
                logger.error(f'Checkout POST: Заказ создан #{order.id}')
            except Exception as order_error:
                logger.error(f'Checkout POST: Ошибка при создании заказа: {order_error}')
                messages.error(request, f"Ошибка при создании заказа: {str(order_error)}")
                return redirect('checkout')
            
            # Проверяем, что заказ создан
            if not order:
                logger.error(f'Checkout POST: Заказ не создан!')
                messages.error(request, "Ошибка при создании заказа.")
                return redirect('checkout')

            # Обработка способа оплаты
            saved_payment = None
            payment_method_type = 'cash'
            payment_status = 'pending'
            
            if payment_method in ('cash', 'sbp'):
                payment_method_type = 'sbp' if payment_method == 'sbp' else 'cash'
                payment_status = 'pending'
            elif payment_method == 'balance':
                payment_method_type = 'balance'
                payment_status = 'paid'
                
                # Списываем с баланса
                profile, _ = UserProfile.objects.select_for_update().get_or_create(user=request.user)
                if profile.balance < final_amount:
                    order.delete()
                    messages.error(request, f"Недостаточно средств на балансе. Текущий баланс: {profile.balance} ₽, требуется: {final_amount} ₽")
                    return redirect('checkout')
                balance_before = profile.balance
                profile.balance -= final_amount
                profile.save()
                
                # Создаем транзакцию
                BalanceTransaction.objects.create(
                    user=request.user,
                    transaction_type='order_payment',
                    amount=final_amount,
                    description=f'Оплата заказа #{order.id}',
                    order=order,
                    status='completed'
                )
            elif payment_method == 'card':
                payment_status = 'paid'
                # Используем сохраненную карту
                if saved_payment_id and saved_payment_id != '':
                    saved_payment = SavedPaymentMethod.objects.select_for_update().get(id=saved_payment_id, user=request.user)
                    payment_method_type = saved_payment.card_type or 'card'
                    if saved_payment.balance < final_amount:
                        order.delete()
                        messages.error(request, f"Недостаточно средств на выбранной карте. Баланс карты: {saved_payment.balance} ₽, требуется: {final_amount} ₽")
                        return redirect('checkout')
                    # Списываем (проверяем, что баланс не станет отрицательным)
                    new_card_balance = saved_payment.balance - final_amount
                    if new_card_balance < 0:
                        order.delete()
                        messages.error(request, f"Недостаточно средств на выбранной карте. Баланс карты: {saved_payment.balance} ₽, требуется: {final_amount} ₽")
                        return redirect('checkout')
                    saved_payment.balance = new_card_balance
                    saved_payment.save()
                    # Фиксируем транзакцию по карте
                    CardTransaction.objects.create(
                        saved_payment_method=saved_payment,
                        transaction_type='withdrawal',
                        amount=final_amount,
                        description=f'Оплата заказа #{order.id}',
                        status='completed'
                    )
                # Новая карта: разрешаем только если карта будет сохранена и на ней достаточно средств
                elif card_number and card_holder_name and expiry_month and expiry_year:
                    payment_method_type = 'visa' if card_number.startswith('4') else 'mastercard' if card_number.startswith('5') else 'card'
                    if save_card:
                        card_type = payment_method_type
                        card_last_4 = card_number[-4:] if len(card_number) >= 4 else card_number
                        is_default = not SavedPaymentMethod.objects.filter(user=request.user).exists()
                        saved_payment = SavedPaymentMethod.objects.create(
                            user=request.user,
                            card_number=card_last_4,
                            card_holder_name=card_holder_name,
                            expiry_month=expiry_month,
                            expiry_year=expiry_year,
                            card_type=card_type,
                            is_default=is_default
                        )
                        if saved_payment.balance < final_amount:
                            order.delete()
                            messages.error(request, f"Недостаточно средств на карте. Баланс карты: {saved_payment.balance} ₽, требуется: {final_amount} ₽")
                            return redirect('checkout')
                        # Списываем (проверяем, что баланс не станет отрицательным)
                        new_card_balance = saved_payment.balance - final_amount
                        if new_card_balance < 0:
                            order.delete()
                            messages.error(request, f"Недостаточно средств на карте. Баланс карты: {saved_payment.balance} ₽, требуется: {final_amount} ₽")
                            return redirect('checkout')
                        saved_payment.balance = new_card_balance
                        saved_payment.save()
                        CardTransaction.objects.create(
                            saved_payment_method=saved_payment,
                            transaction_type='withdrawal',
                            amount=final_amount,
                            description=f'Оплата заказа #{order.id}',
                            status='completed'
                        )
                    else:
                        order.delete()
                        messages.error(request, "Для оплаты новой картой сначала сохраните карту и убедитесь в наличии средств.")
                        return redirect('checkout')
                else:
                    order.delete()
                    messages.error(request, "Пожалуйста, выберите или введите данные карты.")
                    return redirect('checkout')
            
            # Создаем запись о платеже
            payment = Payment.objects.create(
                order=order,
                payment_method=payment_method_type,
                payment_amount=final_amount,
                payment_status=payment_status,
                saved_payment_method=saved_payment,
                promo_code=promo
            )

            # Если платеж прошел (balance или card), переводим заказ в 'delivered'
            if payment_status == 'paid' and order.order_status != 'delivered':
                order.order_status = 'delivered'
                order.save(update_fields=['order_status'])
            
            # Переводим средства на счет организации (если платеж прошел, но не наличными)
            # Наличные оплачиваются при получении, поэтому средства переводятся позже
            if payment_status == 'paid' and payment_method not in ('cash', 'sbp'):
                org_account = OrganizationAccount.get_account()
                balance_before = org_account.balance
                tax_reserve_before = org_account.tax_reserve
                org_account.balance += final_amount
                org_account.tax_reserve += tax_amount
                org_account.save()
                OrganizationTransaction.objects.create(
                    organization_account=org_account,
                    transaction_type='order_payment',
                    amount=final_amount,
                    description=f'Поступление от заказа #{order.id}',
                    order=order,
                    created_by=request.user,
                    balance_before=balance_before,
                    balance_after=org_account.balance,
                    tax_reserve_before=tax_reserve_before,
                    tax_reserve_after=org_account.tax_reserve,
                )

            created_order_items = []
            payment_method_val = request.POST.get('payment_method', 'card')
            cp_method = 'balance' if payment_method_val == 'balance' else ('card' if payment_method_val == 'card' else 'sbp')
            
            for idx, item_data in enumerate(prepared_items):
                if not item_data.get('course'):
                    continue
                try:
                    order_item = OrderItem.objects.create(
                        order=order,
                        course=item_data['course'],
                        quantity=item_data['quantity'],
                        unit_price=item_data['unit_price'],
                    )
                    created_order_items.append(order_item)
                    # Доступ к курсу: по одному CoursePurchase на каждую единицу quantity; не создаём дубликаты для уже купленных курсов
                    existing_count = CoursePurchase.objects.filter(
                        user=request.user, course=item_data['course'], status='paid'
                    ).count()
                    to_create = max(0, item_data['quantity'] - existing_count)
                    for _ in range(to_create):
                        CoursePurchase.objects.create(
                            user=request.user,
                            course=item_data['course'],
                            amount=item_data['unit_price'],
                            status='paid',
                            payment_method=cp_method,
                        )
                except Exception as item_error:
                    logger.error(f'Checkout POST: ошибка при создании позиции заказа #{idx+1}: {item_error}')
                    try:
                        order.delete()
                    except Exception:
                        pass
                    messages.error(request, f"Ошибка при создании заказа: {str(item_error)}")
                    return redirect('checkout')
            
            if not created_order_items:
                try:
                    order.delete()
                except Exception:
                    pass
                messages.error(request, "Ошибка при создании заказа: не удалось добавить курсы.")
                return redirect('checkout')
            
            order_items_from_db = list(OrderItem.objects.filter(order=order).select_related('course').all())
            if not order_items_from_db:
                try:
                    order.delete()
                except Exception:
                    pass
                messages.error(request, "Ошибка при создании заказа: позиции не найдены.")
                return redirect('checkout')
            
            cart.items.all().delete()

            order_items_for_receipt = order_items_from_db
            if order_items_for_receipt:
                try:
                    receipt_vat_total = Decimal('0.00')
                    delivery_vat = (delivery_cost * vat_rate / Decimal('100')).quantize(Decimal('0.01'))
                    
                    receipt = Receipt.objects.create(
                        user=request.user,
                        order=order,
                        status='executed',
                        total_amount=final_amount,
                        subtotal=cart_total,
                        delivery_cost=delivery_cost,
                        discount_amount=discount_amount,
                        vat_rate=vat_rate,
                        payment_method=payment_method_val if payment_method_val in ('cash', 'balance', 'card', 'sbp') else 'card'
                    )
                    for item in order_items_for_receipt:
                        if not item.course:
                            continue
                        ReceiptItem.objects.create(
                            receipt=receipt,
                            course=item.course,
                            article=str(item.course.id),
                            quantity=item.quantity,
                            unit_price=item.unit_price,
                        )
                    if delivery_cost and delivery_cost > 0:
                        ReceiptItem.objects.create(
                            receipt=receipt,
                            course=None,
                            line_description='Доставка',
                            article='DELIVERY',
                            quantity=1,
                            unit_price=delivery_cost,
                        )
                except Exception as receipt_error:
                    logger.error(f'Ошибка при создании чека: {receipt_error}')
                    # НЕ прерываем выполнение - чек не критичен
            _log_activity(request.user, 'create', f'order_{order.id}', f'Создан заказ на сумму {final_amount} ₽', request)
        messages.success(request, "Заказ успешно оформлен!")
        return redirect('order_detail', pk=order.pk)

    # GET запрос - показываем форму
    logger.info(f'Checkout GET: отображение формы для пользователя {request.user.id} ({request.user.username})')
    try:
        addresses = UserAddress.objects.filter(user=request.user)
        logger.info(f'Checkout: найдено адресов: {addresses.count()}')
        saved_payments = SavedPaymentMethod.objects.filter(user=request.user)
        logger.info(f'Checkout: найдено способов оплаты: {saved_payments.count()}')
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        
        # Рассчитываем суммы для отображения
        try:
            cart_total = cart.total_price()
            # Убеждаемся, что это Decimal
            if not isinstance(cart_total, Decimal):
                cart_total = Decimal(str(cart_total)) if cart_total else Decimal('0.00')
        except (ValueError, TypeError, InvalidOperation) as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Ошибка при расчете суммы корзины: {str(e)}')
            cart_total = Decimal('0.00')
            messages.warning(request, "Ошибка при расчете суммы корзины. Пожалуйста, обновите корзину.")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Неожиданная ошибка при расчете суммы корзины: {str(e)}')
            cart_total = Decimal('0.00')
        
        delivery_cost = Decimal('0.00')  # курсы без доставки
        vat_rate = Decimal('20.00')
        try:
            pre_vat_amount = cart_total + delivery_cost
            vat_amount = (pre_vat_amount * vat_rate / Decimal('100')).quantize(Decimal('0.01'))
            total_with_vat = pre_vat_amount + vat_amount
        except (ValueError, TypeError, InvalidOperation):
            pre_vat_amount = Decimal('0.00')
            vat_amount = Decimal('0.00')
            total_with_vat = Decimal('0.00')
        
        # Убеждаемся, что все Decimal значения корректны перед передачей в шаблон
        try:
            user_balance = Decimal(str(profile.balance)) if profile.balance else Decimal('0.00')
        except (ValueError, TypeError, InvalidOperation):
            user_balance = Decimal('0.00')
        
        # Преобразуем все Decimal в строки для безопасной передачи в шаблон
        context = {
            'cart': cart,
            'addresses': addresses,
            'saved_payments': saved_payments,
            'user_balance': float(user_balance),  # Преобразуем в float для шаблона
            'delivery_cost': float(delivery_cost),
            'vat_rate': float(vat_rate),
            'vat_amount': float(vat_amount),
            'total_with_vat': float(total_with_vat),
            'subtotal': float(cart_total),
            'courses_only': True,  # Только онлайн-курсы, адрес доставки не нужен
        }
        
        logger.info(f'Checkout: успешно отображаем страницу для пользователя {request.user.id}')
        return render(request, 'checkout.html', context)
    except Exception as e:
        import traceback
        logger.error(f'Ошибка в checkout view для пользователя {request.user.id}: {str(e)}\n{traceback.format_exc()}')
        messages.error(request, f"Произошла ошибка при загрузке страницы оформления заказа: {str(e)}")
        return redirect('cart')

@login_required
def update_cart_size(request, item_id):
    """Для курсов размер не меняется; редирект в корзину."""
    item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    # Курсы не имеют размеров
    return redirect('cart')

# =================== Отзывы на курсы ===================
@login_required
@require_POST
def add_review(request, product_id):
    """product_id в URL используется как course_id."""
    course = get_object_or_404(Course, id=product_id)
    data = json.loads(request.body)
    rating = int(data.get('rating', 0))
    review_text = data.get('review_text', '').strip()
    
    if not 1 <= rating <= 5:
        return JsonResponse({'success': False, 'message': 'Оценка должна быть от 1 до 5'}, status=400)
    
    from .utils import filter_profanity
    review_text = filter_profanity(review_text)
    
    user_has_purchased = OrderItem.objects.filter(
        order__user=request.user,
        course=course
    ).annotate(
        has_paid=Exists(
            Payment.objects.filter(order=OuterRef('order'), payment_status='paid')
        )
    ).filter(
        Q(has_paid=True) |
        Q(order__order_status__in=['paid', 'shipped', 'delivered'])
    ).exists()
    
    if not user_has_purchased:
        return JsonResponse({'success': False, 'message': 'Вы можете оставить отзыв только на купленный курс'}, status=403)
    
    existing_review = CourseReview.objects.filter(user=request.user, course=course).first()
    if existing_review:
        existing_review.rating = rating
        existing_review.review_text = review_text
        existing_review.save()
        return JsonResponse({'success': True, 'message': 'Отзыв обновлен'})
    
    CourseReview.objects.create(
        user=request.user,
        course=course,
        rating=rating,
        review_text=review_text
    )
    return JsonResponse({'success': True, 'message': 'Отзыв добавлен'})

def get_product_reviews(request, product_id):
    """product_id в URL используется как course_id."""
    course = get_object_or_404(Course, id=product_id)
    reviews = CourseReview.objects.filter(course=course).select_related('user').order_by('-created_at')
    
    limit = int(request.GET.get('limit', 2))
    reviews_limited = reviews[:limit]
    
    reviews_data = []
    for review in reviews_limited:
        reviews_data.append({
            'id': review.id,
            'user_name': review.user.get_full_name() or review.user.username if review.user else 'Анонимный пользователь',
            'rating': review.rating,
            'text': review.review_text or '',
            'created_at': review.created_at.strftime('%d.%m.%Y %H:%M')
        })
    
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    total_reviews = reviews.count()
    
    user_can_review = False
    if request.user.is_authenticated:
        user_can_review = OrderItem.objects.filter(
            order__user=request.user,
            course=course
        ).annotate(
            has_paid=Exists(
                Payment.objects.filter(order=OuterRef('order'), payment_status='paid')
            )
        ).filter(
            Q(has_paid=True) |
            Q(order__order_status__in=['paid', 'shipped', 'delivered'])
        ).exists()
    
    return JsonResponse({
        'success': True,
        'reviews': reviews_data,
        'avg_rating': round(avg_rating, 1),
        'total_reviews': total_reviews,
        'has_more': total_reviews > limit,
        'user_can_review': user_can_review
    })

@login_required
def product_reviews_page(request, product_id):
    """product_id в URL используется как course_id."""
    course = get_object_or_404(Course, id=product_id)
    reviews = CourseReview.objects.filter(course=course).select_related('user').order_by('-created_at')
    
    user_has_purchased = False
    if request.user.is_authenticated:
        user_has_purchased = OrderItem.objects.filter(
            order__user=request.user,
            course=course
        ).annotate(
            has_paid=Exists(
                Payment.objects.filter(order=OuterRef('order'), payment_status='paid')
            )
        ).filter(
            Q(has_paid=True) |
            Q(order__order_status__in=['paid', 'shipped', 'delivered'])
        ).exists()
    
    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    total_reviews = reviews.count()
    
    user_review = None
    if request.user.is_authenticated:
        user_review = CourseReview.objects.filter(user=request.user, course=course).first()
    
    return render(request, 'product_reviews.html', {
        'product': course,
        'reviews': reviews,
        'avg_rating': round(avg_rating, 1),
        'total_reviews': total_reviews,
        'user_has_purchased': user_has_purchased,
        'user_review': user_review
    })

# =================== Техническая поддержка ===================
@login_required
def support_view(request):
    tickets = SupportTicket.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'support.html', {'tickets': tickets})

@login_required
def create_support_ticket(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        subject = data.get('subject', '').strip()
        message_text = data.get('message_text', '').strip()
        
        if not subject or not message_text:
            return JsonResponse({'success': False, 'message': 'Заполните все поля'}, status=400)
        
        ticket = SupportTicket.objects.create(
            user=request.user,
            subject=subject,
            message_text=message_text,
            ticket_status='new'
        )
        
        _log_activity(request.user, 'create', f'ticket_{ticket.id}', f'Создано обращение в поддержку: {subject}', request)
        
        return JsonResponse({
            'success': True,
            'message': 'Обращение создано',
            'ticket_id': ticket.id
        })
    
    return JsonResponse({'success': False, 'message': 'Метод не поддерживается'}, status=405)

@login_required
def support_ticket_detail(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, id=ticket_id, user=request.user)
    return render(request, 'support_detail.html', {'ticket': ticket})

# =================== ПАНЕЛЬ МЕНЕДЖЕРА ===================

@login_required
def manager_dashboard(request):
    """Главная панель менеджера"""
    if not _user_is_manager(request.user):
        messages.error(request, "Доступ запрещен. Требуется роль менеджера.")
        return redirect('profile')
    
    # Статистика для дашборда
    from django.db.models import Count, Sum, Avg
    from django.utils import timezone
    from datetime import timedelta
    
    total_orders = Order.objects.count()
    orders_today = Order.objects.filter(created_at__date=timezone.now().date()).count()
    total_users = User.objects.count()
    active_users = UserProfile.objects.filter(user_status='active').count()
    new_tickets = SupportTicket.objects.filter(ticket_status='new').count()
    
    total_courses = Course.objects.count()
    available_courses = Course.objects.filter(is_available=True).count()
    month_ago = timezone.now() - timedelta(days=30)
    popular_courses = Course.objects.filter(
        orderitem__order__created_at__gte=month_ago
    ).annotate(
        total_sold=Sum('orderitem__quantity')
    ).order_by('-total_sold')[:5]
    
    stats = {
        'total_courses': total_courses,
        'available_courses': available_courses,
        'total_orders': total_orders,
        'orders_today': orders_today,
        'total_users': total_users,
        'active_users': active_users,
        'new_tickets': new_tickets,
        'popular_courses': popular_courses,
    }
    
    blocks = [
        {'title': 'Курсы', 'desc': 'Добавление, редактирование и удаление курсов', 'url': 'manager_courses_list', 'icon': '📦'},
        {'title': 'Категории курсов', 'desc': 'Управление категориями курсов', 'url': 'manager_course_categories_list', 'icon': '🏷️'},
        {'title': 'Заказы', 'desc': 'Просмотр и управление заказами', 'url': 'manager_orders_list', 'icon': '📋'},
        {'title': 'Пользователи', 'desc': 'Просмотр и управление пользователями', 'url': 'manager_users_list', 'icon': '👥'},
        {'title': 'Поддержка', 'desc': 'Обработка обращений в поддержку', 'url': 'manager_support_list', 'icon': '💬'},
        {'title': 'Аналитика', 'desc': 'Статистика и отчёты', 'url': 'manager_analytics', 'icon': '📊'},
    ]
    
    return render(request, 'main/manager/dashboard.html', {
        'blocks': blocks,
        'stats': stats
    })

# =================== УПРАВЛЕНИЕ КУРСАМИ ===================

@login_required
def manager_courses_list(request):
    """Список курсов (доступ: менеджер или админ)"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    q = (request.GET.get('q') or '').strip()
    category_id = request.GET.get('category')
    available_filter = request.GET.get('available')
    qs = Course.objects.select_related('category').prefetch_related('images').all()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if category_id:
        qs = qs.filter(category_id=category_id)
    if available_filter == 'yes':
        qs = qs.filter(is_available=True)
    elif available_filter == 'no':
        qs = qs.filter(is_available=False)
    qs = qs.order_by('-added_at')
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    categories = CourseCategory.objects.all()
    return render(request, 'main/manager/courses_list.html', {
        'page_obj': page_obj,
        'q': q,
        'categories': categories,
        'category_id': category_id,
        'available_filter': available_filter,
    })


@login_required
def manager_course_add(request):
    """Визуальное добавление курса (доступ: менеджер или админ)"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    categories = CourseCategory.objects.all()
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        slug = (request.POST.get('slug') or '').strip()
        if not title:
            messages.error(request, 'Введите название курса.')
            return render(request, 'main/manager/course_edit.html', _course_add_form_context(categories, request.POST))
        if not slug:
            from django.utils.text import slugify
            slug = slugify(title)
        if Course.objects.filter(slug=slug).exists():
            messages.error(request, f'Курс с таким slug уже есть: {slug}')
            return render(request, 'main/manager/course_edit.html', _course_add_form_context(categories, request.POST))
        try:
            course = Course.objects.create(
                title=title,
                slug=slug,
                category_id=request.POST.get('category_id') or None,
                description=request.POST.get('description', '').strip() or None,
                included_content=request.POST.get('included_content', '').strip() or None,
                price=Decimal(request.POST.get('price', 0) or 0),
                discount=Decimal(request.POST.get('discount', 0) or 0),
                is_available=request.POST.get('is_available') == 'on',
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception('Ошибка создания курса: %s', e)
            messages.error(request, f'Ошибка при сохранении курса: {e}')
            return render(request, 'main/manager/course_edit.html', _course_add_form_context(categories, request.POST))
        _log_activity(request.user, 'create', f'course_{course.id}', f'Создан курс: {course.title}', request)
        messages.success(request, 'Курс создан. Добавьте уроки ниже.')
        return redirect('manager_course_edit', course_id=course.id)
    return render(request, 'main/manager/course_edit.html', _course_add_form_context(categories))


def _content_type_choices():
    return list(CourseContentPage.CONTENT_TYPES)


@login_required
def manager_course_edit(request, course_id):
    """Редактирование курса (доступ: менеджер или админ). Включает страницы контента (модальные окна)."""
    if not _user_is_manager(request.user):
        return redirect('profile')
    course = get_object_or_404(Course, pk=course_id)
    categories = CourseCategory.objects.all()
    content_pages = list(course.content_pages.order_by('sort_order', 'id'))
    content_type_choices = _content_type_choices()
    if request.method == 'POST':
        course.title = request.POST.get('title', '').strip() or course.title
        slug = request.POST.get('slug', '').strip()
        if slug:
            course.slug = slug
        course.category_id = request.POST.get('category_id') or None
        course.description = request.POST.get('description', '').strip() or None
        course.included_content = request.POST.get('included_content', '').strip() or None
        try:
            course.price = Decimal(request.POST.get('price', 0) or 0)
            course.discount = Decimal(request.POST.get('discount', 0) or 0)
        except Exception:
            pass
        course.is_available = request.POST.get('is_available') == 'on'
        course.cover_image_path = request.POST.get('cover_image_path', '').strip() or None
        course.save()
        main_photo = request.FILES.get('main_photo')
        if main_photo:
            try:
                from main.course_content_upload import save_course_cover
                course.cover_image_path = save_course_cover(main_photo, course.id)
                course.save(update_fields=['cover_image_path'])
            except Exception as e:
                messages.error(request, f'Ошибка загрузки главного фото: {e}')
        # Добавление контента: файл (PDF/PPTX/DOCX) — каждая страница/слайд автоматом; или ссылка YouTube/Rutube
        add_mode = (request.POST.get('add_content_mode') or '').strip()
        next_sort = max([p.sort_order for p in content_pages], default=0) + 1
        content_file = request.FILES.get('content_file')
        if content_file:
            try:
                from main.course_content_upload import create_content_pages_from_upload
                n = create_content_pages_from_upload(course, content_file, next_sort)
                if n > 0:
                    messages.success(request, f'Добавлено страниц контента: {n} (каждая страница/слайд — отдельное модальное окно).')
                else:
                    messages.warning(request, 'Файл загружен, но страниц не создано. Используйте PDF, PPTX или DOCX.')
            except Exception as e:
                messages.error(request, f'Ошибка обработки файла: {getattr(e, "message", str(e))}')
            next_sort += 100
        elif add_mode == 'file':
            messages.warning(request, 'Файл не получен. Выберите файл (PDF, PPTX или DOCX) и нажмите «Сохранить» снова. Если файл большой — проверьте лимит загрузки на сервере.')
        elif add_mode == 'url':
            url = (request.POST.get('content_url') or '').strip()
            video_type = (request.POST.get('add_video_type') or 'youtube').strip().lower()
            if url and video_type in ('youtube', 'rutube'):
                CourseContentPage.objects.create(
                    course=course,
                    sort_order=next_sort,
                    content_type=video_type,
                    file_path=url,
                    title=(request.POST.get('content_url_title') or '').strip() or None,
                )
                messages.success(request, 'Видео добавлено. В курсе оно откроется в модальном окне.')
        # Обновление/удаление существующих страниц контента
        content_pages = list(course.content_pages.order_by('sort_order', 'id'))
        for page in content_pages:
            key = str(page.id)
            if request.POST.get('cp_%s_delete' % key):
                page.delete()
                continue
            try:
                sort_order = int(request.POST.get('cp_%s_sort_order' % key, page.sort_order) or 0)
            except (TypeError, ValueError):
                sort_order = page.sort_order or 0
            content_type = (request.POST.get('cp_%s_content_type' % key) or page.content_type or 'pdf_page').strip()
            file_path = (request.POST.get('cp_%s_file_path' % key) or '').strip() or page.file_path
            title = (request.POST.get('cp_%s_title' % key) or '').strip() or None
            page_number = request.POST.get('cp_%s_page_number' % key)
            try:
                page_number = int(page_number) if page_number and str(page_number).strip() else None
            except (TypeError, ValueError):
                page_number = page.page_number
            page.sort_order = sort_order
            page.content_type = content_type
            page.file_path = file_path
            page.title = title or None
            page.page_number = page_number
            page.save()
        # Добавление новых страниц контента
        try:
            new_count = int(request.POST.get('cp_new_count', 0) or 0)
        except (TypeError, ValueError):
            new_count = 0
        for i in range(new_count):
            content_type = (request.POST.get('cp_new_%s_content_type' % i) or 'pdf_page').strip()
            file_path = (request.POST.get('cp_new_%s_file_path' % i) or '').strip()
            title = (request.POST.get('cp_new_%s_title' % i) or '').strip() or None
            try:
                sort_order = int(request.POST.get('cp_new_%s_sort_order' % i, 999 + i) or 999 + i)
            except (TypeError, ValueError):
                sort_order = 999 + i
            page_number = request.POST.get('cp_new_%s_page_number' % i)
            try:
                page_number = int(page_number) if page_number and str(page_number).strip() else None
            except (TypeError, ValueError):
                page_number = None
            if content_type or file_path or title:
                CourseContentPage.objects.create(
                    course=course,
                    sort_order=sort_order,
                    content_type=content_type or 'pdf_page',
                    file_path=file_path or '',
                    title=title,
                    page_number=page_number,
                )
        _log_activity(request.user, 'update', f'course_{course_id}', f'Обновлен курс: {course.title}', request)
        messages.success(request, 'Курс обновлен.')
        return redirect('manager_course_edit', course_id=course_id)
    return render(request, 'main/manager/course_edit.html', {
        'course': course,
        'categories': categories,
        'content_pages': content_pages,
        'content_type_choices': content_type_choices,
        'content_type_choices_json': json.dumps([[str(v), str(l)] for v, l in content_type_choices]),
        'form_data': {},
    })


@login_required
def manager_course_delete(request, course_id):
    """Удаление курса (доступ: менеджер или админ)"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    course = get_object_or_404(Course, pk=course_id)
    if request.method == 'POST':
        title = course.title
        course.delete()
        _log_activity(request.user, 'delete', f'course_{course_id}', f'Удален курс: {title}', request)
        messages.success(request, f'Курс "{title}" удален.')
        return redirect('manager_courses_list')
    return render(request, 'main/manager/course_delete.html', {'course': course})


@login_required
def manager_lesson_add(request, course_id):
    """Добавить урок (до 10 страниц: картинка/видео/PDF + текст)."""
    if not _user_is_manager(request.user):
        return redirect('profile')
    course = get_object_or_404(Course, pk=course_id)
    next_order = course.lessons.count() + 1
    if request.method == 'POST':
        title = (request.POST.get('lesson_title') or '').strip() or None
        lesson = Lesson.objects.create(course=course, sort_order=next_order, title=title or f'Урок {next_order}')
        for i in range(LessonPage.MAX_PAGES_PER_LESSON):
            page_type = (request.POST.get(f'page_{i}_type') or 'image').strip()
            file_path = _lesson_page_file_path(request, i, course_id, lesson.id, page_type)
            text = (request.POST.get(f'page_{i}_text') or '').strip() or None
            page_num = request.POST.get(f'page_{i}_page_number')
            page_number = int(page_num) if page_num and str(page_num).strip().isdigit() else None
            page_num_end = request.POST.get(f'page_{i}_page_number_end')
            page_number_end = int(page_num_end) if page_num_end and str(page_num_end).strip().isdigit() else None
            if file_path or text:
                LessonPage.objects.create(
                    lesson=lesson,
                    sort_order=i + 1,
                    page_type=page_type if page_type in ('image', 'video', 'pdf_page') else 'image',
                    file_path=file_path,
                    page_number=page_number,
                    page_number_end=page_number_end,
                    text=text,
                )
        messages.success(request, 'Урок добавлен.')
        return redirect('manager_course_edit', course_id=course_id)
    return render(request, 'main/manager/lesson_edit.html', {
        'course': course,
        'lesson': None,
        'page_slots': [],
        'is_add': True,
        'back_url_name': 'manager_course_edit',
        'back_kwargs': {'course_id': course_id},
    })


@login_required
def manager_lesson_edit(request, course_id, lesson_id):
    """Редактировать урок и его страницы (до 10)."""
    if not _user_is_manager(request.user):
        return redirect('profile')
    course = get_object_or_404(Course, pk=course_id)
    lesson = get_object_or_404(Lesson, pk=lesson_id, course=course)
    pages = list(lesson.pages.order_by('sort_order', 'id'))
    if request.method == 'POST':
        lesson.title = (request.POST.get('lesson_title') or '').strip() or None
        lesson.save()
        lesson.pages.all().delete()
        for i in range(LessonPage.MAX_PAGES_PER_LESSON):
            page_type = (request.POST.get(f'page_{i}_type') or 'image').strip()
            file_path = _lesson_page_file_path(request, i, course_id, lesson.id, page_type)
            text = (request.POST.get(f'page_{i}_text') or '').strip() or None
            page_num = request.POST.get(f'page_{i}_page_number')
            page_number = int(page_num) if page_num and str(page_num).strip().isdigit() else None
            page_num_end = request.POST.get(f'page_{i}_page_number_end')
            page_number_end = int(page_num_end) if page_num_end and str(page_num_end).strip().isdigit() else None
            if file_path or text:
                LessonPage.objects.create(
                    lesson=lesson,
                    sort_order=i + 1,
                    page_type=page_type if page_type in ('image', 'video', 'pdf_page') else 'image',
                    file_path=file_path,
                    page_number=page_number,
                    page_number_end=page_number_end,
                    text=text,
                )
        messages.success(request, 'Урок сохранён.')
        return redirect('manager_course_edit', course_id=course_id)
    page_slots = [p for p in pages if p.file_path or p.text]
    return render(request, 'main/manager/lesson_edit.html', {
        'course': course,
        'lesson': lesson,
        'page_slots': page_slots,
        'is_add': False,
        'back_url_name': 'manager_course_edit',
        'back_kwargs': {'course_id': course_id},
    })


# =================== КАТЕГОРИИ КУРСОВ ===================

@login_required
def manager_course_categories_list(request):
    """Список категорий курсов (доступ: менеджер или админ)"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    categories = CourseCategory.objects.all().order_by('category_name')
    return render(request, 'main/manager/course_categories_list.html', {'categories': categories})


@login_required
def manager_course_category_add(request):
    """Добавление категории курсов (доступ: менеджер или админ)"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    if request.method == 'POST':
        name = request.POST.get('category_name', '').strip()
        if not name:
            messages.error(request, 'Введите название категории.')
            return redirect('manager_course_category_add')
        category = CourseCategory.objects.create(category_name=name)
        _log_activity(request.user, 'create', f'course_category_{category.id}', f'Создана категория: {category.category_name}', request)
        messages.success(request, 'Категория добавлена.')
        return redirect('manager_course_categories_list')
    return render(request, 'main/manager/course_category_edit.html', {'category': None})


@login_required
def manager_course_category_edit(request, category_id):
    """Редактирование категории курсов (доступ: менеджер или админ)"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    category = get_object_or_404(CourseCategory, pk=category_id)
    if request.method == 'POST':
        old_name = category.category_name
        category.category_name = request.POST.get('category_name', '').strip() or old_name
        category.save()
        _log_activity(request.user, 'update', f'course_category_{category_id}', f'Обновлена категория: {old_name} -> {category.category_name}', request)
        messages.success(request, 'Категория обновлена.')
        return redirect('manager_course_categories_list')
    return render(request, 'main/manager/course_category_edit.html', {'category': category})


# =================== УПРАВЛЕНИЕ ЗАКАЗАМИ ===================

@login_required
def manager_orders_list(request):
    """Список заказов для менеджера"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    
    q = (request.GET.get('q') or '').strip()
    status_filter = request.GET.get('status')
    
    qs = Order.objects.select_related('user', 'address').prefetch_related('items').all().order_by('-created_at')
    
    if q:
        qs = qs.filter(Q(id__icontains=q) | Q(user__username__icontains=q) | Q(user__email__icontains=q))
    if status_filter:
        qs = qs.filter(order_status=status_filter)
    
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    
    return render(request, 'main/manager/orders_list.html', {
        'page_obj': page_obj,
        'q': q,
        'status_filter': status_filter,
        'statuses': Order.ORDER_STATUSES
    })

@login_required
def manager_order_detail(request, order_id):
    """Детали заказа для менеджера"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    
    order = get_object_or_404(Order, pk=order_id)
    items = order.items.select_related('course').all()
    delivery = getattr(order, 'delivery', None)
    
    items_with_total = []
    for item in items:
        item_total = float(item.unit_price) * item.quantity
        items_with_total.append({
            'item': item,
            'total': item_total
        })
    
    if request.method == 'POST':
        old_status = order.order_status
        new_status = request.POST.get('order_status')
        if new_status in dict(Order.ORDER_STATUSES):
            order.order_status = new_status
            order.save()
            
            # Если статус "отправлен", создаем или обновляем доставку
            if new_status == 'shipped':
                delivery, created = Delivery.objects.get_or_create(order=order)
                delivery.carrier_name = request.POST.get('carrier_name', '').strip() or None
                delivery.tracking_number = request.POST.get('tracking_number', '').strip() or None
                delivery.delivery_status = 'in_transit'
                if not delivery.shipped_at:
                    delivery.shipped_at = timezone.now()
                delivery.save()
            
            # Если статус меняется на "доставлен" и оплата была наличными - начисляем на счет организации БЕЗ налога
            if new_status == 'delivered' and old_status != 'delivered':
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"СТАТУС ИЗМЕНЕН НА 'delivered' для заказа #{order.id} (менеджер)")
                
                payment = Payment.objects.filter(order=order).first()
                logger.error(f"Payment для заказа #{order.id}: payment_method={payment.payment_method if payment else 'None'}, payment_status={payment.payment_status if payment else 'None'}, paid_from_balance={order.paid_from_balance}")
                
                # Проверяем, что оплата была наличными (cash) или pending (наличные в обработке)
                # и средства еще не были переведены на счет организации
                is_cash_payment = False
                if payment:
                    if payment.payment_method == 'cash':
                        is_cash_payment = True
                    elif payment.payment_method == 'pending' and not order.paid_from_balance:
                        is_cash_payment = True
                    elif payment.payment_status == 'pending' and payment.payment_method not in ['balance', 'card', 'visa', 'mastercard']:
                        is_cash_payment = True
                
                if is_cash_payment:
                    logger.error(f"Оплата наличными обнаружена для заказа #{order.id}")
                    
                    # Проверяем, не были ли уже переведены средства
                    org_payment_exists = OrganizationTransaction.objects.filter(
                        order=order,
                        transaction_type='order_payment'
                    ).exists()
                    
                    logger.error(f"Транзакция order_payment существует: {org_payment_exists}")
                    
                    if not org_payment_exists:
                        # Начисляем сумму заказа на счет организации, но БЕЗ налога
                        try:
                            org_account = OrganizationAccount.get_account()
                            balance_before = org_account.balance
                            tax_reserve_before = org_account.tax_reserve
                            
                            logger.error(f"Баланс организации до начисления: {balance_before}, сумма заказа: {order.total_amount}")
                            
                            org_account.balance += order.total_amount
                            # НЕ добавляем налог в резерв, так как оплата была наличными
                            org_account.save()
                            
                            logger.error(f"Баланс организации после начисления: {org_account.balance}")
                            
                            OrganizationTransaction.objects.create(
                                organization_account=org_account,
                                transaction_type='order_payment',
                                amount=order.total_amount,
                                description=f'Поступление от заказа #{order.id} (наличные, доставлен)',
                                order=order,
                                created_by=request.user,
                                balance_before=balance_before,
                                balance_after=org_account.balance,
                                tax_reserve_before=tax_reserve_before,
                                tax_reserve_after=tax_reserve_before,
                            )
                            logger.error(f"✅ Транзакция создана для заказа #{order.id}")
                        except Exception as e:
                            import traceback
                            logger.error(f"Ошибка при начислении средств на счет организации для заказа #{order.id}: {str(e)}")
                            logger.error(traceback.format_exc())
                    else:
                        logger.error(f"Транзакция уже существует для заказа #{order.id}, пропускаем начисление")
                else:
                    logger.error(f"Оплата не наличными для заказа #{order.id}: payment_method={payment.payment_method if payment else 'None'}")
            
            # Если статус меняется на "отменен" - обрабатываем отмену заказа
            if new_status == 'cancelled' and old_status != 'cancelled':
                try:
                    _process_order_cancellation(order, request.user)
                    messages.success(request, 'Заказ отменен. Деньги возвращены, товар возвращен на склад.')
                except ValueError as e:
                    messages.error(request, str(e))
                except Exception as e:
                    import traceback
                    logger.error(f"Ошибка при отмене заказа #{order.id}: {str(e)}")
                    logger.error(traceback.format_exc())
                    messages.error(request, f'Ошибка при отмене заказа: {str(e)}')
            
            if old_status != new_status:
                _log_activity(request.user, 'update', f'order_{order_id}', f'Изменен статус заказа: {old_status} -> {new_status}', request)
            messages.success(request, 'Статус заказа обновлен')
            return redirect('manager_order_detail', order_id=order.id)
    
    return render(request, 'main/manager/order_detail.html', {
        'order': order,
        'items': items_with_total,
        'delivery': delivery,
        'statuses': Order.ORDER_STATUSES
    })

# =================== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ===================

@login_required
def manager_users_list(request):
    """Список пользователей для менеджера"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    
    q = (request.GET.get('q') or '').strip()
    status_filter = request.GET.get('status')
    role_filter = request.GET.get('role')
    activity_filter = request.GET.get('activity')  # active, inactive
    
    qs = User.objects.select_related('profile').all().order_by('-date_joined')
    
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    if status_filter:
        qs = qs.filter(profile__user_status=status_filter)
    if role_filter:
        qs = qs.filter(profile__role_id=role_filter)
    if activity_filter == 'active':
        # Пользователи с заказами за последние 30 дней
        from datetime import timedelta
        month_ago = timezone.now() - timedelta(days=30)
        qs = qs.filter(order__created_at__gte=month_ago).distinct()
    elif activity_filter == 'inactive':
        # Пользователи без заказов за последние 30 дней
        from datetime import timedelta
        month_ago = timezone.now() - timedelta(days=30)
        qs = qs.exclude(order__created_at__gte=month_ago).distinct()
    
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    roles = Role.objects.all().order_by('role_name')
    
    return render(request, 'main/manager/users_list.html', {
        'page_obj': page_obj,
        'q': q,
        'status_filter': status_filter,
        'role_filter': role_filter,
        'activity_filter': activity_filter,
        'roles': roles
    })

@login_required
def manager_user_toggle_block(request, user_id):
    """Блокировка/разблокировка пользователя"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    
    from django.contrib.auth.models import User as AuthUser
    user = get_object_or_404(AuthUser, pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    old_status = profile.user_status
    profile.user_status = 'active' if profile.user_status == 'blocked' else 'blocked'
    profile.save()
    # Также устанавливаем is_active для дополнительной защиты
    user.is_active = (profile.user_status == 'active')
    user.save()
    _log_activity(request.user, 'update', f'user_{user_id}', f'Изменен статус пользователя: {old_status} -> {profile.user_status}', request)
    messages.success(request, f'Пользователь {"разблокирован" if profile.user_status == "active" else "заблокирован"}')
    return redirect('manager_users_list')

# =================== УПРАВЛЕНИЕ ПОДДЕРЖКОЙ ===================

@login_required
def manager_support_list(request):
    """Список обращений в поддержку для менеджера"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    
    q = (request.GET.get('q') or '').strip()
    status_filter = request.GET.get('status')
    
    qs = SupportTicket.objects.select_related('user').all().order_by('-created_at')
    
    if q:
        qs = qs.filter(Q(subject__icontains=q) | Q(message_text__icontains=q) | Q(user__username__icontains=q))
    if status_filter:
        qs = qs.filter(ticket_status=status_filter)
    
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    
    return render(request, 'main/manager/support_list.html', {
        'page_obj': page_obj,
        'q': q,
        'status_filter': status_filter
    })

@login_required
def manager_support_detail(request, ticket_id):
    """Детали обращения в поддержку для менеджера"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    
    ticket = get_object_or_404(SupportTicket, pk=ticket_id)
    
    if request.method == 'POST':
        ticket.response_text = request.POST.get('response_text', '').strip()
        ticket.ticket_status = request.POST.get('ticket_status', 'new')
        ticket.save()
        _log_activity(request.user, 'update', f'ticket_{ticket_id}', f'Обновлено обращение в поддержку: {ticket.subject}', request)
        messages.success(request, 'Ответ сохранен')
        return redirect('manager_support_detail', ticket_id=ticket.id)
    
    return render(request, 'main/manager/support_detail.html', {'ticket': ticket})

# =================== АНАЛИТИКА И ОТЧЁТЫ ===================

@login_required
def manager_analytics(request):
    """Аналитика для менеджера"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    
    from django.db.models import Count, Sum, Avg, Q
    from django.utils import timezone
    from datetime import timedelta
    
    # Периоды
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Статистика по заказам
    orders_today = Order.objects.filter(created_at__date=today).count()
    orders_week = Order.objects.filter(created_at__date__gte=week_ago).count()
    orders_month = Order.objects.filter(created_at__date__gte=month_ago).count()
    
    revenue_today = Order.objects.filter(created_at__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    revenue_week = Order.objects.filter(created_at__date__gte=week_ago).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    revenue_month = Order.objects.filter(created_at__date__gte=month_ago).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    
    course_of_week = Course.objects.filter(
        orderitem__order__created_at__date__gte=week_ago
    ).annotate(
        total_sold=Sum('orderitem__quantity'),
        total_revenue=Sum(F('orderitem__quantity') * F('orderitem__unit_price'))
    ).order_by('-total_sold').first()
    
    course_of_month = Course.objects.filter(
        orderitem__order__created_at__date__gte=month_ago
    ).annotate(
        total_sold=Sum('orderitem__quantity'),
        total_revenue=Sum(F('orderitem__quantity') * F('orderitem__unit_price'))
    ).order_by('-total_sold').first()
    
    popular_courses = Course.objects.filter(
        orderitem__order__created_at__date__gte=month_ago
    ).annotate(
        total_sold=Sum('orderitem__quantity'),
        total_revenue=Sum(F('orderitem__quantity') * F('orderitem__unit_price'))
    ).order_by('-total_sold')[:10]
    
    category_stats = CourseCategory.objects.annotate(
        total_courses=Count('course'),
        total_sold=Sum('course__orderitem__quantity'),
        total_revenue=Sum(F('course__orderitem__quantity') * F('course__orderitem__unit_price'))
    ).order_by('-total_revenue')[:10]
    
    stats = {
        'orders_today': orders_today,
        'orders_week': orders_week,
        'orders_month': orders_month,
        'revenue_today': revenue_today,
        'revenue_week': revenue_week,
        'revenue_month': revenue_month,
        'course_of_week': course_of_week,
        'course_of_month': course_of_month,
        'popular_courses': popular_courses,
        'category_stats': category_stats,
    }
    
    return render(request, 'main/manager/analytics.html', stats)

@login_required
def manager_analytics_export_csv(request):
    """Экспорт отчёта в CSV"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    
    import csv
    from django.http import HttpResponse
    from django.db.models import Sum, F
    
    report_type = request.GET.get('type', 'sales')  # sales, products, users
    
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response.write('\ufeff')  # BOM для корректного отображения кириллицы в Excel
    
    if report_type == 'sales':
        response['Content-Disposition'] = 'attachment; filename="отчет_по_продажам.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['ID заказа', 'Пользователь', 'Email', 'Сумма (₽)', 'Статус', 'Дата создания'])
        for order in Order.objects.select_related('user').all().order_by('-created_at')[:1000]:
            writer.writerow([
                order.id,
                order.user.username if order.user else '',
                order.user.email if order.user else '',
                order.total_amount,
                order.get_order_status_display(),
                order.created_at.strftime('%Y-%m-%d %H:%M')
            ])
    elif report_type == 'courses':
        response['Content-Disposition'] = 'attachment; filename="отчет_по_курсам.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['ID', 'Название', 'Категория', 'Цена (₽)', 'Скидка (%)', 'Продано (шт.)', 'Доступен'])
        for course in Course.objects.select_related('category').annotate(
            total_sold=Sum('orderitem__quantity')
        ).all():
            writer.writerow([
                course.id,
                course.title,
                course.category.category_name if course.category else '',
                course.price,
                course.discount,
                course.total_sold or 0,
                'Да' if course.is_available else 'Нет'
            ])
    elif report_type == 'users':
        response['Content-Disposition'] = 'attachment; filename="отчет_по_пользователям.csv"'
        writer = csv.writer(response, delimiter=';')
        writer.writerow(['ID', 'Логин', 'Email', 'Имя', 'Фамилия', 'Роль', 'Статус', 'Баланс (₽)', 'Заказов', 'Дата регистрации'])
        for user in User.objects.select_related('profile').annotate(
            total_orders=Count('order')
        ).all():
            profile = getattr(user, 'profile', None)
            writer.writerow([
                user.id,
                user.username,
                user.email,
                user.first_name,
                user.last_name,
                profile.role.role_name if profile and profile.role else '',
                profile.user_status if profile else '',
                profile.balance if profile else 0,
                user.total_orders,
                user.date_joined.strftime('%Y-%m-%d %H:%M')
            ])
    
    return response

@login_required
def manager_analytics_export_pdf(request):
    """Экспорт отчёта в PDF"""
    if not _user_is_manager(request.user):
        return redirect('profile')
    
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from io import BytesIO
        from django.db.models import Sum, Count
        from django.utils import timezone
        from datetime import timedelta
        
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        y = height - 20 * mm
        line_height = 6 * mm
        left_margin = 15 * mm
        
        # Используем шрифт с поддержкой кириллицы
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import platform
        import os
        
        font_name = "Helvetica"
        font_bold = "Helvetica-Bold"
        
        # Пытаемся использовать системные шрифты с поддержкой кириллицы
        try:
            system = platform.system()
            arial_found = False
            
            # Для Windows используем системные шрифты
            if system == 'Windows':
                font_dir = r'C:\Windows\Fonts'
                
                # Список возможных путей к Arial
                arial_variants = [
                    'arial.ttf',
                    'Arial.ttf',
                    'ARIAL.TTF',
                    'arialuni.ttf',  # Arial Unicode MS (полная поддержка Unicode)
                ]
                
                arial_bold_variants = [
                    'arialbd.ttf',
                    'Arialbd.ttf',
                    'ARIALBD.TTF',
                ]
                
                # Пробуем найти и зарегистрировать Arial
                for variant in arial_variants:
                    arial_path = os.path.join(font_dir, variant)
                    if os.path.exists(arial_path):
                        try:
                            pdfmetrics.registerFont(TTFont('Arial', arial_path))
                            font_name = 'Arial'
                            arial_found = True
                            break
                        except Exception:
                            continue
                
                # Пробуем найти и зарегистрировать Arial Bold
                if arial_found:
                    for variant in arial_bold_variants:
                        arial_bold_path = os.path.join(font_dir, variant)
                        if os.path.exists(arial_bold_path):
                            try:
                                pdfmetrics.registerFont(TTFont('Arial-Bold', arial_bold_path))
                                font_bold = 'Arial-Bold'
                                break
                            except Exception:
                                pass
            # Для Linux используем DejaVu Sans
            elif system == 'Linux':
                dejavu_fonts = [
                    ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
                    ('/usr/share/fonts/TTF/DejaVuSans.ttf', '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf'),
                    ('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'),
                ]
                
                for regular_path, bold_path in dejavu_fonts:
                    if os.path.exists(regular_path):
                        try:
                            pdfmetrics.registerFont(TTFont('DejaVuSans', regular_path))
                            font_name = 'DejaVuSans'
                            arial_found = True
                            
                            if os.path.exists(bold_path):
                                try:
                                    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', bold_path))
                                    font_bold = 'DejaVuSans-Bold'
                                except Exception:
                                    font_bold = 'DejaVuSans'
                            else:
                                font_bold = 'DejaVuSans'
                            break
                        except Exception:
                            continue
        except Exception:
            pass
        
        def draw(text, bold=False, font_size=10):
            nonlocal y
            current_font = font_bold if bold else font_name
            c.setFont(current_font, font_size)
            c.drawString(left_margin, y, str(text))
            y -= line_height
        
        draw("Отчёт по продажам", bold=True, font_size=16)
        draw(f"Дата: {timezone.now().strftime('%d.%m.%Y %H:%M')}")
        y -= 5 * mm
        
        # Статистика
        month_ago = timezone.now() - timedelta(days=30)
        orders_count = Order.objects.filter(created_at__gte=month_ago).count()
        revenue = Order.objects.filter(created_at__gte=month_ago).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
        
        draw("Статистика за последний месяц:", bold=True)
        draw(f"Заказов: {orders_count}")
        draw(f"Выручка: {revenue} ₽")
        y -= 5 * mm
        
        # Популярные курсы
        draw("Популярные курсы:", bold=True)
        popular = Course.objects.filter(
            orderitem__order__created_at__gte=month_ago
        ).annotate(
            total_sold=Sum('orderitem__quantity')
        ).order_by('-total_sold')[:10]
        
        for i, course in enumerate(popular, 1):
            draw(f"{i}. {course.title} - продано: {course.total_sold or 0} шт.")
        
        c.showPage()
        c.save()
        
        buffer.seek(0)
        pdf_content = buffer.getvalue()
        buffer.close()
        
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="отчет_по_продажам.pdf"'
        return response
        
    except ImportError:
        messages.error(request, "PDF генератор не установлен. Пожалуйста, установите reportlab.")
        return redirect('manager_analytics')

# =================== ПАНЕЛЬ АДМИНИСТРАТОРА ===================

# =================== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ И РОЛЯМИ ===================

@login_required
def admin_users_list(request):
    """Расширенный список пользователей для админа"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    _log_activity(request.user, 'view', 'users_list', 'Просмотр списка пользователей', request)
    
    q = (request.GET.get('q') or '').strip()
    status_filter = request.GET.get('status')
    role_filter = request.GET.get('role')
    activity_filter = request.GET.get('activity')
    
    qs = User.objects.select_related('profile').all().order_by('-date_joined')
    
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    if status_filter:
        qs = qs.filter(profile__user_status=status_filter)
    if role_filter:
        qs = qs.filter(profile__role_id=role_filter)
    if activity_filter == 'active':
        from datetime import timedelta
        month_ago = timezone.now() - timedelta(days=30)
        qs = qs.filter(order__created_at__gte=month_ago).distinct()
    elif activity_filter == 'inactive':
        from datetime import timedelta
        month_ago = timezone.now() - timedelta(days=30)
        qs = qs.exclude(order__created_at__gte=month_ago).distinct()
    
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    roles = Role.objects.all().order_by('role_name')
    
    return render(request, 'main/admin/users_list.html', {
        'page_obj': page_obj,
        'q': q,
        'status_filter': status_filter,
        'role_filter': role_filter,
        'activity_filter': activity_filter,
        'roles': roles
    })

@login_required
def admin_users_import_csv(request):
    """Импорт пользователей из CSV файла"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    if request.method == 'POST':
        if 'csv_file' not in request.FILES:
            messages.error(request, 'Файл не загружен')
            return redirect('admin_users_list')
        
        import csv
        import io
        from django.contrib.auth.hashers import make_password
        
        csv_file = request.FILES['csv_file']
        decoded_file = csv_file.read().decode('utf-8-sig')
        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)
        
        success_count = 0
        error_count = 0
        errors = []
        
        with transaction.atomic():
            for row_num, row in enumerate(reader, start=2):
                try:
                    # Получаем обязательные поля
                    username = row.get('username', '').strip()
                    email = row.get('email', '').strip()
                    password = row.get('password', '').strip()
                    
                    if not username:
                        errors.append(f"Строка {row_num}: отсутствует логин")
                        error_count += 1
                        continue
                    
                    if User.objects.filter(username=username).exists():
                        errors.append(f"Строка {row_num}: пользователь с логином '{username}' уже существует")
                        error_count += 1
                        continue
                    
                    if not email:
                        email = f"{username}@example.com"
                    
                    if not password:
                        password = 'default_password_123'  # Пользователь должен будет сменить
                    
                    # Создаем пользователя
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        password=password,
                        first_name=row.get('first_name', '').strip(),
                        last_name=row.get('last_name', '').strip(),
                        is_active=row.get('is_active', 'true').lower() in ('true', '1', 'yes', 'да')
                    )
                    
                    # Получаем роль
                    role = None
                    role_name = row.get('role', '').strip()
                    if role_name:
                        role = Role.objects.filter(role_name=role_name.upper()).first()
                    
                    # Создаем профиль
                    UserProfile.objects.create(
                        user=user,
                        role=role,
                        full_name=f"{user.first_name} {user.last_name}".strip() or username,
                        phone_number=row.get('phone_number', '').strip() or None,
                        user_status=row.get('user_status', 'active').strip() or 'active',
                        balance=Decimal(str(row.get('balance', '0')).replace(',', '.'))
                    )
                    
                    success_count += 1
                    _log_activity(request.user, 'create', f'user_{user.id}', f'Импортирован пользователь: {username}', request)
                    
                except Exception as e:
                    errors.append(f"Строка {row_num}: {str(e)}")
                    error_count += 1
        
        if success_count > 0:
            messages.success(request, f'Успешно импортировано пользователей: {success_count}')
        if error_count > 0:
            error_msg = f'Ошибок при импорте: {error_count}'
            if len(errors) <= 10:
                error_msg += f'. Детали: {"; ".join(errors[:10])}'
            else:
                error_msg += f'. Первые 10 ошибок: {"; ".join(errors[:10])}'
            messages.warning(request, error_msg)
        
        _log_activity(request.user, 'import', 'users_csv', f'Импорт пользователей из CSV: успешно {success_count}, ошибок {error_count}', request)
        return redirect('admin_users_list')
    
    return redirect('admin_users_list')

@login_required
def admin_user_create(request):
    """Создание нового пользователя"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    roles = Role.objects.all().order_by('role_name')
    
    if request.method == 'POST':
        try:
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            role_id = request.POST.get('role_id')
            user_status = request.POST.get('user_status', 'active')
            
            if not username or not email or not password:
                messages.error(request, 'Логин, email и пароль обязательны')
                return render(request, 'main/admin/user_edit.html', {
                    'user_obj': None,
                    'roles': roles,
                    'is_create': True
                })
            
            # Создаем пользователя
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )
            
            # Создаем профиль
            secret_word = request.POST.get('secret_word', '').strip()
            profile = UserProfile.objects.create(
                user=user,
                role_id=role_id if role_id else None,
                user_status=user_status,
                full_name=f"{first_name} {last_name}".strip(),
                secret_word=secret_word if secret_word else None
            )
            
            _log_activity(request.user, 'create', f'user_{user.id}', f'Создан пользователь: {username}', request)
            messages.success(request, f'Пользователь {username} успешно создан')
            return redirect('admin_user_edit', user_id=user.id)
        except Exception as e:
            messages.error(request, f'Ошибка при создании пользователя: {str(e)}')
    
    return render(request, 'main/admin/user_edit.html', {
        'user_obj': None,
        'roles': roles,
        'is_create': True
    })

@login_required
def admin_user_edit(request, user_id):
    """Редактирование пользователя админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    user = get_object_or_404(User, pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    roles = Role.objects.all().order_by('role_name')
    
    if request.method == 'POST':
        try:
            user.username = request.POST.get('username', '').strip()
            user.email = request.POST.get('email', '').strip()
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name = request.POST.get('last_name', '').strip()
            
            new_password = request.POST.get('password', '').strip()
            if new_password:
                user.set_password(new_password)
                _log_activity(request.user, 'update', f'user_{user.id}', 'Изменен пароль пользователя', request)
            
            user.is_active = request.POST.get('is_active') == 'on'
            user.is_staff = request.POST.get('is_staff') == 'on'
            user.is_superuser = request.POST.get('is_superuser') == 'on'
            user.save()
            
            # Обновляем профиль
            # 3НФ: full_name хранится в user.first_name, user.last_name (уже обновлены выше)
            profile.phone_number = request.POST.get('phone_number', '').strip()
            birth_date_str = request.POST.get('birth_date', '').strip()
            if birth_date_str:
                try:
                    from datetime import datetime
                    profile.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            balance_str = request.POST.get('balance', '').strip()
            if balance_str:
                try:
                    profile.balance = Decimal(balance_str)
                except (ValueError, InvalidOperation):
                    pass
            
            # Обновление секретного слова (только если указано)
            secret_word = request.POST.get('secret_word', '').strip()
            if secret_word:
                profile.secret_word = secret_word
                _log_activity(request.user, 'update', f'user_{user.id}', 'Изменено секретное слово пользователя', request)
            
            role_id = request.POST.get('role_id')
            if role_id:
                try:
                    old_role = profile.role.role_name if profile.role else None
                    profile.role = Role.objects.get(pk=role_id)
                    new_role = profile.role.role_name
                    if old_role != new_role:
                        _log_activity(request.user, 'update', f'user_{user.id}', f'Изменена роль: {old_role} -> {new_role}', request)
                except Role.DoesNotExist:
                    profile.role = None
            else:
                profile.role = None
            
            old_status = profile.user_status
            profile.user_status = 'blocked' if request.POST.get('blocked') == 'on' else 'active'
            if old_status != profile.user_status:
                _log_activity(request.user, 'update', f'user_{user.id}', f'Изменен статус: {old_status} -> {profile.user_status}', request)
            
            profile.save()
            # Также устанавливаем is_active для дополнительной защиты
            user.is_active = (profile.user_status == 'active')
            user.save()
            
            _log_activity(request.user, 'update', f'user_{user.id}', f'Обновлен пользователь: {user.username}', request)
            messages.success(request, 'Пользователь обновлен')
            return redirect('admin_users_list')
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении: {str(e)}')
    
    return render(request, 'main/admin/user_edit.html', {
        'user_obj': user,
        'profile': profile,
        'roles': roles,
        'is_create': False
    })

@login_required
def admin_user_delete(request, user_id):
    """Удаление пользователя"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    user = get_object_or_404(User, pk=user_id)
    
    if request.method == 'POST':
        username = user.username
        user_id_val = user.id
        user.delete()
        _log_activity(request.user, 'delete', f'user_{user_id_val}', f'Удален пользователь: {username}', request)
        messages.success(request, f'Пользователь {username} удален')
        return redirect('admin_users_list')
    
    return render(request, 'main/admin/user_delete.html', {'user_obj': user})

@login_required
def admin_roles_list(request):
    """Управление ролями"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    _log_activity(request.user, 'view', 'roles_list', 'Просмотр списка ролей', request)
    
    roles = Role.objects.all().order_by('role_name')
    
    if request.method == 'POST' and request.POST.get('action') == 'create':
        role_name = request.POST.get('role_name', '').strip()
        if role_name:
            role, created = Role.objects.get_or_create(role_name=role_name)
            if created:
                _log_activity(request.user, 'create', f'role_{role.id}', f'Создана роль: {role_name}', request)
                messages.success(request, 'Роль создана')
            else:
                messages.info(request, 'Роль уже существует')
        return redirect('admin_roles_list')
    
    if request.method == 'POST' and request.POST.get('action') == 'delete':
        role_id = request.POST.get('role_id')
        try:
            role = Role.objects.get(pk=role_id)
            role_name = role.role_name
            role.delete()
            _log_activity(request.user, 'delete', f'role_{role_id}', f'Удалена роль: {role_name}', request)
            messages.success(request, 'Роль удалена')
        except Role.DoesNotExist:
            messages.error(request, 'Роль не найдена')
        return redirect('admin_roles_list')
    
    return render(request, 'main/admin/roles_list.html', {'roles': roles})

# =================== УПРАВЛЕНИЕ ТОВАРАМИ, КАТЕГОРИЯМИ И БРЕНДАМИ ===================

@login_required
def admin_products_list(request):
    """Список товаров для админа (с логированием)"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    _log_activity(request.user, 'view', 'products_list', 'Просмотр списка товаров', request)

    q = (request.GET.get('q') or '').strip()
    category_id = request.GET.get('category')
    brand_id = request.GET.get('brand')
    available_filter = request.GET.get('available')

    qs = Product.objects.select_related('category', 'brand').prefetch_related('sizes', 'producttag_set__tag', 'images').all()

    if q:
        qs = qs.filter(Q(product_name__icontains=q) | Q(product_description__icontains=q))
    if category_id:
        qs = qs.filter(category_id=category_id)
    if brand_id:
        qs = qs.filter(brand_id=brand_id)
    if available_filter == 'yes':
        qs = qs.filter(is_available=True)
    elif available_filter == 'no':
        qs = qs.filter(is_available=False)

    qs = qs.order_by('-added_at')
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)

    categories = Category.objects.all()
    brands = Brand.objects.all()

    return render(request, 'main/admin/products_list.html', {
        'page_obj': page_obj,
        'q': q,
        'categories': categories,
        'brands': brands,
        'category_id': category_id,
        'brand_id': brand_id,
        'available_filter': available_filter,
    })

@login_required
def admin_products_import_csv(request):
    """Импорт товаров из CSV файла"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    if request.method == 'POST':
        if 'csv_file' not in request.FILES:
            messages.error(request, 'Файл не загружен')
            return redirect('admin_products_list')
        
        import csv
        import io
        from decimal import Decimal, InvalidOperation
        
        csv_file = request.FILES['csv_file']
        decoded_file = csv_file.read().decode('utf-8-sig')
        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)
        
        success_count = 0
        error_count = 0
        errors = []
        
        with transaction.atomic():
            for row_num, row in enumerate(reader, start=2):  # Начинаем с 2, т.к. 1 строка - заголовки
                try:
                    # Получаем обязательные поля
                    product_name = row.get('product_name', '').strip()
                    if not product_name:
                        errors.append(f"Строка {row_num}: отсутствует название товара")
                        error_count += 1
                        continue
                    
                    # Получаем цену
                    try:
                        price = Decimal(str(row.get('price', '0')).replace(',', '.'))
                    except (InvalidOperation, ValueError):
                        errors.append(f"Строка {row_num}: неверный формат цены")
                        error_count += 1
                        continue
                    
                    # Получаем категорию (по имени или ID)
                    category = None
                    category_name = row.get('category', '').strip()
                    if category_name:
                        category = Category.objects.filter(category_name=category_name).first()
                        if not category:
                            # Пытаемся найти по ID
                            try:
                                category = Category.objects.get(id=int(category_name))
                            except (ValueError, Category.DoesNotExist):
                                pass
                    
                    # Получаем бренд (по имени или ID)
                    brand = None
                    brand_name = row.get('brand', '').strip()
                    if brand_name:
                        brand = Brand.objects.filter(brand_name=brand_name).first()
                        if not brand:
                            try:
                                brand = Brand.objects.get(id=int(brand_name))
                            except (ValueError, Brand.DoesNotExist):
                                pass
                    
                    # Получаем остальные поля
                    discount = Decimal(str(row.get('discount', '0')).replace(',', '.'))
                    stock_quantity = int(row.get('stock_quantity', '0') or '0')
                    product_description = row.get('product_description', '').strip() or None
                    is_available = row.get('is_available', 'true').lower() in ('true', '1', 'yes', 'да')
                    
                    # Создаем товар
                    product = Product.objects.create(
                        product_name=product_name,
                        category=category,
                        brand=brand,
                        price=price,
                        discount=discount,
                        stock_quantity=stock_quantity,
                        product_description=product_description,
                        is_available=is_available
                    )
                    
                    success_count += 1
                    _log_activity(request.user, 'create', f'product_{product.id}', f'Импортирован товар: {product_name}', request)
                    
                except Exception as e:
                    errors.append(f"Строка {row_num}: {str(e)}")
                    error_count += 1
        
        if success_count > 0:
            messages.success(request, f'Успешно импортировано товаров: {success_count}')
        if error_count > 0:
            error_msg = f'Ошибок при импорте: {error_count}'
            if len(errors) <= 10:
                error_msg += f'. Детали: {"; ".join(errors[:10])}'
            else:
                error_msg += f'. Первые 10 ошибок: {"; ".join(errors[:10])}'
            messages.warning(request, error_msg)
        
        _log_activity(request.user, 'import', 'products_csv', f'Импорт товаров из CSV: успешно {success_count}, ошибок {error_count}', request)
        return redirect('admin_products_list')
    
    return redirect('admin_products_list')

@login_required
def admin_product_add(request):
    """Добавление товара админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    categories = Category.objects.all()
    brands = Brand.objects.all()
    suppliers = Supplier.objects.all()
    tags = Tag.objects.all()
    
    if request.method == 'POST':
        messages.error(request, 'Создание товара выполняется через новый API-интерфейс. Используйте элементы управления на странице.')
        return redirect('admin_products_list')
    
    return render(request, 'main/manager/product_edit.html', {
        'product': None,
        'categories': categories,
        'brands': brands,
        'suppliers': suppliers,
        'tags': tags,
        'product_images_json': json.dumps([]),
        'back_url_name': 'admin_products_list',
    })

@login_required
def admin_product_edit(request, product_id):
    """Редактирование товара админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    product = get_object_or_404(Product, pk=product_id)
    categories = Category.objects.all()
    brands = Brand.objects.all()
    suppliers = Supplier.objects.all()
    tags = Tag.objects.all()
    product_tags = [pt.tag.id for pt in product.producttag_set.all()]
    old_name = product.product_name
    
    if request.method == 'POST':
        messages.error(request, 'Редактирование товара выполняется через новый API-интерфейс. Пожалуйста, обновите страницу и повторите действия.')
        return redirect('admin_products_list')
    
    return render(request, 'main/manager/product_edit.html', {
        'product': product,
        'categories': categories,
        'brands': brands,
        'suppliers': suppliers,
        'tags': tags,
        'product_tags': product_tags,
        'product_images_json': json.dumps(_serialize_product_images(product)),
        'back_url_name': 'admin_products_list',
    })

@login_required
def admin_product_delete(request, product_id):
    """Удаление товара админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    product = get_object_or_404(Product, pk=product_id)
    product_name = product.product_name
    
    if request.method == 'POST':
        product.delete()
        _log_activity(request.user, 'delete', f'product_{product_id}', f'Удален товар: {product_name}', request)
        messages.success(request, f'Товар "{product_name}" удален')
        return redirect('admin_products_list')
    
    return render(request, 'main/manager/product_delete.html', {'product': product})

# =================== УПРАВЛЕНИЕ ЗАКАЗАМИ И ДОСТАВКОЙ ===================

@login_required
def admin_orders_list(request):
    """Список заказов для админа"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    _log_activity(request.user, 'view', 'orders_list', 'Просмотр списка заказов', request)
    
    # Собственная логика для админа, не используем manager_orders_list
    q = (request.GET.get('q') or '').strip()
    status_filter = request.GET.get('status')
    
    qs = Order.objects.select_related('user', 'address').prefetch_related('items').all().order_by('-created_at')
    
    if q:
        qs = qs.filter(Q(id__icontains=q) | Q(user__username__icontains=q) | Q(user__email__icontains=q))
    if status_filter:
        qs = qs.filter(order_status=status_filter)
    
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    
    return render(request, 'main/admin/orders_list.html', {
        'page_obj': page_obj,
        'q': q,
        'statuses': Order.ORDER_STATUSES
    })

@login_required
def admin_order_detail(request, order_id):
    """Детали заказа для админа"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    order = get_object_or_404(Order, pk=order_id)
    
    if request.method == 'POST':
        old_status = order.order_status
        new_status = request.POST.get('order_status')
        if new_status in dict(Order.ORDER_STATUSES):
            order.order_status = new_status
            order.save()
            
            if old_status != new_status:
                _log_activity(request.user, 'update', f'order_{order_id}', f'Изменен статус заказа: {old_status} -> {new_status}', request)
            
            # Если статус "отправлен", создаем или обновляем доставку
            if new_status == 'shipped':
                delivery, created = Delivery.objects.get_or_create(order=order)
                delivery.carrier_name = request.POST.get('carrier_name', '').strip() or None
                delivery.tracking_number = request.POST.get('tracking_number', '').strip() or None
                delivery.delivery_status = 'in_transit'
                if not delivery.shipped_at:
                    delivery.shipped_at = timezone.now()
                delivery.save()
                _log_activity(request.user, 'update', f'order_{order_id}', f'Назначен курьер: {delivery.carrier_name}', request)
            
            # Если статус меняется на "доставлен" и оплата была наличными - начисляем на счет организации БЕЗ налога
            if new_status == 'delivered' and old_status != 'delivered':
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"СТАТУС ИЗМЕНЕН НА 'delivered' для заказа #{order.id} (админ)")
                
                payment = Payment.objects.filter(order=order).first()
                logger.error(f"Payment для заказа #{order.id}: payment_method={payment.payment_method if payment else 'None'}, payment_status={payment.payment_status if payment else 'None'}, paid_from_balance={order.paid_from_balance}")
                
                # Проверяем, что оплата была наличными (cash) или pending (наличные в обработке)
                # и средства еще не были переведены на счет организации
                is_cash_payment = False
                if payment:
                    if payment.payment_method == 'cash':
                        is_cash_payment = True
                    elif payment.payment_method == 'pending' and not order.paid_from_balance:
                        is_cash_payment = True
                    elif payment.payment_status == 'pending' and payment.payment_method not in ['balance', 'card', 'visa', 'mastercard']:
                        is_cash_payment = True
                
                if is_cash_payment:
                    logger.error(f"Оплата наличными обнаружена для заказа #{order.id}")
                    
                    # Проверяем, не были ли уже переведены средства
                    org_payment_exists = OrganizationTransaction.objects.filter(
                        order=order,
                        transaction_type='order_payment'
                    ).exists()
                    
                    logger.error(f"Транзакция order_payment существует: {org_payment_exists}")
                    
                    if not org_payment_exists:
                        # Начисляем сумму заказа на счет организации, но БЕЗ налога
                        try:
                            org_account = OrganizationAccount.get_account()
                            balance_before = org_account.balance
                            tax_reserve_before = org_account.tax_reserve
                            
                            logger.error(f"Баланс организации до начисления: {balance_before}, сумма заказа: {order.total_amount}")
                            
                            org_account.balance += order.total_amount
                            # НЕ добавляем налог в резерв, так как оплата была наличными
                            org_account.save()
                            
                            logger.error(f"Баланс организации после начисления: {org_account.balance}")
                            
                            OrganizationTransaction.objects.create(
                                organization_account=org_account,
                                transaction_type='order_payment',
                                amount=order.total_amount,
                                description=f'Поступление от заказа #{order.id} (наличные, доставлен)',
                                order=order,
                                created_by=request.user,
                                balance_before=balance_before,
                                balance_after=org_account.balance,
                                tax_reserve_before=tax_reserve_before,
                                tax_reserve_after=tax_reserve_before,
                            )
                            logger.error(f"✅ Транзакция создана для заказа #{order.id}")
                        except Exception as e:
                            import traceback
                            logger.error(f"Ошибка при начислении средств на счет организации для заказа #{order.id}: {str(e)}")
                            logger.error(traceback.format_exc())
                    else:
                        logger.error(f"Транзакция уже существует для заказа #{order.id}, пропускаем начисление")
                else:
                    logger.error(f"Оплата не наличными для заказа #{order.id}: payment_method={payment.payment_method if payment else 'None'}")
            
            # Если статус меняется на "отменен" - обрабатываем отмену заказа
            if new_status == 'cancelled' and old_status != 'cancelled':
                try:
                    _process_order_cancellation(order, request.user)
                    messages.success(request, 'Заказ отменен. Деньги возвращены, товар возвращен на склад.')
                except ValueError as e:
                    messages.error(request, str(e))
                except Exception as e:
                    import traceback
                    logger.error(f"Ошибка при отмене заказа #{order.id}: {str(e)}")
                    logger.error(traceback.format_exc())
                    messages.error(request, f'Ошибка при отмене заказа: {str(e)}')
            
            messages.success(request, 'Статус заказа обновлен')
            return redirect('admin_order_detail', order_id=order.id)
    
    items = order.items.select_related('course').all()
    items_with_total = []
    for item in items:
        item_total = float(item.unit_price) * item.quantity
        items_with_total.append({
            'item': item,
            'total': item_total
        })
    delivery = getattr(order, 'delivery', None)
    
    return render(request, 'main/admin/order_detail.html', {
        'order': order,
        'items': items_with_total,
        'delivery': delivery,
        'statuses': Order.ORDER_STATUSES
    })

# =================== УПРАВЛЕНИЕ ПОДДЕРЖКОЙ ===================

@login_required
def admin_support_list(request):
    """Список обращений для админа с назначением ответственных"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    _log_activity(request.user, 'view', 'support_list', 'Просмотр списка обращений', request)
    
    q = (request.GET.get('q') or '').strip()
    status_filter = request.GET.get('status')
    assigned_filter = request.GET.get('assigned')
    
    qs = SupportTicket.objects.select_related('user', 'assigned_to').all().order_by('-created_at')
    
    if q:
        qs = qs.filter(Q(subject__icontains=q) | Q(message_text__icontains=q) | Q(user__username__icontains=q))
    if status_filter:
        qs = qs.filter(ticket_status=status_filter)
    if assigned_filter == 'assigned':
        qs = qs.exclude(assigned_to__isnull=True)
    elif assigned_filter == 'unassigned':
        qs = qs.filter(assigned_to__isnull=True)
    
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    
    # Список менеджеров для назначения
    managers = User.objects.filter(
        Q(is_superuser=True) |
        Q(profile__role__role_name__iexact='MANAGER') |
        Q(profile__role__role_name__iexact='manager') |
        Q(profile__role__role_name__iexact='менеджер') |
        Q(profile__role__role_name__iexact='ADMIN')
    ).distinct()
    
    return render(request, 'main/admin/support_list.html', {
        'page_obj': page_obj,
        'q': q,
        'status_filter': status_filter,
        'assigned_filter': assigned_filter,
        'managers': managers
    })

@login_required
def admin_support_detail(request, ticket_id):
    """Детали обращения для админа с назначением ответственного"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    ticket = get_object_or_404(SupportTicket, pk=ticket_id)
    
    if request.method == 'POST':
        old_assigned = ticket.assigned_to.username if ticket.assigned_to else None
        assigned_to_id = request.POST.get('assigned_to')
        
        if assigned_to_id:
            try:
                assigned_user = User.objects.get(pk=assigned_to_id)
                ticket.assigned_to = assigned_user
                new_assigned = assigned_user.username
                if old_assigned != new_assigned:
                    _log_activity(request.user, 'update', f'ticket_{ticket_id}', f'Назначен ответственный: {new_assigned}', request)
            except User.DoesNotExist:
                pass
        else:
            ticket.assigned_to = None
            if old_assigned:
                _log_activity(request.user, 'update', f'ticket_{ticket_id}', 'Снят ответственный', request)
        
        ticket.response_text = request.POST.get('response_text', '').strip()
        old_status = ticket.ticket_status
        ticket.ticket_status = request.POST.get('ticket_status', 'new')
        if old_status != ticket.ticket_status:
            _log_activity(request.user, 'update', f'ticket_{ticket_id}', f'Изменен статус: {old_status} -> {ticket.ticket_status}', request)
        
        ticket.save()
        _log_activity(request.user, 'update', f'ticket_{ticket_id}', 'Обновлено обращение в поддержку', request)
        messages.success(request, 'Обращение обновлено')
        return redirect('admin_support_detail', ticket_id=ticket.id)
    
    managers = User.objects.filter(
        Q(is_superuser=True) |
        Q(profile__role__role_name__iexact='MANAGER') |
        Q(profile__role__role_name__iexact='manager') |
        Q(profile__role__role_name__iexact='менеджер') |
        Q(profile__role__role_name__iexact='ADMIN')
    ).distinct()
    
    return render(request, 'main/admin/support_detail.html', {
        'ticket': ticket,
        'managers': managers
    })

# =================== АНАЛИТИКА И ОТЧЁТЫ ===================

@login_required
def admin_analytics(request):
    """Расширенная аналитика для админа"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    _log_activity(request.user, 'view', 'analytics', 'Просмотр аналитики', request)
    
    from django.db.models import Count, Sum, Avg, Q
    from django.utils import timezone
    from datetime import timedelta
    
    # Периоды
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    year_ago = today - timedelta(days=365)
    
    # Статистика по заказам
    orders_today = Order.objects.filter(created_at__date=today).count()
    orders_week = Order.objects.filter(created_at__date__gte=week_ago).count()
    orders_month = Order.objects.filter(created_at__date__gte=month_ago).count()
    orders_year = Order.objects.filter(created_at__date__gte=year_ago).count()
    
    revenue_today = Order.objects.filter(created_at__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    revenue_week = Order.objects.filter(created_at__date__gte=week_ago).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    revenue_month = Order.objects.filter(created_at__date__gte=month_ago).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    revenue_year = Order.objects.filter(created_at__date__gte=year_ago).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
    
    # Статистика по пользователям
    total_users = User.objects.count()
    active_users = UserProfile.objects.filter(user_status='active').count()
    blocked_users = UserProfile.objects.filter(user_status='blocked').count()
    new_users_month = User.objects.filter(date_joined__gte=month_ago).count()
    
    # Статистика по курсам
    total_products = Course.objects.count()
    available_products = Course.objects.filter(is_available=True).count()
    out_of_stock = 0  # для курсов нет склада
    
    # Курс недели/месяца
    product_of_week = Course.objects.filter(
        orderitem__order__created_at__date__gte=week_ago
    ).annotate(
        total_sold=Sum('orderitem__quantity'),
        total_revenue=Sum(F('orderitem__quantity') * F('orderitem__unit_price'))
    ).order_by('-total_sold').first()
    
    product_of_month = Course.objects.filter(
        orderitem__order__created_at__date__gte=month_ago
    ).annotate(
        total_sold=Sum('orderitem__quantity'),
        total_revenue=Sum(F('orderitem__quantity') * F('orderitem__unit_price'))
    ).order_by('-total_sold').first()
    
    # Популярные курсы
    popular_products = Course.objects.filter(
        orderitem__order__created_at__date__gte=month_ago
    ).annotate(
        total_sold=Sum('orderitem__quantity'),
        total_revenue=Sum(F('orderitem__quantity') * F('orderitem__unit_price'))
    ).order_by('-total_sold')[:10]
    
    # Статистика по категориям курсов
    category_stats = CourseCategory.objects.annotate(
        total_products=Count('course'),
        total_sold=Sum('course__orderitem__quantity'),
        total_revenue=Sum(F('course__orderitem__quantity') * F('course__orderitem__unit_price'))
    ).order_by('-total_revenue')[:10]
    
    # Активность пользователей
    active_users_list = User.objects.filter(
        order__created_at__gte=month_ago
    ).annotate(
        total_orders=Count('order'),
        total_spent=Sum('order__total_amount')
    ).order_by('-total_spent')[:10]
    
    # Статистика по налогам (3НФ: tax_amount — свойство, не поле)
    total_tax_month = sum(
        (o.tax_amount for o in Order.objects.filter(
            created_at__date__gte=month_ago,
            order_status__in=['paid', 'shipped', 'delivered']
        )),
        Decimal('0')
    )
    total_tax_year = sum(
        (o.tax_amount for o in Order.objects.filter(
            created_at__date__gte=year_ago,
            order_status__in=['paid', 'shipped', 'delivered']
        )),
        Decimal('0')
    )
    
    # Счет организации
    org_account = OrganizationAccount.get_account()
    
    stats = {
        'orders_today': orders_today,
        'orders_week': orders_week,
        'orders_month': orders_month,
        'orders_year': orders_year,
        'revenue_today': revenue_today,
        'revenue_week': revenue_week,
        'revenue_month': revenue_month,
        'revenue_year': revenue_year,
        'total_users': total_users,
        'active_users': active_users,
        'blocked_users': blocked_users,
        'new_users_month': new_users_month,
        'total_products': total_products,
        'available_products': available_products,
        'out_of_stock': out_of_stock,
        'product_of_week': product_of_week,
        'product_of_month': product_of_month,
        'popular_products': popular_products,
        'category_stats': category_stats,
        'active_users_list': active_users_list,
        'total_tax_month': total_tax_month,
        'total_tax_year': total_tax_year,
        'org_balance': org_account.balance,
        'org_tax_reserve': org_account.tax_reserve,
    }
    
    return render(request, 'main/admin/analytics.html', stats)

@login_required
def admin_analytics_export_csv(request):
    """Расширенный экспорт отчётов в CSV"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    _log_activity(request.user, 'export', 'csv_report', 'Экспорт отчёта в CSV', request)
    
    return manager_analytics_export_csv(request)

@login_required
def admin_org_account(request):
    """Управление счетом организации"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    org_account = OrganizationAccount.get_account()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'withdraw':
            # Вывод средств на карту админа
            try:
                amount = Decimal(request.POST.get('amount', '0'))
            except (ValueError, InvalidOperation):
                messages.error(request, "Неверный формат суммы.")
                return redirect('admin_org_account')
            
            card_id = request.POST.get('card_id')
            
            if amount <= 0:
                messages.error(request, "Сумма должна быть больше нуля.")
                return redirect('admin_org_account')
            
            # Обновляем объект из БД для актуальных данных
            org_account.refresh_from_db()
            
            if not org_account.can_withdraw(amount):
                messages.error(request, f"Недостаточно средств на счете организации. Доступно: {org_account.balance} ₽, запрошено: {amount} ₽")
                return redirect('admin_org_account')
            
            if not card_id:
                messages.error(request, "Выберите карту для вывода средств.")
                return redirect('admin_org_account')
            
            try:
                card = SavedPaymentMethod.objects.get(id=card_id, user=request.user)
            except SavedPaymentMethod.DoesNotExist:
                messages.error(request, "Карта не найдена.")
                return redirect('admin_org_account')
            
            try:
                with transaction.atomic():
                    # Блокируем запись для обновления
                    org_account = OrganizationAccount.objects.select_for_update().get(pk=org_account.pk)
                    
                    # Повторная проверка после блокировки
                    if not org_account.can_withdraw(amount):
                        messages.error(request, f"Недостаточно средств на счете организации. Доступно: {org_account.balance} ₽, запрошено: {amount} ₽")
                        return redirect('admin_org_account')
                    
                    balance_before = org_account.balance
                    tax_reserve_before = org_account.tax_reserve
                    org_account.balance -= amount
                    org_account.save()
                    balance_after = org_account.balance
                    card.balance += amount
                    card.save()
                    OrganizationTransaction.objects.create(
                        organization_account=org_account,
                        transaction_type='withdrawal',
                        amount=amount,
                        description=f'Вывод на карту {card.mask_card_number()}',
                        created_by=request.user,
                        balance_before=balance_before,
                        balance_after=balance_after,
                        tax_reserve_before=tax_reserve_before,
                        tax_reserve_after=tax_reserve_before,
                    )
                    
                    CardTransaction.objects.create(
                        saved_payment_method=card,
                        transaction_type='deposit',
                        amount=amount,
                        description=f'Поступление со счета организации',
                        status='completed'
                    )
                    
                    _log_activity(request.user, 'update', 'org_account', f'Вывод {amount} ₽ на карту {card.mask_card_number()}', request)
                    messages.success(request, f"Средства в размере {amount} ₽ переведены на карту {card.mask_card_number()}")
            except Exception as e:
                messages.error(request, f"Ошибка при выводе средств: {str(e)}")
                return redirect('admin_org_account')
        
        elif action == 'pay_tax':
            # Оплата налога
            try:
                amount = Decimal(request.POST.get('amount', '0'))
            except (ValueError, InvalidOperation):
                messages.error(request, "Неверный формат суммы.")
                return redirect('admin_org_account')
            
            if amount <= 0:
                messages.error(request, "Сумма должна быть больше нуля.")
                return redirect('admin_org_account')
            
            # Обновляем объект из БД для актуальных данных
            org_account.refresh_from_db()
            
            if not org_account.can_pay_tax(amount):
                if org_account.tax_reserve < amount:
                    messages.error(request, f"Недостаточно средств в резерве на налоги. Доступно: {org_account.tax_reserve} ₽, запрошено: {amount} ₽")
                elif org_account.balance < amount:
                    messages.error(request, f"Недостаточно средств на счете организации. Доступно: {org_account.balance} ₽, запрошено: {amount} ₽")
                else:
                    messages.error(request, f"Недостаточно средств для оплаты налога.")
                return redirect('admin_org_account')
            
            try:
                with transaction.atomic():
                    # Блокируем запись для обновления
                    org_account = OrganizationAccount.objects.select_for_update().get(pk=org_account.pk)
                    
                    # Повторная проверка после блокировки
                    if not org_account.can_pay_tax(amount):
                        if org_account.tax_reserve < amount:
                            messages.error(request, f"Недостаточно средств в резерве на налоги. Доступно: {org_account.tax_reserve} ₽, запрошено: {amount} ₽")
                        elif org_account.balance < amount:
                            messages.error(request, f"Недостаточно средств на счете организации. Доступно: {org_account.balance} ₽, запрошено: {amount} ₽")
                        else:
                            messages.error(request, f"Недостаточно средств для оплаты налога.")
                        return redirect('admin_org_account')
                    
                    balance_before = org_account.balance
                    tax_reserve_before = org_account.tax_reserve
                    org_account.balance -= amount
                    org_account.tax_reserve -= amount
                    org_account.save()
                    OrganizationTransaction.objects.create(
                        organization_account=org_account,
                        transaction_type='tax_payment',
                        amount=amount,
                        description=f'Оплата налога',
                        created_by=request.user,
                        balance_before=balance_before,
                        balance_after=org_account.balance,
                        tax_reserve_before=tax_reserve_before,
                        tax_reserve_after=org_account.tax_reserve,
                    )
                    
                    _log_activity(request.user, 'update', 'org_account', f'Оплата налога {amount} ₽', request)
                    messages.success(request, f"Налог в размере {amount} ₽ оплачен")
            except Exception as e:
                messages.error(request, f"Ошибка при оплате налога: {str(e)}")
                return redirect('admin_org_account')
        
        return redirect('admin_org_account')
    
    # Получаем транзакции
    transactions = OrganizationTransaction.objects.filter(
        organization_account=org_account
    ).select_related('order', 'created_by').order_by('-created_at')[:50]
    
    # Получаем карты админа
    admin_cards = SavedPaymentMethod.objects.filter(user=request.user)
    
    return render(request, 'main/admin/org_account.html', {
        'org_account': org_account,
        'transactions': transactions,
        'admin_cards': admin_cards,
    })

@login_required
def admin_analytics_export_pdf(request):
    """Расширенный экспорт отчётов в PDF с диаграммами"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    _log_activity(request.user, 'export', 'pdf_report', 'Экспорт отчёта в PDF', request)
    
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.utils import ImageReader
        from io import BytesIO
        from django.db.models import Sum, Count
        from django.utils import timezone
        from django.http import HttpResponse
        from datetime import timedelta
        import base64
        import platform
        import os
        
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        y = height - 20 * mm
        line_height = 6 * mm
        left_margin = 15 * mm
        
        # Используем шрифт с поддержкой кириллицы
        font_name = "Helvetica"
        font_bold = "Helvetica-Bold"
        
        # Пытаемся использовать системные шрифты с поддержкой кириллицы
        try:
            system = platform.system()
            arial_found = False
            
            if system == 'Windows':
                font_dir = r'C:\Windows\Fonts'
                arial_variants = ['arial.ttf', 'Arial.ttf', 'ARIAL.TTF', 'arialuni.ttf']
                arial_bold_variants = ['arialbd.ttf', 'Arialbd.ttf', 'ARIALBD.TTF']
                
                for variant in arial_variants:
                    arial_path = os.path.join(font_dir, variant)
                    if os.path.exists(arial_path):
                        try:
                            pdfmetrics.registerFont(TTFont('Arial', arial_path))
                            font_name = 'Arial'
                            arial_found = True
                            break
                        except Exception:
                            continue
                
                if arial_found:
                    for variant in arial_bold_variants:
                        arial_bold_path = os.path.join(font_dir, variant)
                        if os.path.exists(arial_bold_path):
                            try:
                                pdfmetrics.registerFont(TTFont('Arial-Bold', arial_bold_path))
                                font_bold = 'Arial-Bold'
                                break
                            except Exception:
                                pass
            elif system == 'Linux':
                dejavu_fonts = [
                    ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
                    ('/usr/share/fonts/TTF/DejaVuSans.ttf', '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf'),
                    ('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'),
                ]
                
                for regular_path, bold_path in dejavu_fonts:
                    if os.path.exists(regular_path):
                        try:
                            pdfmetrics.registerFont(TTFont('DejaVuSans', regular_path))
                            font_name = 'DejaVuSans'
                            arial_found = True
                            
                            if os.path.exists(bold_path):
                                try:
                                    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', bold_path))
                                    font_bold = 'DejaVuSans-Bold'
                                except Exception:
                                    font_bold = 'DejaVuSans'
                            else:
                                font_bold = 'DejaVuSans'
                            break
                        except Exception:
                            continue
        except Exception:
            pass
        
        def draw(text, bold=False, font_size=10):
            nonlocal y
            current_font = font_bold if bold else font_name
            c.setFont(current_font, font_size)
            c.drawString(left_margin, y, str(text))
            y -= line_height
        
        # Заголовок
        draw("Отчёт по аналитике", bold=True, font_size=18)
        draw(f"Дата: {timezone.now().strftime('%d.%m.%Y %H:%M')}")
        y -= 10 * mm
        
        # Статистика по периодам
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        year_ago = today - timedelta(days=365)
        
        orders_today = Order.objects.filter(created_at__date=today).count()
        orders_week = Order.objects.filter(created_at__date__gte=week_ago).count()
        orders_month = Order.objects.filter(created_at__date__gte=month_ago).count()
        orders_year = Order.objects.filter(created_at__date__gte=year_ago).count()
        
        revenue_today = Order.objects.filter(created_at__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
        revenue_week = Order.objects.filter(created_at__date__gte=week_ago).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
        revenue_month = Order.objects.filter(created_at__date__gte=month_ago).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
        revenue_year = Order.objects.filter(created_at__date__gte=year_ago).aggregate(Sum('total_amount'))['total_amount__sum'] or Decimal('0')
        
        draw("Статистика по заказам:", bold=True, font_size=14)
        draw(f"Сегодня: {orders_today} заказов, {revenue_today} ₽")
        draw(f"За неделю: {orders_week} заказов, {revenue_week} ₽")
        draw(f"За месяц: {orders_month} заказов, {revenue_month} ₽")
        draw(f"За год: {orders_year} заказов, {revenue_year} ₽")
        y -= 5 * mm
        
        # Статистика по пользователям
        total_users = User.objects.count()
        active_users = UserProfile.objects.filter(user_status='active').count()
        blocked_users = UserProfile.objects.filter(user_status='blocked').count()
        new_users_month = User.objects.filter(date_joined__gte=month_ago).count()
        
        draw("Статистика по пользователям:", bold=True, font_size=14)
        draw(f"Всего: {total_users}")
        draw(f"Активных: {active_users}")
        draw(f"Заблокированных: {blocked_users}")
        draw(f"Новых за месяц: {new_users_month}")
        y -= 5 * mm
        
        # Статистика по курсам
        total_products = Course.objects.count()
        available_products = Course.objects.filter(is_available=True).count()
        
        draw("Статистика по курсам:", bold=True, font_size=14)
        draw(f"Всего: {total_products}")
        draw(f"Доступных: {available_products}")
        y -= 10 * mm
        
        # Добавляем диаграммы, если они переданы через POST
        if request.method == 'POST':
            chart_images = {}
            
            # Получаем изображения диаграмм из POST данных
            revenue_chart = request.POST.get('revenue_chart')
            users_chart = request.POST.get('users_chart')
            categories_chart = request.POST.get('categories_chart')
            
            # Функция для добавления изображения в PDF
            def add_image_to_pdf(base64_data, title, max_width=170*mm, max_height=100*mm):
                nonlocal y
                if not base64_data:
                    return
                
                try:
                    # Удаляем префикс data:image/png;base64, если есть
                    if ',' in base64_data:
                        base64_data = base64_data.split(',')[1]
                    
                    # Декодируем base64
                    image_data = base64.b64decode(base64_data)
                    image_io = BytesIO(image_data)
                    
                    # Создаем ImageReader
                    img = ImageReader(image_io)
                    img_width, img_height = img.getSize()
                    
                    # Вычисляем размеры с сохранением пропорций
                    scale = min(max_width / img_width, max_height / img_height, 1.0)
                    display_width = img_width * scale
                    display_height = img_height * scale
                    
                    # Проверяем, нужно ли создать новую страницу
                    if y - display_height - 20 * mm < 30 * mm:
                        c.showPage()
                        y = height - 20 * mm
                    
                    # Добавляем заголовок диаграммы
                    draw(title, bold=True, font_size=12)
                    y -= 3 * mm
                    
                    # Добавляем изображение
                    c.drawImage(img, left_margin, y - display_height, width=display_width, height=display_height)
                    y -= display_height + 10 * mm
                    
                except Exception as e:
                    # Если не удалось добавить изображение, просто пропускаем
                    pass
            
            # Добавляем диаграммы
            if revenue_chart:
                add_image_to_pdf(revenue_chart, "Выручка по периодам", max_width=170*mm, max_height=80*mm)
            
            if users_chart:
                add_image_to_pdf(users_chart, "Распределение пользователей", max_width=170*mm, max_height=80*mm)
            
            if categories_chart:
                add_image_to_pdf(categories_chart, "Статистика по категориям", max_width=170*mm, max_height=100*mm)
        
        # Популярные курсы
        draw("Популярные курсы (за месяц):", bold=True, font_size=14)
        popular = Course.objects.filter(
            orderitem__order__created_at__gte=month_ago
        ).annotate(
            total_sold=Sum('orderitem__quantity')
        ).order_by('-total_sold')[:10]
        
        for i, course in enumerate(popular, 1):
            if y < 50 * mm:
                c.showPage()
                y = height - 20 * mm
            draw(f"{i}. {course.title} - продано: {course.total_sold or 0} шт.")
        
        c.showPage()
        c.save()
        
        buffer.seek(0)
        pdf_content = buffer.getvalue()
        buffer.close()
        
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="отчет_по_аналитике.pdf"'
        return response
        
    except ImportError:
        messages.error(request, "PDF генератор не установлен. Пожалуйста, установите reportlab.")
        return redirect('admin_analytics')
    except Exception as e:
        messages.error(request, f"Ошибка при генерации PDF: {str(e)}")
        return redirect('admin_analytics')

# =================== ЛОГИ АКТИВНОСТИ И АУДИТ ===================

@login_required
def admin_activity_logs(request):
    """Просмотр логов активности пользователей"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    _log_activity(request.user, 'view', 'activity_logs', 'Просмотр логов активности', request)
    
    q = (request.GET.get('q') or '').strip()
    action_filter = request.GET.get('action')
    user_filter = request.GET.get('user')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    qs = ActivityLog.objects.select_related('user').all().order_by('-created_at')
    
    if q:
        qs = qs.filter(Q(action_description__icontains=q) | Q(target_object__icontains=q))
    if action_filter:
        qs = qs.filter(action_type=action_filter)
    if user_filter:
        qs = qs.filter(user_id=user_filter)
    if date_from:
        try:
            from datetime import datetime
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            qs = qs.filter(created_at__gte=date_from_obj)
        except ValueError:
            pass
    if date_to:
        try:
            from datetime import datetime
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            qs = qs.filter(created_at__lte=date_to_obj)
        except ValueError:
            pass
    
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    
    # Уникальные типы действий для фильтра
    action_types = ActivityLog.objects.values_list('action_type', flat=True).distinct()
    
    # Список пользователей для фильтра
    users_with_logs = User.objects.filter(activitylog__isnull=False).distinct()
    
    return render(request, 'main/admin/activity_logs.html', {
        'page_obj': page_obj,
        'q': q,
        'action_filter': action_filter,
        'user_filter': user_filter,
        'date_from': date_from,
        'date_to': date_to,
        'action_types': action_types,
        'users_with_logs': users_with_logs
    })

@login_required
def admin_activity_log_detail(request, log_id):
    """Детали лога активности"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    log = get_object_or_404(ActivityLog, pk=log_id)
    
    return render(request, 'main/admin/activity_log_detail.html', {'log': log})

# =================== УПРАВЛЕНИЕ ПРОМОКОДАМИ ===================

@login_required
def admin_promotions_list(request):
    """Список промокодов для админа"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    _log_activity(request.user, 'view', 'promotions_list', 'Просмотр списка промокодов', request)
    
    q = (request.GET.get('q') or '').strip()
    promotions = Promotion.objects.all().order_by('-id')
    
    if q:
        promotions = promotions.filter(
            Q(promo_code__icontains=q) | Q(promo_description__icontains=q)
        )
    
    paginator = Paginator(promotions, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'main/admin/promotions_list.html', {
        'page_obj': page_obj,
        'q': q
    })

@login_required
def admin_promotion_add(request):
    """Добавление промокода админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    if request.method == 'POST':
        try:
            promo_code = request.POST.get('promo_code', '').strip().upper()
            promo_description = request.POST.get('promo_description', '').strip()
            discount = Decimal(request.POST.get('discount', '0'))
            start_date_str = request.POST.get('start_date', '').strip()
            end_date_str = request.POST.get('end_date', '').strip()
            is_active = request.POST.get('is_active') == 'on'
            
            if not promo_code:
                messages.error(request, 'Код промокода обязателен')
                return render(request, 'main/admin/promotion_edit.html', {'promotion': None})
            
            start_date = None
            end_date = None
            if start_date_str:
                try:
                    from datetime import datetime
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            if end_date_str:
                try:
                    from datetime import datetime
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            
            promotion = Promotion.objects.create(
                promo_code=promo_code,
                promo_description=promo_description,
                discount=discount,
                start_date=start_date,
                end_date=end_date,
                is_active=is_active
            )
            
            _log_activity(request.user, 'create', f'promotion_{promotion.id}', f'Создан промокод: {promo_code}', request)
            messages.success(request, f'Промокод {promo_code} создан')
            return redirect('admin_promotions_list')
        except Exception as e:
            messages.error(request, f'Ошибка при создании промокода: {str(e)}')
    
    return render(request, 'main/admin/promotion_edit.html', {'promotion': None})

@login_required
def admin_promotion_edit(request, promo_id):
    """Редактирование промокода админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    promotion = get_object_or_404(Promotion, pk=promo_id)
    
    if request.method == 'POST':
        try:
            old_code = promotion.promo_code
            promotion.promo_code = request.POST.get('promo_code', '').strip().upper()
            promotion.promo_description = request.POST.get('promo_description', '').strip()
            promotion.discount = Decimal(request.POST.get('discount', '0'))
            start_date_str = request.POST.get('start_date', '').strip()
            end_date_str = request.POST.get('end_date', '').strip()
            promotion.is_active = request.POST.get('is_active') == 'on'
            
            if start_date_str:
                try:
                    from datetime import datetime
                    promotion.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            else:
                promotion.start_date = None
                
            if end_date_str:
                try:
                    from datetime import datetime
                    promotion.end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            else:
                promotion.end_date = None
            
            promotion.save()
            _log_activity(request.user, 'update', f'promotion_{promo_id}', f'Обновлен промокод: {old_code}', request)
            messages.success(request, 'Промокод обновлен')
            return redirect('admin_promotions_list')
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении: {str(e)}')
    
    return render(request, 'main/admin/promotion_edit.html', {'promotion': promotion})

@login_required
def admin_promotion_delete(request, promo_id):
    """Удаление промокода админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    promotion = get_object_or_404(Promotion, pk=promo_id)
    
    if request.method == 'POST':
        promo_code = promotion.promo_code
        promotion.delete()
        _log_activity(request.user, 'delete', f'promotion_{promo_id}', f'Удален промокод: {promo_code}', request)
        messages.success(request, f'Промокод {promo_code} удален')
        return redirect('admin_promotions_list')
    
    return render(request, 'main/admin/promotion_delete.html', {'promotion': promotion})

# =================== УПРАВЛЕНИЕ КАТЕГОРИЯМИ И БРЕНДАМИ ===================

@login_required
def admin_categories_list(request):
    """Список категорий и брендов для админа"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    _log_activity(request.user, 'view', 'categories_list', 'Просмотр категорий и брендов', request)
    
    categories = Category.objects.all().order_by('category_name')
    brands = Brand.objects.all().order_by('brand_name')
    
    return render(request, 'main/admin/categories_list.html', {
        'categories': categories,
        'brands': brands
    })

@login_required
def admin_categories_import_csv(request):
    """Импорт категорий из CSV файла"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    if request.method == 'POST':
        if 'csv_file' not in request.FILES:
            messages.error(request, 'Файл не загружен')
            return redirect('admin_categories_list')
        
        import csv
        import io
        
        csv_file = request.FILES['csv_file']
        decoded_file = csv_file.read().decode('utf-8-sig')
        io_string = io.StringIO(decoded_file)
        reader = csv.DictReader(io_string)
        
        success_count = 0
        error_count = 0
        errors = []
        
        with transaction.atomic():
            for row_num, row in enumerate(reader, start=2):
                try:
                    # Получаем обязательные поля
                    category_name = row.get('category_name', '').strip()
                    if not category_name:
                        errors.append(f"Строка {row_num}: отсутствует название категории")
                        error_count += 1
                        continue
                    
                    # Проверяем, не существует ли уже такая категория
                    if Category.objects.filter(category_name=category_name).exists():
                        errors.append(f"Строка {row_num}: категория '{category_name}' уже существует")
                        error_count += 1
                        continue
                    
                    # Получаем родительскую категорию
                    parent_category = None
                    parent_name = row.get('parent_category', '').strip()
                    if parent_name:
                        parent_category = Category.objects.filter(category_name=parent_name).first()
                        if not parent_category:
                            try:
                                parent_category = Category.objects.get(id=int(parent_name))
                            except (ValueError, Category.DoesNotExist):
                                pass
                    
                    # Создаем категорию
                    category = Category.objects.create(
                        category_name=category_name,
                        category_description=row.get('category_description', '').strip() or None,
                        parent_category=parent_category
                    )
                    
                    success_count += 1
                    _log_activity(request.user, 'create', f'category_{category.id}', f'Импортирована категория: {category_name}', request)
                    
                except Exception as e:
                    errors.append(f"Строка {row_num}: {str(e)}")
                    error_count += 1
        
        if success_count > 0:
            messages.success(request, f'Успешно импортировано категорий: {success_count}')
        if error_count > 0:
            error_msg = f'Ошибок при импорте: {error_count}'
            if len(errors) <= 10:
                error_msg += f'. Детали: {"; ".join(errors[:10])}'
            else:
                error_msg += f'. Первые 10 ошибок: {"; ".join(errors[:10])}'
            messages.warning(request, error_msg)
        
        _log_activity(request.user, 'import', 'categories_csv', f'Импорт категорий из CSV: успешно {success_count}, ошибок {error_count}', request)
        return redirect('admin_categories_list')
    
    return redirect('admin_categories_list')

@login_required
def admin_category_add(request):
    """Добавление категории админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    if request.method == 'POST':
        try:
            category = Category.objects.create(
                category_name=request.POST.get('category_name', '').strip(),
                category_description=request.POST.get('category_description', '').strip() or None,
                parent_category_id=request.POST.get('parent_category_id') or None
            )
            _log_activity(request.user, 'create', f'category_{category.id}', f'Создана категория: {category.category_name}', request)
            messages.success(request, 'Категория добавлена')
            return redirect('admin_categories_list')
        except Exception as e:
            messages.error(request, f'Ошибка при создании категории: {str(e)}')
    
    categories = Category.objects.all()
    return render(request, 'main/admin/category_edit.html', {
        'category': None,
        'categories': categories
    })

@login_required
def admin_category_edit(request, category_id):
    """Редактирование категории админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    category = get_object_or_404(Category, pk=category_id)
    
    if request.method == 'POST':
        try:
            old_name = category.category_name
            category.category_name = request.POST.get('category_name', '').strip()
            category.category_description = request.POST.get('category_description', '').strip() or None
            category.parent_category_id = request.POST.get('parent_category_id') or None
            category.save()
            _log_activity(request.user, 'update', f'category_{category_id}', f'Обновлена категория: {old_name} -> {category.category_name}', request)
            messages.success(request, 'Категория обновлена')
            return redirect('admin_categories_list')
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении: {str(e)}')
    
    categories = Category.objects.exclude(pk=category_id)
    return render(request, 'main/admin/category_edit.html', {
        'category': category,
        'categories': categories
    })

@login_required
def admin_brand_add(request):
    """Добавление бренда админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    if request.method == 'POST':
        try:
            brand = Brand.objects.create(
                brand_name=request.POST.get('brand_name', '').strip(),
                brand_country=request.POST.get('brand_country', '').strip() or None,
                brand_description=request.POST.get('brand_description', '').strip() or None
            )
            _log_activity(request.user, 'create', f'brand_{brand.id}', f'Создан бренд: {brand.brand_name}', request)
            messages.success(request, 'Бренд добавлен')
            return redirect('admin_categories_list')
        except Exception as e:
            messages.error(request, f'Ошибка при создании бренда: {str(e)}')
    
    return render(request, 'main/admin/brand_edit.html', {'brand': None})

@login_required
def admin_brand_edit(request, brand_id):
    """Редактирование бренда админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    brand = get_object_or_404(Brand, pk=brand_id)
    
    if request.method == 'POST':
        try:
            old_name = brand.brand_name
            brand.brand_name = request.POST.get('brand_name', '').strip()
            brand.brand_country = request.POST.get('brand_country', '').strip() or None
            brand.brand_description = request.POST.get('brand_description', '').strip() or None
            brand.save()
            _log_activity(request.user, 'update', f'brand_{brand_id}', f'Обновлен бренд: {old_name} -> {brand.brand_name}', request)
            messages.success(request, 'Бренд обновлен')
            return redirect('admin_categories_list')
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении: {str(e)}')
    
    return render(request, 'main/admin/brand_edit.html', {'brand': brand})

# =================== УПРАВЛЕНИЕ ПОСТАВЩИКАМИ ===================

@login_required
def admin_suppliers_list(request):
    """Список поставщиков для админа"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    _log_activity(request.user, 'view', 'suppliers_list', 'Просмотр списка поставщиков', request)
    
    q = (request.GET.get('q') or '').strip()
    suppliers = Supplier.objects.all().order_by('supplier_name')
    
    if q:
        suppliers = suppliers.filter(
            Q(supplier_name__icontains=q) | 
            Q(contact_person__icontains=q) |
            Q(contact_email__icontains=q)
        )
    
    paginator = Paginator(suppliers, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'main/admin/suppliers_list.html', {
        'page_obj': page_obj,
        'q': q
    })

@login_required
def admin_supplier_add(request):
    """Добавление поставщика админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    if request.method == 'POST':
        try:
            supplier = Supplier.objects.create(
                supplier_name=request.POST.get('supplier_name', '').strip(),
                contact_person=request.POST.get('contact_person', '').strip() or None,
                contact_phone=request.POST.get('contact_phone', '').strip() or None,
                contact_email=request.POST.get('contact_email', '').strip() or None,
                supply_country=request.POST.get('supply_country', '').strip() or None,
                delivery_cost=Decimal(request.POST.get('delivery_cost', '0')) if request.POST.get('delivery_cost') else None,
                supplier_type=request.POST.get('supplier_type', '').strip() or None
            )
            _log_activity(request.user, 'create', f'supplier_{supplier.id}', f'Создан поставщик: {supplier.supplier_name}', request)
            messages.success(request, 'Поставщик добавлен')
            return redirect('admin_suppliers_list')
        except Exception as e:
            messages.error(request, f'Ошибка при создании поставщика: {str(e)}')
    
    return render(request, 'main/admin/supplier_edit.html', {'supplier': None})

@login_required
def admin_supplier_edit(request, supplier_id):
    """Редактирование поставщика админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    
    if request.method == 'POST':
        try:
            old_name = supplier.supplier_name
            supplier.supplier_name = request.POST.get('supplier_name', '').strip()
            supplier.contact_person = request.POST.get('contact_person', '').strip() or None
            supplier.contact_phone = request.POST.get('contact_phone', '').strip() or None
            supplier.contact_email = request.POST.get('contact_email', '').strip() or None
            supplier.supply_country = request.POST.get('supply_country', '').strip() or None
            delivery_cost_str = request.POST.get('delivery_cost', '').strip()
            supplier.delivery_cost = Decimal(delivery_cost_str) if delivery_cost_str else None
            supplier.supplier_type = request.POST.get('supplier_type', '').strip() or None
            supplier.save()
            _log_activity(request.user, 'update', f'supplier_{supplier_id}', f'Обновлен поставщик: {old_name} -> {supplier.supplier_name}', request)
            messages.success(request, 'Поставщик обновлен')
            return redirect('admin_suppliers_list')
        except Exception as e:
            messages.error(request, f'Ошибка при обновлении: {str(e)}')
    
    return render(request, 'main/admin/supplier_edit.html', {'supplier': supplier})

@login_required
def admin_supplier_delete(request, supplier_id):
    """Удаление поставщика админом"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    
    if request.method == 'POST':
        supplier_name = supplier.supplier_name
        supplier.delete()
        _log_activity(request.user, 'delete', f'supplier_{supplier_id}', f'Удален поставщик: {supplier_name}', request)
        messages.success(request, f'Поставщик {supplier_name} удален')
        return redirect('admin_suppliers_list')
    
    return render(request, 'main/admin/supplier_delete.html', {'supplier': supplier})

# =================== УПРАВЛЕНИЕ БЭКАПАМИ БАЗЫ ДАННЫХ ===================

@login_required
def admin_backups_list(request):
    """Список бэкапов базы данных"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    try:
        _log_activity(request.user, 'view', 'backups_list', 'Просмотр списка бэкапов', request)
    except Exception as e:
        # Если не удалось залогировать, продолжаем работу
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f'Не удалось залогировать просмотр бэкапов: {str(e)}')
    
    try:
        backups = DatabaseBackup.objects.all().order_by('-created_at')
        
        paginator = Paginator(backups, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        return render(request, 'main/admin/backups_list.html', {
            'page_obj': page_obj
        })
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Ошибка при получении списка бэкапов: {str(e)}', exc_info=True)
        
        # Если ошибка подключения к БД, показываем сообщение
        error_msg = str(e)
        if 'UnicodeDecodeError' in error_msg or 'codec' in error_msg.lower():
            messages.error(request, 'Ошибка подключения к базе данных. Возможно, база данных повреждена или удалена. Используйте экстренное восстановление.')
            return render(request, 'main/admin/backups_list.html', {
                'page_obj': None,
                'error': 'Ошибка подключения к базе данных'
            })
        else:
            messages.error(request, f'Ошибка при загрузке списка бэкапов: {error_msg}')
            return render(request, 'main/admin/backups_list.html', {
                'page_obj': None,
                'error': error_msg
            })

@login_required
def admin_backup_create(request):
    """
    Создание полного бэкапа базы данных.
    
    Сохраняет ВСЕ данные системы MPTCOURSE:
    - Пользователи, профили, роли, адреса, настройки (auth_user, userprofile, role, useraddress, usersettings)
    - Курсы, категории, фото, страницы контента (course, course_category, course_image, course_content_page)
    - Уроки, страницы уроков, прохождения, уведомления (lesson, lesson_page, lesson_completion, user_notification)
    - Покупки курсов, просмотры контента, опросы, отзывы, избранное (course_purchase, course_content_view, course_survey, course_review, course_favorite, course_refund_request)
    - Корзины и элементы (cart, cartitem)
    - Заказы, элементы заказов, платежи (order, orderitem, payment)
    - Чеки и элементы (receipt, receiptitem)
    - Промокоды и использование (promotion, promo_usage)
    - Балансы, карты, транзакции (balancetransaction, savedpaymentmethod, cardtransaction)
    - Счёт организации (organizationaccount, organizationtransaction)
    - Поддержка, логи активности, настройки чеков (supportticket, activitylog, receiptconfig)
    - И все таблицы Django (сессии, миграции, content types и т.д.)
    """
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    if request.method == 'POST':
        try:
            from django.conf import settings
            import shutil
            from datetime import datetime
            import os
            
            # Список ключевых таблиц для проверки/описания бэкапа (имена как db_table в моделях)
            tables_to_check = [
                ('auth_user', 'Пользователи'),
                ('userprofile', 'Профили'),
                ('role', 'Роли'),
                ('course', 'Курсы'),
                ('course_category', 'Категории курсов'),
                ('course_purchase', 'Покупки курсов'),
                ('lesson', 'Уроки'),
                ('lesson_page', 'Страницы уроков'),
                ('lesson_completion', 'Прохождения уроков'),
                ('cart', 'Корзины'),
                ('cartitem', 'Элементы корзины'),
                ('order', 'Заказы'),
                ('orderitem', 'Элементы заказов'),
                ('payment', 'Платежи'),
                ('receipt', 'Чеки'),
                ('receiptitem', 'Элементы чеков'),
                ('balancetransaction', 'Транзакции баланса'),
                ('activitylog', 'Логи активности'),
                ('usersettings', 'Настройки пользователей'),
                ('course_favorite', 'Избранные курсы'),
                ('supportticket', 'Билеты поддержки'),
            ]
            backup_stats = {}
            
            # Получаем настройки базы данных
            db_config = settings.DATABASES['default']
            db_engine = db_config.get('ENGINE', '')
            
            # Закрываем все соединения с БД перед созданием бэкапа
            from django.db import connections
            for conn in connections.all():
                conn.close()
            
            # Создаем директорию для бэкапов, если её нет
            backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            
            # Генерируем имя файла бэкапа
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            backup_size = 0
            
            if 'sqlite' in db_engine.lower():
                # SQLite - создаем полный бэкап всех данных
                db_path = db_config['NAME']
                from pathlib import Path as PathLib
                if isinstance(db_path, PathLib):
                    db_path = str(db_path)
                elif not isinstance(db_path, str):
                    db_path = str(db_path)
                
                if not os.path.exists(db_path):
                    messages.error(request, 'База данных не найдена')
                    return redirect('admin_backups_list')
                
                # Используем VACUUM INTO для создания полного бэкапа
                # Это гарантирует, что все данные из WAL файла будут включены в бэкап
                import sqlite3
                import tempfile
                
                # Имена таблиц в БД соответствуют db_table в моделях (без префикса main_)
                def _safe_table_sql(t):
                    return f'"{t}"' if t == 'order' else t

                # Проверяем количество записей в ключевых таблицах ДО создания бэкапа
                original_stats = {}
                try:
                    conn_check = sqlite3.connect(db_path)
                    cursor_check = conn_check.cursor()
                    for table, name in tables_to_check:
                        try:
                            cursor_check.execute(f"SELECT COUNT(*) FROM {_safe_table_sql(table)}")
                            count = cursor_check.fetchone()[0]
                            original_stats[table] = count
                        except Exception:
                            original_stats[table] = 0
                    conn_check.close()
                except Exception:
                    pass
                
                # Создаем временный файл для VACUUM INTO
                temp_backup = os.path.join(backup_dir, f'temp_backup_{timestamp}.sqlite3')
                
                try:
                    # Подключаемся к БД и выполняем VACUUM INTO
                    # Это создаст полный бэкап со всеми данными, включая данные из WAL
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    # Выполняем VACUUM INTO для создания полного бэкапа
                    # Это гарантирует включение всех данных, включая логи (ActivityLog),
                    # избранное (Favorite), корзины (Cart), заказы (Order), чеки (Receipt) и все остальное
                    cursor.execute(f"VACUUM INTO '{temp_backup}'")
                    conn.commit()
                    conn.close()
                    
                    # Переименовываем временный файл в финальный
                    backup_filename = f'db_backup_{timestamp}.sqlite3'
                    backup_path = os.path.join(backup_dir, backup_filename)
                    shutil.move(temp_backup, backup_path)
                    
                except Exception as e:
                    # Если VACUUM INTO не сработал, используем стандартное копирование
                    # но сначала выполняем CHECKPOINT для слияния WAL
                    try:
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()
                        # Выполняем CHECKPOINT для слияния WAL файла в основной файл
                        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                        conn.commit()
                        conn.close()
                    except:
                        pass
                    
                    # Копируем файл базы данных
                    backup_filename = f'db_backup_{timestamp}.sqlite3'
                    backup_path = os.path.join(backup_dir, backup_filename)
                    shutil.copy2(db_path, backup_path)
                
                # Проверяем, что файл скопирован корректно
                if not os.path.exists(backup_path):
                    messages.error(request, 'Ошибка: файл бэкапа не был создан')
                    return redirect('admin_backups_list')
                
                # Проверяем размер файла
                backup_size = os.path.getsize(backup_path)
                original_size = os.path.getsize(db_path)
                
                if backup_size == 0:
                    messages.error(request, 'Ошибка: файл бэкапа пустой')
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    return redirect('admin_backups_list')
                
                # Проверяем, что бэкап содержит данные
                # Для SQLite минимальный размер файла обычно больше 0
                if backup_size < 1024:  # Минимум 1KB для валидной SQLite БД
                    messages.error(request, f'Ошибка: файл бэкапа слишком мал (размер: {backup_size} байт)')
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    return redirect('admin_backups_list')
                
                # Проверяем целостность бэкапа и наличие всех таблиц
                backup_stats = {}  # Инициализируем переменную для статистики бэкапа
                try:
                    conn = sqlite3.connect(backup_path)
                    cursor = conn.cursor()
                    
                    # Проверяем целостность
                    cursor.execute("PRAGMA integrity_check")
                    result = cursor.fetchone()
                    
                    if result and result[0] != 'ok':
                        conn.close()
                        messages.error(request, f'Ошибка: бэкап поврежден: {result[0]}')
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        return redirect('admin_backups_list')
                    
                    # Все таблицы БД MPTCOURSE (имена как в db_table)
                    critical_tables = [
                        'auth_user', 'role', 'userprofile', 'useraddress', 'usersettings',
                        'course_category', 'course', 'course_image', 'course_content_page',
                        'lesson', 'lesson_page', 'course_purchase', 'lesson_completion',
                        'user_notification', 'course_refund_request', 'course_content_view',
                        'course_survey', 'course_review', 'course_favorite',
                        'cart', 'cartitem', 'order', 'orderitem', 'payment',
                        'receipt', 'receiptitem', 'promotion', 'promo_usage',
                        'savedpaymentmethod', 'cardtransaction', 'balancetransaction',
                        'supportticket', 'activitylog', 'receiptconfig',
                        'organizationaccount', 'organizationtransaction',
                        'django_content_type', 'django_migrations', 'django_session',
                    ]
                    missing_tables = []
                    for table in critical_tables:
                        cursor.execute("""
                            SELECT name FROM sqlite_master 
                            WHERE type='table' AND name=?
                        """, (table,))
                        if not cursor.fetchone():
                            missing_tables.append(table)
                    
                    # Количество записей в ключевых таблицах в бэкапе
                    backup_stats = {}
                    for table, name in tables_to_check:
                        try:
                            cursor.execute(f"SELECT COUNT(*) FROM {_safe_table_sql(table)}")
                            count = cursor.fetchone()[0]
                            backup_stats[table] = count
                        except Exception:
                            backup_stats[table] = 0
                    
                    conn.close()
                    
                    # Сравниваем статистику до и после
                    if original_stats:
                        mismatches = []
                        for table, name in tables_to_check:
                            original_count = original_stats.get(table, 0)
                            backup_count = backup_stats.get(table, 0)
                            if original_count != backup_count:
                                mismatches.append(f"{name}: было {original_count}, в бэкапе {backup_count}")
                        
                        if mismatches:
                            messages.error(request, f'ОШИБКА: Данные не совпадают! {"; ".join(mismatches)}. Бэкап может быть неполным.')
                            if os.path.exists(backup_path):
                                os.remove(backup_path)
                            return redirect('admin_backups_list')
                    
                    if missing_tables:
                        messages.warning(request, f'Предупреждение: в бэкапе отсутствуют некоторые таблицы: {", ".join(missing_tables)}. Бэкап может быть неполным.')
                        # Не удаляем бэкап, так как это может быть нормально для новой БД
                    
                except Exception as e:
                    messages.warning(request, f'Не удалось проверить целостность бэкапа: {str(e)}')
                    # Продолжаем, так как это не критично
                    
            elif 'postgresql' in db_engine.lower() or 'postgres' in db_engine.lower():
                # PostgreSQL - создаем полный SQL дамп через pg_dump
                # Это сохраняет ВСЕ данные: таблицы, индексы, последовательности, функции, триггеры, ограничения
                # Включая: избранное (Favorite), корзины (Cart), заказы (Order), логи (ActivityLog) и все остальное
                import subprocess
                db_name = db_config['NAME']
                db_user = db_config.get('USER', 'postgres')
                db_password = db_config.get('PASSWORD', '')
                db_host = db_config.get('HOST', 'localhost')
                db_port = db_config.get('PORT', '5432')
                
                backup_filename = f'db_backup_{timestamp}.sql'
                backup_path = os.path.join(backup_dir, backup_filename)
                
                # Формируем команду pg_dump с флагами для полного бэкапа
                # --verbose: подробный вывод (для отладки)
                # --no-owner: не включать команды OWNER (для совместимости между разными пользователями)
                # --no-acl: не включать команды ACL (для совместимости)
                # --clean: включить команды DROP перед CREATE (для чистого восстановления)
                # --if-exists: использовать IF EXISTS в командах DROP (безопаснее)
                # --encoding=UTF8: явно указываем кодировку
                cmd = ['pg_dump', '--verbose', '--no-owner', '--no-acl', '--clean', '--if-exists', '--encoding=UTF8']
                if db_host:
                    cmd.extend(['-h', db_host])
                if db_port:
                    cmd.extend(['-p', str(db_port)])
                if db_user:
                    cmd.extend(['-U', db_user])
                cmd.extend(['-d', db_name])
                
                # Устанавливаем переменную окружения для пароля
                env = os.environ.copy()
                if db_password:
                    env['PGPASSWORD'] = db_password
                
                # Устанавливаем кодировку UTF-8
                env['PYTHONIOENCODING'] = 'utf-8'
                if 'LANG' not in env:
                    env['LANG'] = 'en_US.UTF-8'
                env['PGCLIENTENCODING'] = 'UTF8'
                
                # Создаем полный дамп всех данных в файл
                try:
                    with open(backup_path, 'w', encoding='utf-8') as f:
                        result = subprocess.run(
                            cmd,
                            stdout=f,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding='utf-8',
                            errors='replace',
                            env=env,
                            timeout=600  # 10 минут таймаут для больших БД
                        )
                    
                    if result.returncode != 0:
                        error_msg = (result.stderr or 'Неизвестная ошибка').strip()
                        messages.error(request, f'Ошибка при создании бэкапа PostgreSQL: {error_msg}')
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        return redirect('admin_backups_list')
                    
                    # Проверяем размер файла
                    backup_size = os.path.getsize(backup_path)
                    if backup_size == 0:
                        messages.error(request, 'Ошибка: файл бэкапа пустой')
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        return redirect('admin_backups_list')
                    
                    # Проверяем, что в дампе есть данные (минимальный размер для валидного дампа)
                    if backup_size < 1024:  # Минимум 1KB
                        messages.error(request, f'Ошибка: файл бэкапа слишком мал (размер: {backup_size} байт). Возможно, база данных пуста или произошла ошибка.')
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        return redirect('admin_backups_list')
                        
                except subprocess.TimeoutExpired:
                    messages.error(request, 'Таймаут при создании бэкапа (превышено 10 минут). База данных слишком большая или произошла ошибка.')
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    return redirect('admin_backups_list')
                except FileNotFoundError:
                    messages.error(request, 'pg_dump не найден. Установите PostgreSQL client tools. В Docker это должно быть установлено автоматически.')
                    return redirect('admin_backups_list')
                except Exception as e:
                    messages.error(request, f'Ошибка при создании бэкапа PostgreSQL: {str(e)}')
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    return redirect('admin_backups_list')
            else:
                messages.error(request, f'Неподдерживаемый тип базы данных: {db_engine}')
                return redirect('admin_backups_list')
            
            # Формируем описание бэкапа (для записи в БД)
            notes_text = (
                'Полный бэкап БД MPTCOURSE: пользователи, профили, роли, курсы, уроки, '
                'покупки курсов, корзины, заказы, платежи, чеки, промокоды, балансы, '
                'транзакции, поддержка, логи активности, настройки, возвраты, уведомления и все остальные данные.'
            )
            try:
                if 'backup_stats' in locals() and backup_stats:
                    stats_list = [f"{name}: {backup_stats.get(table, 0)}" for table, name in tables_to_check]
                    stats_text = ', '.join(stats_list)
                    notes_text = (
                        f'Полный бэкап всех данных MPTCOURSE. Статистика: {stats_text}. '
                        'Включает: курсы, уроки, покупки, корзины, заказы, чеки, платежи, '
                        'балансы, логи, настройки, поддержку, избранное и все таблицы БД.'
                    )
            except Exception:
                pass
            
            # Создаем запись в базе данных
            backup_name = request.POST.get('backup_name', '').strip() or f'Полный бэкап от {datetime.now().strftime("%d.%m.%Y %H:%M")}'
            schedule = request.POST.get('schedule', 'now')
            notes = request.POST.get('notes', '').strip() or notes_text
            
            # Если выбрано "Прямо сейчас", создаем бэкап немедленно
            # Если выбрано расписание, сохраняем настройку для автоматических бэкапов
            is_automatic = schedule != 'now'
            
            backup = DatabaseBackup.objects.create(
                backup_name=backup_name,
                created_by=request.user,
                file_size=backup_size,
                schedule=schedule,
                notes=notes,
                is_automatic=is_automatic
            )
            
            # Сохраняем путь к файлу
            backup.backup_file.name = f'backups/{backup_filename}'
            backup.save()
            
            _log_activity(request.user, 'create', f'backup_{backup.id}', f'Создан бэкап базы данных: {backup_name}', request)
            messages.success(request, f'Бэкап "{backup_name}" успешно создан')
            return redirect('admin_backups_list')
        except Exception as e:
            messages.error(request, f'Ошибка при создании бэкапа: {str(e)}')
            return redirect('admin_backups_list')
    
    return render(request, 'main/admin/backup_create.html')

@login_required
def admin_backup_download(request, backup_id):
    """Скачивание бэкапа"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    backup = get_object_or_404(DatabaseBackup, pk=backup_id)
    
    if not backup.backup_file:
        messages.error(request, 'Файл бэкапа не найден')
        return redirect('admin_backups_list')
    
    _log_activity(request.user, 'download', f'backup_{backup_id}', f'Скачан бэкап: {backup.backup_name}', request)
    
    from django.http import FileResponse
    import os
    from django.conf import settings
    
    file_path = os.path.join(settings.MEDIA_ROOT, backup.backup_file.name)
    if not os.path.exists(file_path):
        messages.error(request, 'Файл бэкапа не найден на сервере')
        return redirect('admin_backups_list')
    
    response = FileResponse(open(file_path, 'rb'), content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{backup.backup_name.replace(" ", "_")}.sqlite3"'
    return response

@login_required
def admin_backup_delete(request, backup_id):
    """Удаление бэкапа"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    backup = get_object_or_404(DatabaseBackup, pk=backup_id)
    
    if request.method == 'POST':
        try:
            backup_name = backup.backup_name
            # Удаляем файл, если он существует
            if backup.backup_file:
                from django.conf import settings
                file_path = os.path.join(settings.MEDIA_ROOT, backup.backup_file.name)
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            backup.delete()
            _log_activity(request.user, 'delete', f'backup_{backup_id}', f'Удален бэкап: {backup_name}', request)
            messages.success(request, f'Бэкап "{backup_name}" удален')
            return redirect('admin_backups_list')
        except Exception as e:
            messages.error(request, f'Ошибка при удалении бэкапа: {str(e)}')
    
    return render(request, 'main/admin/backup_delete.html', {'backup': backup})

@login_required
def admin_backup_restore(request, backup_id):
    """Восстановление базы данных из бэкапа"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    backup = get_object_or_404(DatabaseBackup, pk=backup_id)
    
    if request.method == 'POST':
        try:
            from django.conf import settings
            import shutil
            
            # Проверяем наличие файла бэкапа
            if not backup.backup_file:
                messages.error(request, 'Файл бэкапа не найден')
                return redirect('admin_backups_list')
            
            backup_path = os.path.join(settings.MEDIA_ROOT, backup.backup_file.name)
            if not os.path.exists(backup_path):
                messages.error(request, 'Файл бэкапа не найден на сервере')
                return redirect('admin_backups_list')
            
            # Получаем настройки базы данных
            db_config = settings.DATABASES['default']
            db_engine = db_config.get('ENGINE', '')
            db_name = db_config['NAME']
            
            # Закрываем все соединения с БД перед восстановлением
            # Это критически важно для корректного восстановления
            from django.db import connections
            for conn in connections.all():
                try:
                    conn.close()
                except:
                    pass
            
            # Определяем тип базы данных и восстанавливаем соответствующим образом
            if 'sqlite' in db_engine.lower():
                # SQLite - копируем файл
                db_path = db_name
                # Преобразуем Path объект в строку, если необходимо
                from pathlib import Path as PathLib
                if isinstance(db_path, PathLib):
                    db_path = str(db_path)
                elif not isinstance(db_path, str):
                    db_path = str(db_path)
                
                # Если путь относительный, делаем его абсолютным
                if not os.path.isabs(db_path):
                    base_dir = getattr(settings, 'BASE_DIR', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    db_path = os.path.join(base_dir, db_path)
                
                # Создаем резервную копию текущей БД перед восстановлением
                if os.path.exists(db_path):
                    backup_current_path = f"{db_path}.before_restore_{int(timezone.now().timestamp())}"
                    try:
                        shutil.copy2(db_path, backup_current_path)
                    except:
                        pass
                
                # Проверяем, что файл бэкапа существует и не пустой
                if not os.path.exists(backup_path):
                    messages.error(request, 'Файл бэкапа не найден на сервере')
                    return redirect('admin_backups_list')
                
                backup_size = os.path.getsize(backup_path)
                if backup_size == 0:
                    messages.error(request, 'Ошибка: файл бэкапа пустой')
                    return redirect('admin_backups_list')
                
                # Восстанавливаем БД из бэкапа
                shutil.copy2(backup_path, db_path)
                
                # Проверяем, что восстановление прошло успешно
                if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
                    messages.error(request, 'Ошибка: база данных не была восстановлена корректно')
                    return redirect('admin_backups_list')
                
                # Проверяем целостность восстановленной БД
                try:
                    import sqlite3
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA integrity_check")
                    result = cursor.fetchone()
                    conn.close()
                    
                    if result and result[0] != 'ok':
                        messages.error(request, f'Ошибка: восстановленная база данных повреждена: {result[0]}')
                        return redirect('admin_backups_list')
                    
                    # Проверяем наличие таблиц
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
                    tables = cursor.fetchall()
                    conn.close()
                    
                    if len(tables) == 0:
                        messages.warning(request, 'Восстановление завершено, но таблицы не найдены. Возможно, база данных пуста.')
                    elif len(tables) < 10:
                        messages.warning(request, f'Восстановление завершено, но найдено только {len(tables)} таблиц. Возможно, не все данные восстановлены.')
                except Exception as e:
                    # Если не удалось проверить, продолжаем
                    messages.warning(request, f'Не удалось проверить целостность восстановленной БД: {str(e)}')
                    
            elif 'postgresql' in db_engine.lower() or 'postgres' in db_engine.lower():
                # PostgreSQL - восстанавливаем через psql
                import subprocess
                db_user = db_config.get('USER', 'postgres')
                db_password = db_config.get('PASSWORD', '')
                db_host = db_config.get('HOST', 'localhost')
                db_port = db_config.get('PORT', '5432')
                
                # Проверяем, что файл бэкапа существует и не пустой
                if not os.path.exists(backup_path):
                    messages.error(request, 'Файл бэкапа не найден на сервере')
                    return redirect('admin_backups_list')
                
                backup_size = os.path.getsize(backup_path)
                if backup_size == 0:
                    messages.error(request, 'Ошибка: файл бэкапа пустой')
                    return redirect('admin_backups_list')
                
                # Устанавливаем пароль через переменную окружения
                env = os.environ.copy()
                if db_password:
                    env['PGPASSWORD'] = db_password
                
                # Устанавливаем кодировку UTF-8
                env['PYTHONIOENCODING'] = 'utf-8'
                if 'LANG' not in env:
                    env['LANG'] = 'en_US.UTF-8'
                env['PGCLIENTENCODING'] = 'UTF8'
                
                try:
                    # Отключаем все активные соединения к целевой БД перед восстановлением
                    # Это необходимо для корректного восстановления в Docker
                    terminate_cmd = [
                        'psql',
                        '-h', db_host,
                        '-p', str(db_port),
                        '-U', db_user,
                        '-d', 'postgres',
                        '-c', f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();"
                    ]
                    subprocess.run(terminate_cmd, env=env, capture_output=True, encoding='utf-8', errors='replace', timeout=30)
                    
                    # Сначала удаляем существующую БД (если есть)
                    # Используем --if-exists для безопасности
                    drop_cmd = [
                        'psql',
                        '-h', db_host,
                        '-p', str(db_port),
                        '-U', db_user,
                        '-d', 'postgres',
                        '-c', f'DROP DATABASE IF EXISTS "{db_name}";'
                    ]
                    drop_result = subprocess.run(drop_cmd, env=env, capture_output=True, encoding='utf-8', errors='replace', timeout=60)
                    
                    if drop_result.returncode != 0:
                        # Если не удалось удалить, продолжаем (возможно, БД не существует)
                        pass
                    
                    # Создаем новую БД
                    create_cmd = [
                        'psql',
                        '-h', db_host,
                        '-p', str(db_port),
                        '-U', db_user,
                        '-d', 'postgres',
                        '-c', f'CREATE DATABASE "{db_name}";'
                    ]
                    result = subprocess.run(create_cmd, env=env, capture_output=True, encoding='utf-8', errors='replace', timeout=60)
                    
                    if result.returncode != 0:
                        error_msg = (result.stderr or result.stdout or 'Неизвестная ошибка').strip()
                        # Проверяем, не потому ли ошибка, что БД уже существует
                        if 'already exists' not in error_msg.lower():
                            messages.error(request, f'Ошибка при создании БД: {error_msg}')
                            return redirect('admin_backups_list')
                    
                    # Восстанавливаем данные из бэкапа
                    # Используем ON_ERROR_STOP=off для продолжения при некритичных ошибках
                    # Но все равно проверяем результат
                    restore_cmd = [
                        'psql',
                        '-h', db_host,
                        '-p', str(db_port),
                        '-U', db_user,
                        '-d', db_name,
                        '-f', backup_path,
                        '-v', 'ON_ERROR_STOP=off'  # Продолжаем при некритичных ошибках
                    ]
                    result = subprocess.run(restore_cmd, env=env, capture_output=True, encoding='utf-8', errors='replace', timeout=600)
                    
                    # Проверяем результат восстановления
                    # Некоторые предупреждения допустимы (например, "does not exist" при DROP)
                    if result.returncode != 0:
                        error_output = result.stderr or result.stdout or ''
                        # Игнорируем некритичные ошибки
                        critical_errors = [line for line in error_output.split('\n') 
                                         if line.strip() and 
                                         'ERROR' in line.upper() and 
                                         'does not exist' not in line.lower() and
                                         'already exists' not in line.lower()]
                        
                        if critical_errors:
                            error_msg = '\n'.join(critical_errors[:5])  # Показываем первые 5 ошибок
                            messages.error(request, f'Ошибка при восстановлении БД: {error_msg}')
                            return redirect('admin_backups_list')
                    
                    # Проверяем, что восстановление прошло успешно
                    # Проверяем наличие хотя бы одной таблицы
                    check_cmd = [
                        'psql',
                        '-h', db_host,
                        '-p', str(db_port),
                        '-U', db_user,
                        '-d', db_name,
                        '-c', "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
                    ]
                    check_result = subprocess.run(check_cmd, env=env, capture_output=True, encoding='utf-8', errors='replace', timeout=30)
                    
                    # Проверяем результат проверки таблиц
                    table_count = 0
                    if check_result.returncode == 0 and check_result.stdout:
                        try:
                            # Извлекаем число из вывода psql
                            for line in check_result.stdout.split('\n'):
                                line = line.strip()
                                if line.isdigit():
                                    table_count = int(line)
                                    break
                        except:
                            pass
                    
                    if table_count == 0:
                        messages.warning(request, 'Восстановление завершено, но таблицы не найдены. Возможно, база данных пуста или произошла ошибка.')
                    elif table_count < 10:  # Минимум 10 таблиц для нормальной работы Django
                        messages.warning(request, f'Восстановление завершено, но найдено только {table_count} таблиц. Возможно, не все данные восстановлены.')
                        
                except subprocess.TimeoutExpired:
                    messages.error(request, 'Таймаут при восстановлении базы данных (превышено 10 минут)')
                    return redirect('admin_backups_list')
                except FileNotFoundError:
                    messages.error(request, 'psql не найден. Установите PostgreSQL client tools. В Docker это должно быть установлено автоматически.')
                    return redirect('admin_backups_list')
                except Exception as e:
                    messages.error(request, f'Ошибка при восстановлении PostgreSQL БД: {str(e)}')
                    return redirect('admin_backups_list')
            else:
                messages.error(request, f'Неподдерживаемый тип базы данных для восстановления: {db_engine}')
                return redirect('admin_backups_list')
            
            # Переподключаемся к БД после восстановления
            # Это необходимо, чтобы Django увидел новую БД
            from django.db import connections
            try:
                # Закрываем все соединения
                for conn in connections.all():
                    try:
                        conn.close()
                    except:
                        pass
                # Переподключаемся
                connection = connections['default']
                connection.ensure_connection()
            except Exception as e:
                # Если не удалось переподключиться, продолжаем
                # Пользователь перезапустит сервер вручную
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f'Не удалось переподключиться к БД после восстановления: {str(e)}')
            
            # Инициализируем обязательные записи после восстановления
            # Это создаст необходимые системные записи, если их нет
            try:
                from .utils import initialize_required_records
                initialize_required_records()
            except Exception as e:
                # Если не удалось инициализировать, это не критично
                # Записи будут созданы при следующем обращении
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f'Не удалось инициализировать обязательные записи после восстановления: {str(e)}')
            
            # Логируем активность (защита от ошибок, если БД еще не готова)
            try:
                _log_activity(request.user, 'restore', f'backup_{backup_id}', f'Восстановлена БД из бэкапа: {backup.backup_name}', request)
            except Exception:
                # Если не удалось залогировать, это не критично
                pass
            
            messages.success(request, f'База данных успешно восстановлена из бэкапа "{backup.backup_name}". Рекомендуется перезапустить сервер для применения изменений.')
            return redirect('admin_backups_list')
        except Exception as e:
            messages.error(request, f'Ошибка при восстановлении БД: {str(e)}')
            return redirect('admin_backups_list')
    
    return render(request, 'main/admin/backup_restore.html', {'backup': backup})

@login_required
def admin_db_delete(request):
    """Очистка всех таблиц базы данных (для тестирования восстановления)"""
    if not _user_is_admin(request.user):
        return redirect('profile')
    
    if request.method == 'POST':
        try:
            from django.conf import settings
            from django.db import connection, connections
            
            # Получаем настройки базы данных
            db_config = settings.DATABASES['default']
            db_engine = db_config.get('ENGINE', '')
            
            # Закрываем все соединения с БД
            for conn in connections.all():
                conn.close()
            
            cleared = False
            
            # Определяем тип базы данных и очищаем таблицы
            if 'sqlite' in db_engine.lower():
                # SQLite - очищаем все таблицы
                try:
                    with connection.cursor() as cursor:
                        # Получаем список всех таблиц
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
                        tables = [row[0] for row in cursor.fetchall()]
                        
                        # Отключаем проверку внешних ключей для быстрой очистки
                        cursor.execute("PRAGMA foreign_keys = OFF;")
                        
                        # Очищаем каждую таблицу
                        for table in tables:
                            cursor.execute(f"DELETE FROM {table};")
                        
                        # Включаем обратно проверку внешних ключей
                        cursor.execute("PRAGMA foreign_keys = ON;")
                        
                        # Сбрасываем автоинкременты
                        for table in tables:
                            try:
                                cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}';")
                            except:
                                pass
                        
                        cleared = True
                except Exception as e:
                    messages.error(request, f'Ошибка при очистке SQLite БД: {str(e)}')
                    return redirect('admin_backups_list')
                    
            elif 'postgresql' in db_engine.lower() or 'postgres' in db_engine.lower():
                # PostgreSQL - очищаем все таблицы
                try:
                    with connection.cursor() as cursor:
                        # Получаем список всех таблиц
                        cursor.execute("""
                            SELECT tablename FROM pg_tables 
                            WHERE schemaname = 'public' 
                            ORDER BY tablename;
                        """)
                        tables = [row[0] for row in cursor.fetchall()]
                        
                        if tables:
                            # Отключаем проверку внешних ключей для быстрой очистки
                            cursor.execute("SET session_replication_role = replica;")
                            
                            # Очищаем каждую таблицу
                            for table in tables:
                                try:
                                    cursor.execute(f"TRUNCATE TABLE {table} CASCADE;")
                                except Exception as e:
                                    # Если TRUNCATE не работает, используем DELETE
                                    try:
                                        cursor.execute(f"DELETE FROM {table};")
                                    except:
                                        pass
                            
                            # Включаем обратно проверку внешних ключей
                            cursor.execute("SET session_replication_role = DEFAULT;")
                            
                            cleared = True
                        else:
                            messages.warning(request, 'Таблицы не найдены в базе данных')
                            return redirect('admin_backups_list')
                            
                except Exception as e:
                    messages.error(request, f'Ошибка при очистке PostgreSQL БД: {str(e)}')
                    return redirect('admin_backups_list')
            else:
                messages.error(request, f'Неподдерживаемый тип базы данных: {db_engine}')
                return redirect('admin_backups_list')
            
            if cleared:
                _log_activity(request.user, 'delete', 'database', 'Все таблицы базы данных очищены (тестовая операция)', request)
                messages.warning(request, '⚠️ Все таблицы базы данных очищены! Сайт будет показывать ошибку 500. Используйте восстановление из бэкапа через страницу ошибки 500, чтобы вернуть сайт в рабочее состояние.')
            
            return redirect('admin_backups_list')
        except Exception as e:
            messages.error(request, f'Ошибка при очистке БД: {str(e)}')
            return redirect('admin_backups_list')
    
    return render(request, 'main/admin/db_delete.html')
