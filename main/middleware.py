from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib.auth import logout
from django.contrib import messages
from django.http import HttpResponse
import traceback
import sys

class DatabaseEmptyCheckMiddleware:
    """Middleware для проверки, что база данных не пуста. Показывает страницу восстановления, если БД пуста."""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # В режиме разработки не блокируем сайт при пустой БД
        try:
            from django.conf import settings
            if getattr(settings, 'DEBUG', False):
                return self.get_response(request)
        except Exception:
            # Если settings недоступен, продолжаем обычную логику
            pass
        # Исключаем статические файлы, медиа, API и страницы восстановления из проверки
        # ВАЖНО: страницы восстановления должны быть доступны даже при пустой БД
        excluded_paths = [
            '/static/', '/media/', '/api/', '/swagger/', '/redoc/',
            '/admin-secret-check/', '/emergency-restore/', '/favicon.ico'
        ]
        
        # Исключаем все запросы к страницам восстановления (GET и POST)
        if any(request.path.startswith(path) for path in excluded_paths):
            return self.get_response(request)
        
        # Проверяем, есть ли данные в БД
        try:
            from django.contrib.auth.models import User
            from django.db import connection
            
            # Проверяем доступность БД
            try:
                connection.ensure_connection()
            except Exception:
                # БД недоступна - показываем страницу 500.html (handler500)
                try:
                    from main.views import handler500
                    return handler500(request)
                except Exception:
                    # Если handler500 не работает, показываем простую страницу 500
                    try:
                        return render(request, '500.html', status=500)
                    except Exception:
                        return HttpResponse(
                            '<html><body><h1>Ошибка 500</h1><p>База данных недоступна.</p><p><a href="/">Вернуться на главную</a></p><p><a href="/admin-secret-check/">Если вы администратор</a></p></body></html>',
                            content_type='text/html',
                            status=500
                        )
            
            # Проверяем, существует ли таблица User (на случай, если миграции еще не выполнены)
            try:
                from django.db import connection
                from django.conf import settings
                db_engine = settings.DATABASES['default'].get('ENGINE', '')
                
                with connection.cursor() as cursor:
                    table_exists = False
                    if 'sqlite' in db_engine.lower():
                        # Для SQLite
                        cursor.execute("""
                            SELECT name FROM sqlite_master 
                            WHERE type='table' AND name='auth_user'
                        """)
                        table_exists = cursor.fetchone() is not None
                    elif 'postgresql' in db_engine.lower() or 'postgres' in db_engine.lower():
                        # Для PostgreSQL
                        cursor.execute("""
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables 
                                WHERE table_schema = 'public' 
                                AND table_name = 'auth_user'
                            )
                        """)
                        table_exists = cursor.fetchone()[0]
                    else:
                        # Для других БД просто пытаемся выполнить запрос
                        # Если таблица не существует, будет исключение
                        try:
                            User.objects.count()
                            table_exists = True
                        except Exception:
                            table_exists = False
                
                if not table_exists:
                    # Таблицы еще не созданы - это нормально при первой установке
                    # Пропускаем проверку
                    return self.get_response(request)
            except Exception:
                # Если произошла ошибка, пропускаем проверку таблицы
                # и пытаемся проверить количество пользователей напрямую
                pass
            
            # Проверяем, есть ли хотя бы один пользователь в БД
            # Если БД пуста (нет пользователей), показываем страницу 500.html
            try:
                user_count = User.objects.count()
                if user_count == 0:
                    # БД пуста - показываем страницу 500.html (handler500)
                    try:
                        from main.views import handler500
                        return handler500(request)
                    except Exception:
                        # Если handler500 не работает, показываем простую страницу 500
                        try:
                            return render(request, '500.html', status=500)
                        except Exception:
                            return HttpResponse(
                                '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ошибка 500 - MPTCOURSE</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f5f5f5; }
        .container { background: white; padding: 40px; border-radius: 8px; max-width: 600px; margin: 0 auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #dc3545; margin-bottom: 20px; }
        p { color: #666; margin-bottom: 30px; line-height: 1.6; }
        a { display: inline-block; padding: 12px 24px; background: #000; color: white; text-decoration: none; border-radius: 6px; margin: 5px; }
        a:hover { background: #333; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚠️ Ошибка 500</h1>
        <p>Произошла внутренняя ошибка сервера. База данных пуста или недоступна.</p>
        <p><a href="/">Вернуться на главную</a></p>
        <p><a href="/admin-secret-check/">Если вы администратор</a></p>
    </div>
</body>
</html>''',
                                content_type='text/html',
                                status=500
                            )
            except Exception as db_error:
                # Если произошла ошибка при проверке количества пользователей,
                # возможно БД повреждена или недоступна - показываем страницу 500.html
                try:
                    from main.views import handler500
                    return handler500(request)
                except Exception:
                    # Если handler500 не работает, показываем простую страницу 500
                    try:
                        return render(request, '500.html', status=500)
                    except Exception:
                        return HttpResponse(
                            '<html><body><h1>Ошибка 500</h1><p>Не удалось проверить состояние базы данных.</p><p><a href="/">Вернуться на главную</a></p><p><a href="/admin-secret-check/">Если вы администратор</a></p></body></html>',
                            content_type='text/html',
                            status=500
                        )
        except Exception as e:
            # Если произошла ошибка при проверке, логируем и продолжаем
            # (не блокируем работу сайта из-за ошибки проверки)
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f'Ошибка при проверке БД на пустоту: {str(e)}')
        
        return self.get_response(request)


class AdminAccessMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Исключаем статические файлы, медиа, API и страницы восстановления из проверки
        if (request.path.startswith('/static/') or 
            request.path.startswith('/media/') or
            request.path.startswith('/api/') or
            request.path.startswith('/swagger/') or
            request.path.startswith('/redoc/') or
            request.path.startswith('/admin-secret-check/') or
            request.path.startswith('/emergency-restore/')):
            return self.get_response(request)
        
        # Проверяем доступ к админке только для HTML страниц
        if request.path.startswith('/admin/'):
            # Разрешаем доступ к статическим файлам админки и JavaScript интернационализации
            if (request.path.startswith('/admin/static/') or 
                request.path.startswith('/admin/jsi18n/') or
                request.path.endswith('.css') or
                request.path.endswith('.js') or
                request.path.endswith('.png') or
                request.path.endswith('.jpg') or
                request.path.endswith('.gif') or
                request.path.endswith('.svg') or
                request.path.endswith('.ico')):
                return self.get_response(request)
            # Разрешаем доступ, только если сессия содержит admin_access_granted
            if not request.session.get('admin_access_granted', False):
                return redirect(reverse('custom_admin_login'))
        return self.get_response(request)


class BlockedUserMiddleware:
    """Middleware для проверки статуса пользователя и блокировки доступа заблокированным пользователям"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Исключаем статические файлы, медиа, API, страницы входа/регистрации и восстановления
        excluded_paths = [
            '/static/', '/media/', '/api/', '/swagger/', '/redoc/',
            '/login/', '/register/', '/logout/',
            '/admin-secret-check/', '/emergency-restore/'
        ]
        
        if any(request.path.startswith(path) for path in excluded_paths):
            return self.get_response(request)
        
        # Проверяем только аутентифицированных пользователей
        # Если БД недоступна, пропускаем проверку профиля
        try:
            if request.user.is_authenticated:
                # Проверка is_active (стандартное поле Django)
                if not request.user.is_active:
                    logout(request)
                    messages.error(request, 'Ваш аккаунт заблокирован. Обратитесь в поддержку: https://t.me/toshaplenka')
                    return redirect('login')
                
                # Проверка статуса в профиле
                try:
                    profile = request.user.profile
                    if profile.user_status == 'blocked':
                        logout(request)
                        messages.error(request, 'Ваш аккаунт заблокирован. Обратитесь в поддержку: https://t.me/toshaplenka')
                        return redirect('login')
                except Exception:
                    # Если профиля нет или БД недоступна, пропускаем проверку
                    pass
        except Exception:
            # Если БД недоступна и не удалось проверить пользователя, пропускаем проверку
            pass
        
        return self.get_response(request)


class CustomErrorHandlerMiddleware:
    """Middleware для обработки ошибок и показа кастомной страницы 500 даже в DEBUG режиме"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        return response
    
    def process_exception(self, request, exception):
        """Обрабатывает исключения и показывает кастомную страницу 500"""
        # Логируем ошибку
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Ошибка 500: {str(exception)}', exc_info=True)
        
        # Показываем кастомную страницу 500
        try:
            from django.db import connection
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
                    from main.views import get_restore_html
                    from django.http import HttpResponse
                    return HttpResponse(get_restore_html(), content_type='text/html', status=500)
                except Exception:
                    # Если даже это не работает, возвращаем простой HTML
                    from django.http import HttpResponse
                    return HttpResponse(
                        '<html><body><h1>Ошибка 500</h1><p>База данных недоступна. <a href="/admin-secret-check/">Восстановить</a></p></body></html>',
                        content_type='text/html',
                        status=500
                    )
            
            # Если БД доступна, показываем обычную страницу ошибки 500
            return render(request, '500.html', status=500)
        except Exception as e:
            # Если даже рендеринг не работает, возвращаем простой HTML
            from django.http import HttpResponse
            return HttpResponse(
                '<html><body><h1>Ошибка 500</h1><p>Произошла внутренняя ошибка сервера.</p><p><a href="/">Вернуться на главную</a></p></body></html>',
                content_type='text/html',
                status=500
            )
