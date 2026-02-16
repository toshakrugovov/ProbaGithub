"""
Management command для создания автоматических полных бэкапов по расписанию.

Создает полные бэкапы всех данных БД MPTCOURSE:
- Пользователи, профили, роли, адреса, настройки
- Курсы, категории, уроки, страницы контента и уроков
- Покупки курсов, прохождения, уведомления, возвраты
- Корзины, заказы, платежи, чеки
- Промокоды, балансы, транзакции, поддержка, логи
- И все остальные таблицы (имена как db_table в моделях)

Запускать через cron или планировщик задач Windows.
"""
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from main.models import DatabaseBackup
from django.contrib.auth.models import User
import shutil
import os
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Создает автоматические бэкапы базы данных по расписанию'

    def add_arguments(self, parser):
        parser.add_argument(
            '--schedule',
            type=str,
            choices=['weekly', 'monthly', 'yearly'],
            help='Тип расписания для создания бэкапа',
        )

    def handle(self, *args, **options):
        schedule = options.get('schedule')
        
        if not schedule:
            self.stdout.write(self.style.ERROR('Не указан тип расписания'))
            return
        
        # Получаем путь к базе данных
        db_path = settings.DATABASES['default']['NAME']
        # Преобразуем Path объект в строку, если необходимо
        from pathlib import Path as PathLib
        if isinstance(db_path, PathLib):
            db_path = str(db_path)
        elif not isinstance(db_path, str):
            db_path = str(db_path)
        
        if not os.path.exists(db_path):
            self.stdout.write(self.style.ERROR(f'База данных не найдена: {db_path}'))
            return
        
        # Проверяем, нужно ли создавать бэкап
        now = timezone.now()
        last_backup = DatabaseBackup.objects.filter(
            schedule=schedule,
            is_automatic=True
        ).order_by('-created_at').first()
        
        should_create = False
        if not last_backup:
            should_create = True
        else:
            if schedule == 'weekly':
                # Проверяем, прошла ли неделя
                if now - last_backup.created_at >= timedelta(days=7):
                    should_create = True
            elif schedule == 'monthly':
                # Проверяем, прошел ли месяц
                if now - last_backup.created_at >= timedelta(days=30):
                    should_create = True
            elif schedule == 'yearly':
                # Проверяем, прошел ли год
                if now - last_backup.created_at >= timedelta(days=365):
                    should_create = True
        
        if not should_create:
            self.stdout.write(self.style.SUCCESS(f'Бэкап по расписанию {schedule} не требуется'))
            return
        
        try:
            # Закрываем все соединения с БД перед копированием (важно для SQLite)
            from django.db import connections
            for conn in connections.all():
                conn.close()
            
            # Создаем директорию для бэкапов, если её нет
            backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            
            # Генерируем имя файла бэкапа
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f'db_backup_{schedule}_{timestamp}.sqlite3'
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # Используем VACUUM INTO для создания полного бэкапа
            # Это гарантирует, что все данные из WAL файла будут включены в бэкап
            # Сохраняет ВСЕ данные: избранное (Favorite), корзины (Cart), заказы (Order), 
            # логи (ActivityLog) и все остальное
            import sqlite3
            
            try:
                # Подключаемся к БД и выполняем VACUUM INTO
                # Это создаст полный бэкап со всеми данными, включая данные из WAL
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Выполняем VACUUM INTO для создания полного бэкапа
                cursor.execute(f"VACUUM INTO '{backup_path}'")
                conn.commit()
                conn.close()
                
                self.stdout.write(self.style.SUCCESS(f'Создан полный бэкап через VACUUM INTO'))
                
            except Exception as e:
                # Если VACUUM INTO не сработал, используем стандартное копирование
                # но сначала выполняем CHECKPOINT для слияния WAL
                self.stdout.write(self.style.WARNING(f'VACUUM INTO не удался: {str(e)}, используем стандартное копирование'))
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
                shutil.copy2(db_path, backup_path)
            
            # Проверяем, что файл скопирован корректно
            if not os.path.exists(backup_path):
                self.stdout.write(self.style.ERROR('Ошибка: файл бэкапа не был создан'))
                return
            
            # Проверяем размер файла
            backup_size = os.path.getsize(backup_path)
            original_size = os.path.getsize(db_path)
            
            if backup_size == 0:
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                self.stdout.write(self.style.ERROR('Ошибка: файл бэкапа пустой'))
                return
            
            # Проверяем, что бэкап содержит данные
            # Для SQLite минимальный размер файла обычно больше 0
            if backup_size < 1024:  # Минимум 1KB для валидной SQLite БД
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                self.stdout.write(self.style.ERROR(f'Ошибка: файл бэкапа слишком мал (размер: {backup_size} байт)'))
                return
            
            # Проверяем целостность бэкапа и наличие всех таблиц
            try:
                conn = sqlite3.connect(backup_path)
                cursor = conn.cursor()
                
                # Проверяем целостность
                cursor.execute("PRAGMA integrity_check")
                result = cursor.fetchone()
                
                if result and result[0] != 'ok':
                    conn.close()
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    self.stdout.write(self.style.ERROR(f'Ошибка: бэкап поврежден: {result[0]}'))
                    return
                
                # Все таблицы БД MPTCOURSE (имена как db_table в моделях)
                critical_tables = [
                    'auth_user', 'role', 'userprofile', 'useraddress', 'usersettings',
                    'course_category', 'course', 'course_image', 'course_content_page',
                    'lesson', 'lesson_page', 'course_purchase', 'lesson_completion',
                    'user_notification', 'course_refund_request', 'course_content_view',
                    'course_survey', 'course_review', 'course_favorite',
                    'cart', 'cartitem', 'order', 'orderitem', 'payment',
                    'receipt', 'receiptitem', 'promotion', 'promo_usage',
                    'savedpaymentmethod', 'cardtransaction', 'balancetransaction', 'supportticket',
                    'activitylog', 'receiptconfig', 'organizationaccount', 'organizationtransaction',
                ]
                missing_tables = []
                for table in critical_tables:
                    cursor.execute("""
                        SELECT name FROM sqlite_master 
                        WHERE type='table' AND name=?
                    """, (table,))
                    if not cursor.fetchone():
                        missing_tables.append(table)
                
                def _safe_table_sql(t):
                    return f'"{t}"' if t == 'order' else t
                tables_to_check = [
                    ('auth_user', 'Пользователи'),
                    ('userprofile', 'Профили'),
                    ('course', 'Курсы'),
                    ('course_purchase', 'Покупки курсов'),
                    ('cart', 'Корзины'),
                    ('order', 'Заказы'),
                    ('receipt', 'Чеки'),
                    ('payment', 'Платежи'),
                    ('activitylog', 'Логи'),
                    ('usersettings', 'Настройки'),
                ]
                stats = {}
                for table, name in tables_to_check:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {_safe_table_sql(table)}")
                        count = cursor.fetchone()[0]
                        stats[name] = count
                    except Exception:
                        stats[name] = 0
                
                conn.close()
                
                if missing_tables:
                    self.stdout.write(self.style.WARNING(f'Предупреждение: в бэкапе отсутствуют некоторые таблицы: {", ".join(missing_tables)}'))
                
                stats_text = ', '.join([f"{name}: {count}" for name, count in stats.items()])
                self.stdout.write(self.style.SUCCESS(f'Статистика бэкапа: {stats_text}'))
                
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'Не удалось проверить целостность бэкапа: {str(e)}'))
                # Продолжаем, так как это не критично
            
            # Получаем размер файла (используем уже проверенный размер)
            file_size = backup_size
            
            # Получаем первого суперпользователя или создаем системного
            admin_user = User.objects.filter(is_superuser=True).first()
            
            # Создаем запись в базе данных
            schedule_names = {
                'weekly': 'Еженедельный',
                'monthly': 'Ежемесячный',
                'yearly': 'Ежегодный'
            }
            backup_name = f'{schedule_names[schedule]} бэкап от {datetime.now().strftime("%d.%m.%Y %H:%M")}'
            
            backup = DatabaseBackup.objects.create(
                backup_name=backup_name,
                created_by=admin_user,
                file_size=file_size,
                schedule=schedule,
                notes=f'Автоматический полный бэкап БД MPTCOURSE (все таблицы и данные). Расписание: {schedule}',
                is_automatic=True
            )
            
            # Сохраняем путь к файлу
            backup.backup_file.name = f'backups/{backup_filename}'
            backup.save()
            
            self.stdout.write(self.style.SUCCESS(f'Бэкап "{backup_name}" успешно создан'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка при создании бэкапа: {str(e)}'))

