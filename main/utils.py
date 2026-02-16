"""
Утилиты для работы с базой данных
"""
import os
import re
import subprocess
from decimal import Decimal

from django.conf import settings
from django.db import connections

from .models import OrganizationAccount, ReceiptConfig

# Базовый набор выражений для маскировки нецензурной лексики.
# Поддерживает кириллические и латинские варианты написания.
_PROFANITY_PATTERNS = [
    r'\b(?:хер|ху[йея][\w-]*|пизд[\w-]*|еб[аоыу][\w-]*|ебн[\w-]*|бл[я@]д[\w-]*|сука[\w-]*|муд[ао][\w-]*|сук[аи][\w-]*)\b',
    r'\b(?:fuck[\w-]*|shit[\w-]*|bitch[\w-]*|asshole[\w-]*|bastard[\w-]*)\b',
]


def filter_profanity(text: str) -> str:
    """
    Маскирует нецензурные слова, сохраняя первую букву и заменяя остальные символы на *.
    """
    if not text:
        return ''

    def _mask(match: re.Match) -> str:
        word = match.group(0)
        if len(word) <= 2:
            return '*' * len(word)
        return word[0] + '*' * (len(word) - 1)

    cleaned = text
    for pattern in _PROFANITY_PATTERNS:
        cleaned = re.sub(pattern, _mask, cleaned, flags=re.IGNORECASE | re.UNICODE)
    return cleaned

def create_sql_dump(output_path, include_data=True):
    """
    Создает SQL дамп базы данных
    
    Args:
        output_path: Путь к файлу для сохранения дампа
        include_data: Включать ли данные в дамп (True) или только схему (False)
    
    Returns:
        bool: True если успешно, False в противном случае
    """
    db_config = settings.DATABASES['default']
    engine = db_config.get('ENGINE', '')
    
    try:
        if 'sqlite' in engine:
            # Для SQLite используем .dump команду
            db_path = db_config['NAME']
            from pathlib import Path
            if isinstance(db_path, (str, Path)) and not os.path.isabs(str(db_path)):
                from django.conf import settings
                base_dir = Path(settings.BASE_DIR) if hasattr(settings, 'BASE_DIR') else Path(__file__).resolve().parent.parent.parent
                db_path = str(base_dir / db_path)
            db_path = str(db_path)
            
            # Закрываем все соединения
            for conn in connections.all():
                conn.close()
            
            # Создаем SQL дамп через sqlite3
            with open(output_path, 'w', encoding='utf-8') as f:
                result = subprocess.run(
                    ['sqlite3', db_path, '.dump'],
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                if result.returncode != 0:
                    return False
                
                # Добавляем инициализацию обязательных записей в конец дампа
                f.write('\n\n-- ============================================\n')
                f.write('-- Инициализация обязательных записей\n')
                f.write('-- ============================================\n\n')
                
                # Инициализация счета организации
                f.write('-- Создание счета организации, если его нет\n')
                f.write('INSERT OR IGNORE INTO main_organizationaccount (id, balance, tax_reserve, created_at, updated_at)\n')
                f.write("VALUES (1, 0.00, 0.00, datetime('now'), datetime('now'));\n\n")
                
                # Инициализация настроек чека
                f.write('-- Создание настроек чека, если их нет\n')
                f.write("INSERT OR IGNORE INTO main_receiptconfig (id, company_name, company_inn, company_address, cashier_name, shift_number, kkt_rn, kkt_sn, fn_number, site_fns)\n")
                f.write("VALUES (1, 'ООО «MPTCOURSE»', '7700000000', 'г. Москва, ул. Примерная, д. 1', 'Кассир', '1', '0000000000000000', '1234567890', '0000000000000000', 'www.nalog.ru');\n\n")
                
                # Инициализация суперюзера
                f.write('-- Создание суперюзера admin@gmail.com с паролем 4856106Anton, если его нет\n')
                f.write("INSERT OR IGNORE INTO auth_user (username, email, password, is_superuser, is_staff, is_active, first_name, last_name, date_joined)\n")
                f.write("VALUES ('admin', 'admin@gmail.com', 'pbkdf2_sha256$1000000$FASiHAM7fJ5s43T8XIC86H$sw2Szw9ZpvtJ18TqqT3/KfjRiOzUPEQ5fSz/KsWd200=', 1, 1, 1, 'Admin', 'User', datetime('now'));\n\n")
                
                # Примечание о таблицах Django
                f.write('-- Примечание: Таблицы Django (django_migrations, django_content_type, django_session,\n')
                f.write('-- auth_user, auth_group, auth_permission, django_admin_log и связанные таблицы)\n')
                f.write('-- уже включены в дамп выше, так как они являются частью базы данных.\n')
            
            return True
            
        elif 'postgresql' in engine:
            # Для PostgreSQL используем pg_dump
            db_name = db_config['NAME']
            db_user = db_config.get('USER', 'postgres')
            db_password = db_config.get('PASSWORD', '')
            db_host = db_config.get('HOST', 'localhost')
            db_port = db_config.get('PORT', '5432')
            
            # Формируем команду pg_dump
            cmd = ['pg_dump']
            if db_host:
                cmd.extend(['-h', db_host])
            if db_port:
                cmd.extend(['-p', str(db_port)])
            if db_user:
                cmd.extend(['-U', db_user])
            if not include_data:
                cmd.append('-s')  # Только схема
            
            cmd.append(db_name)
            
            # Устанавливаем переменную окружения для пароля
            env = os.environ.copy()
            if db_password:
                env['PGPASSWORD'] = db_password
            
            # Создаем дамп
            with open(output_path, 'w', encoding='utf-8') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env
                )
                
                if result.returncode != 0:
                    return False
                
                # Добавляем инициализацию обязательных записей в конец дампа
                f.write('\n\n-- ============================================\n')
                f.write('-- Инициализация обязательных записей\n')
                f.write('-- ============================================\n\n')
                
                # Инициализация счета организации
                f.write('-- Создание счета организации, если его нет\n')
                f.write('INSERT INTO main_organizationaccount (id, balance, tax_reserve, created_at, updated_at)\n')
                f.write("VALUES (1, 0.00, 0.00, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)\n")
                f.write("ON CONFLICT (id) DO NOTHING;\n\n")
                
                # Инициализация настроек чека
                f.write('-- Создание настроек чека, если их нет\n')
                f.write("INSERT INTO main_receiptconfig (id, company_name, company_inn, company_address, cashier_name, shift_number, kkt_rn, kkt_sn, fn_number, site_fns)\n")
                f.write("VALUES (1, 'ООО «MPTCOURSE»', '7700000000', 'г. Москва, ул. Примерная, д. 1', 'Кассир', '1', '0000000000000000', '1234567890', '0000000000000000', 'www.nalog.ru')\n")
                f.write("ON CONFLICT DO NOTHING;\n\n")
                
                # Инициализация суперюзера
                f.write('-- Создание суперюзера admin@gmail.com с паролем 4856106Anton, если его нет\n')
                f.write("INSERT INTO auth_user (username, email, password, is_superuser, is_staff, is_active, first_name, last_name, date_joined)\n")
                f.write("VALUES ('admin', 'admin@gmail.com', 'pbkdf2_sha256$1000000$FASiHAM7fJ5s43T8XIC86H$sw2Szw9ZpvtJ18TqqT3/KfjRiOzUPEQ5fSz/KsWd200=', TRUE, TRUE, TRUE, 'Admin', 'User', CURRENT_TIMESTAMP)\n")
                f.write("ON CONFLICT (username) DO UPDATE SET\n")
                f.write("    email = EXCLUDED.email,\n")
                f.write("    password = EXCLUDED.password,\n")
                f.write("    is_superuser = EXCLUDED.is_superuser,\n")
                f.write("    is_staff = EXCLUDED.is_staff,\n")
                f.write("    is_active = EXCLUDED.is_active;\n\n")
            
            return True
        else:
            return False
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Ошибка при создании SQL дампа: {str(e)}')
        return False


def create_superuser_if_not_exists():
    """
    Создает суперюзера admin@gmail.com с паролем 4856106Anton, если его еще нет
    """
    try:
        from django.contrib.auth.models import User
        from django.db import connection
        
        # Проверяем, что БД доступна
        try:
            connection.ensure_connection()
        except Exception:
            return False
        
        # Проверяем, существует ли уже суперюзер с таким username
        # Сначала проверяем по username (более надежно)
        user = User.objects.filter(username='admin').first()
        
        # Если не нашли по username, ищем по email (но берем первый, если несколько)
        if not user:
            user = User.objects.filter(email='admin@gmail.com').first()
        
        # Если нашли несколько пользователей с таким email, обновляем все, но работаем с первым
        if user and User.objects.filter(email='admin@gmail.com').count() > 1:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f'Найдено несколько пользователей с email admin@gmail.com. Обновляем пользователя {user.id}')
        
        if user:
            # Обновляем существующего пользователя, если нужно
            updated = False
            if not user.is_superuser:
                user.is_superuser = True
                updated = True
            if not user.is_staff:
                user.is_staff = True
                updated = True
            if not user.is_active:
                user.is_active = True
                updated = True
            if user.email != 'admin@gmail.com':
                user.email = 'admin@gmail.com'
                updated = True
            # Всегда обновляем пароль на нужный
            user.set_password('4856106Anton')
            user.save()
            
            # Обновляем профиль пользователя, если он заблокирован
            try:
                from .models import UserProfile
                profile, _ = UserProfile.objects.get_or_create(user=user)
                if profile.user_status == 'blocked':
                    profile.user_status = 'active'
                    profile.save()
                    updated = True
            except Exception:
                pass
            
            import logging
            logger = logging.getLogger(__name__)
            if updated:
                logger.info('Суперюзер admin обновлен')
            return True
        
        # Создаем нового суперюзера
        User.objects.create_superuser(
            username='admin',
            email='admin@gmail.com',
            password='4856106Anton',
            first_name='Admin',
            last_name='User'
        )
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info('Суперюзер admin@gmail.com создан успешно')
        return True
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Ошибка при создании суперюзера: {str(e)}')
        return False


def initialize_required_records():
    """
    Инициализирует обязательные записи в базе данных
    Вызывается после восстановления из бэкапа
    """
    try:
        from django.db import connection
        # Проверяем, что БД доступна
        try:
            connection.ensure_connection()
        except Exception:
            return False
        
        # Создаем счет организации, если его нет
        OrganizationAccount.objects.get_or_create(
            pk=1,
            defaults={
                'balance': Decimal('0.00'),
                'tax_reserve': Decimal('0.00')
            }
        )
        
        # Создаем настройки чека, если их нет
        if not ReceiptConfig.objects.exists():
            ReceiptConfig.objects.create()
        
        # Создаем суперюзера, если его нет
        create_superuser_if_not_exists()
        
        return True
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Ошибка при инициализации обязательных записей: {str(e)}')
        return False


def create_clean_backup(output_path):
    """
    Создает "чистый" бэкап базы данных:
    - Сохраняет структуру всех таблиц
    - Сохраняет системные данные (миграции, content types, суперпользователи, роли, категории, бренды, поставщики, настройки)
    - Удаляет пользовательские данные (заказы, товары, корзины, отзывы и т.д.)
    - Сбрасывает балансы и транзакции
    
    Args:
        output_path: Путь к файлу для сохранения дампа
    
    Returns:
        bool: True если успешно, False в противном случае
    """
    db_config = settings.DATABASES['default']
    engine = db_config.get('ENGINE', '')
    
    try:
        if 'sqlite' in engine:
            # Для SQLite создаем полный дамп, затем удаляем данные из пользовательских таблиц
            db_path = db_config['NAME']
            from pathlib import Path
            if isinstance(db_path, (str, Path)) and not os.path.isabs(str(db_path)):
                from django.conf import settings
                base_dir = Path(settings.BASE_DIR) if hasattr(settings, 'BASE_DIR') else Path(__file__).resolve().parent.parent.parent
                db_path = str(base_dir / db_path)
            db_path = str(db_path)
            
            # Закрываем все соединения
            for conn in connections.all():
                conn.close()
            
            # Создаем SQL дамп через sqlite3
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.sql', encoding='utf-8') as tmp_dump:
                tmp_dump_path = tmp_dump.name
                result = subprocess.run(
                    ['sqlite3', db_path, '.dump'],
                    stdout=tmp_dump,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                if result.returncode != 0:
                    os.unlink(tmp_dump_path)
                    return False
            
            # Читаем дамп и обрабатываем его
            with open(tmp_dump_path, 'r', encoding='utf-8') as f:
                dump_content = f.read()
            
            # Список таблиц, данные из которых нужно удалить (пользовательские данные)
            tables_to_clear = [
                'main_product',
                'main_productimage',
                'main_productsize',
                'main_producttag',
                'main_order',
                'main_orderitem',
                'main_cart',
                'main_cartitem',
                'main_favorite',
                'main_productreview',
                'main_supportticket',
                'main_payment',
                'main_savedpaymentmethod',
                'main_balancetransaction',
                'main_cardtransaction',
                'main_receipt',
                'main_receiptitem',
                'main_activitylog',
                'main_databasebackup',
                'main_useraddress',
                'main_delivery',
                'main_organizationtransaction',
                'main_promotion',  # Промоакции можно очистить
            ]
            
            # Таблицы пользователей - удаляем всех, кроме суперпользователей
            # Обрабатываем auth_user и userprofile отдельно
            
            # Записываем обработанный дамп
            with open(output_path, 'w', encoding='utf-8') as f:
                # Записываем структуру (CREATE TABLE и т.д.)
                lines = dump_content.split('\n')
                in_insert = False
                current_table = None
                
                for line in lines:
                    line_upper = line.upper().strip()
                    
                    # Определяем начало INSERT для таблицы
                    if line_upper.startswith('INSERT INTO'):
                        # Извлекаем имя таблицы
                        parts = line.split("'")
                        if len(parts) >= 2:
                            table_name = parts[1]
                            current_table = table_name
                            
                            # Пропускаем INSERT для таблиц, которые нужно очистить
                            if table_name in tables_to_clear:
                                in_insert = True
                                continue
                            
                            # Для auth_user и userprofile - особая обработка
                            if table_name == 'auth_user':
                                in_insert = True
                                # Будем фильтровать только суперпользователей
                                continue
                            elif table_name == 'userprofile':
                                in_insert = True
                                # Будем фильтровать профили суперпользователей
                                continue
                            
                            # Для остальных таблиц - сохраняем INSERT
                            f.write(line + '\n')
                            in_insert = False
                        else:
                            f.write(line + '\n')
                            in_insert = False
                    elif in_insert:
                        # Пропускаем строки данных для таблиц, которые нужно очистить
                        if current_table in tables_to_clear:
                            continue
                        elif current_table == 'auth_user':
                            # Сохраняем только суперпользователей (is_superuser=1)
                            if ',1,' in line or ', 1,' in line or line.strip().endswith(',1)') or line.strip().endswith(', 1)'):
                                f.write(line + '\n')
                            continue
                        elif current_table == 'userprofile':
                            # Пропускаем все профили - они будут созданы автоматически
                            continue
                        else:
                            f.write(line + '\n')
                    else:
                        # Сохраняем все остальные строки (CREATE TABLE, индексы и т.д.)
                        f.write(line + '\n')
                
                # Добавляем очистку пользовательских таблиц и инициализацию
                f.write('\n\n-- ============================================\n')
                f.write('-- Очистка пользовательских данных\n')
                f.write('-- ============================================\n\n')
                
                for table in tables_to_clear:
                    f.write(f'DELETE FROM {table};\n')
                
                # Удаляем всех пользователей, кроме суперпользователей
                f.write("DELETE FROM userprofile WHERE user_id NOT IN (SELECT id FROM auth_user WHERE is_superuser = 1);\n")
                f.write("DELETE FROM auth_user WHERE is_superuser = 0;\n")
                
                # Сбрасываем балансы
                f.write("UPDATE main_organizationaccount SET balance = 0.00, tax_reserve = 0.00 WHERE id = 1;\n")
                f.write("UPDATE userprofile SET balance = 0.00;\n")
                
                # Инициализация обязательных записей
                f.write('\n\n-- ============================================\n')
                f.write('-- Инициализация обязательных записей\n')
                f.write('-- ============================================\n\n')
                
                f.write('-- Создание счета организации, если его нет\n')
                f.write('INSERT OR IGNORE INTO main_organizationaccount (id, balance, tax_reserve, created_at, updated_at)\n')
                f.write("VALUES (1, 0.00, 0.00, datetime('now'), datetime('now'));\n\n")
                
                f.write('-- Создание настроек чека, если их нет\n')
                f.write("INSERT OR IGNORE INTO main_receiptconfig (id, company_name, company_inn, company_address, cashier_name, shift_number, kkt_rn, kkt_sn, fn_number, site_fns)\n")
                f.write("VALUES (1, 'ООО «MPTCOURSE»', '7700000000', 'г. Москва, ул. Примерная, д. 1', 'Кассир', '1', '0000000000000000', '1234567890', '0000000000000000', 'www.nalog.ru');\n\n")
                
                f.write('-- Создание суперюзера admin@gmail.com с паролем 4856106Anton, если его нет\n')
                f.write("INSERT OR IGNORE INTO auth_user (username, email, password, is_superuser, is_staff, is_active, first_name, last_name, date_joined)\n")
                f.write("VALUES ('admin', 'admin@gmail.com', 'pbkdf2_sha256$1000000$FASiHAM7fJ5s43T8XIC86H$sw2Szw9ZpvtJ18TqqT3/KfjRiOzUPEQ5fSz/KsWd200=', 1, 1, 1, 'Admin', 'User', datetime('now'));\n\n")
            
            # Удаляем временный файл
            os.unlink(tmp_dump_path)
            return True
            
        elif 'postgresql' in engine:
            # Для PostgreSQL создаем дамп со структурой и данными, затем добавляем команды очистки
            db_name = db_config['NAME']
            db_user = db_config.get('USER', 'postgres')
            db_password = db_config.get('PASSWORD', '')
            db_host = db_config.get('HOST', 'localhost')
            db_port = db_config.get('PORT', '5432')
            
            # Формируем команду pg_dump (со структурой и данными)
            cmd = ['pg_dump']
            if db_host:
                cmd.extend(['-h', db_host])
            if db_port:
                cmd.extend(['-p', str(db_port)])
            if db_user:
                cmd.extend(['-U', db_user])
            cmd.append(db_name)
            
            # Устанавливаем переменную окружения для пароля
            env = os.environ.copy()
            if db_password:
                env['PGPASSWORD'] = db_password
            
            # Создаем дамп
            with open(output_path, 'w', encoding='utf-8') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env
                )
                
                if result.returncode != 0:
                    return False
                
                # Добавляем очистку пользовательских данных
                f.write('\n\n-- ============================================\n')
                f.write('-- Очистка пользовательских данных\n')
                f.write('-- ============================================\n\n')
                
                # Список таблиц для очистки
                tables_to_clear = [
                    'main_product',
                    'main_productimage',
                    'main_productsize',
                    'main_producttag',
                    'main_order',
                    'main_orderitem',
                    'main_cart',
                    'main_cartitem',
                    'main_favorite',
                    'main_productreview',
                    'main_supportticket',
                    'main_payment',
                    'main_savedpaymentmethod',
                    'main_balancetransaction',
                    'main_cardtransaction',
                    'main_receipt',
                    'main_receiptitem',
                    'main_activitylog',
                    'main_databasebackup',
                    'main_useraddress',
                    'main_delivery',
                    'main_organizationtransaction',
                    'main_promotion',
                ]
                
                # Отключаем проверку внешних ключей для быстрой очистки
                f.write('-- Временно отключаем проверку внешних ключей\n')
                f.write('SET session_replication_role = replica;\n\n')
                
                for table in tables_to_clear:
                    f.write(f'TRUNCATE TABLE {table} CASCADE;\n')
                
                # Удаляем пользователей, кроме суперпользователей
                f.write("DELETE FROM userprofile WHERE user_id NOT IN (SELECT id FROM auth_user WHERE is_superuser = TRUE);\n")
                f.write("DELETE FROM auth_user WHERE is_superuser = FALSE;\n")
                
                # Сбрасываем балансы
                f.write("UPDATE main_organizationaccount SET balance = 0.00, tax_reserve = 0.00 WHERE id = 1;\n")
                f.write("UPDATE userprofile SET balance = 0.00;\n")
                
                # Включаем обратно проверку внешних ключей
                f.write('\n-- Включаем обратно проверку внешних ключей\n')
                f.write('SET session_replication_role = DEFAULT;\n\n')
                
                # Инициализация обязательных записей
                f.write('-- ============================================\n')
                f.write('-- Инициализация обязательных записей\n')
                f.write('-- ============================================\n\n')
                
                f.write('-- Создание счета организации, если его нет\n')
                f.write('INSERT INTO main_organizationaccount (id, balance, tax_reserve, created_at, updated_at)\n')
                f.write("VALUES (1, 0.00, 0.00, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)\n")
                f.write("ON CONFLICT (id) DO UPDATE SET balance = 0.00, tax_reserve = 0.00;\n\n")
                
                f.write('-- Создание настроек чека, если их нет\n')
                f.write("INSERT INTO main_receiptconfig (id, company_name, company_inn, company_address, cashier_name, shift_number, kkt_rn, kkt_sn, fn_number, site_fns)\n")
                f.write("VALUES (1, 'ООО «MPTCOURSE»', '7700000000', 'г. Москва, ул. Примерная, д. 1', 'Кассир', '1', '0000000000000000', '1234567890', '0000000000000000', 'www.nalog.ru')\n")
                f.write("ON CONFLICT (id) DO NOTHING;\n\n")
                
                f.write('-- Создание суперюзера admin@gmail.com с паролем 4856106Anton, если его нет\n')
                f.write("INSERT INTO auth_user (username, email, password, is_superuser, is_staff, is_active, first_name, last_name, date_joined)\n")
                f.write("VALUES ('admin', 'admin@gmail.com', 'pbkdf2_sha256$1000000$FASiHAM7fJ5s43T8XIC86H$sw2Szw9ZpvtJ18TqqT3/KfjRiOzUPEQ5fSz/KsWd200=', TRUE, TRUE, TRUE, 'Admin', 'User', CURRENT_TIMESTAMP)\n")
                f.write("ON CONFLICT (username) DO UPDATE SET\n")
                f.write("    email = EXCLUDED.email,\n")
                f.write("    password = EXCLUDED.password,\n")
                f.write("    is_superuser = EXCLUDED.is_superuser,\n")
                f.write("    is_staff = EXCLUDED.is_staff,\n")
                f.write("    is_active = EXCLUDED.is_active;\n\n")
            
            return True
        else:
            return False
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f'Ошибка при создании чистого бэкапа: {str(e)}')
        return False