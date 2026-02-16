"""
Management command для тестирования созданных SQL объектов:
- VIEW (представления)
- Stored Procedures (хранимые процедуры)
- Triggers (триггеры)
"""
from django.core.management.base import BaseCommand
from django.db import connection
from decimal import Decimal
import json


class Command(BaseCommand):
    help = 'Тестирует созданные SQL объекты (VIEW, процедуры, триггеры)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== Тестирование SQL объектов ===\n'))
        
        # Тест 1: Проверка VIEW
        self.stdout.write(self.style.WARNING('1. Тестирование VIEW...'))
        self.test_views()
        
        # Тест 2: Проверка хранимых процедур
        self.stdout.write(self.style.WARNING('\n2. Тестирование хранимых процедур...'))
        self.test_procedures()
        
        # Тест 3: Проверка триггеров
        self.stdout.write(self.style.WARNING('\n3. Тестирование триггеров...'))
        self.test_triggers()
        
        self.stdout.write(self.style.SUCCESS('\n=== Тестирование завершено ==='))

    def test_views(self):
        """Тестирует созданные VIEW"""
        with connection.cursor() as cursor:
            # Тест v_order_summary
            try:
                cursor.execute("SELECT COUNT(*) FROM v_order_summary")
                count = cursor.fetchone()[0]
                self.stdout.write(f"  ✓ v_order_summary: найдено {count} записей")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ v_order_summary: {str(e)}"))
            
            # Тест v_product_sales_stats
            try:
                cursor.execute("SELECT COUNT(*) FROM v_product_sales_stats")
                count = cursor.fetchone()[0]
                self.stdout.write(f"  ✓ v_product_sales_stats: найдено {count} записей")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ v_product_sales_stats: {str(e)}"))
            
            # Тест v_user_balance_summary
            try:
                cursor.execute("SELECT COUNT(*) FROM v_user_balance_summary")
                count = cursor.fetchone()[0]
                self.stdout.write(f"  ✓ v_user_balance_summary: найдено {count} записей")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ v_user_balance_summary: {str(e)}"))

    def test_procedures(self):
        """Тестирует хранимые процедуры"""
        with connection.cursor() as cursor:
            # Тест calculate_order_total
            try:
                # Получаем первый заказ для теста
                cursor.execute("SELECT id FROM main_order LIMIT 1")
                result = cursor.fetchone()
                if result:
                    order_id = result[0]
                    cursor.execute("SELECT calculate_order_total(%s)", [order_id])
                    total = cursor.fetchone()[0]
                    self.stdout.write(f"  ✓ calculate_order_total: для заказа #{order_id} = {total}")
                else:
                    self.stdout.write(self.style.WARNING("  ⚠ calculate_order_total: нет заказов для теста"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ calculate_order_total: {str(e)}"))
            
            # Тест apply_promo_to_order (только проверка существования)
            try:
                cursor.execute("""
                    SELECT proname FROM pg_proc 
                    WHERE proname = 'apply_promo_to_order'
                """)
                if cursor.fetchone():
                    self.stdout.write("  ✓ apply_promo_to_order: процедура существует")
                else:
                    self.stdout.write(self.style.ERROR("  ✗ apply_promo_to_order: процедура не найдена"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ apply_promo_to_order: {str(e)}"))
            
            # Тест update_user_balance (только проверка существования)
            try:
                cursor.execute("""
                    SELECT proname FROM pg_proc 
                    WHERE proname = 'update_user_balance'
                """)
                if cursor.fetchone():
                    self.stdout.write("  ✓ update_user_balance: процедура существует")
                else:
                    self.stdout.write(self.style.ERROR("  ✗ update_user_balance: процедура не найдена"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  ✗ update_user_balance: {str(e)}"))

    def test_triggers(self):
        """Тестирует триггеры"""
        with connection.cursor() as cursor:
            # Проверяем существование триггеров
            triggers_to_check = [
                'trigger_audit_order_changes',
                'trigger_audit_balance_changes',
                'trigger_audit_product_changes'
            ]
            
            for trigger_name in triggers_to_check:
                try:
                    cursor.execute("""
                        SELECT tgname FROM pg_trigger 
                        WHERE tgname = %s
                    """, [trigger_name])
                    if cursor.fetchone():
                        self.stdout.write(f"  ✓ {trigger_name}: триггер существует")
                    else:
                        self.stdout.write(self.style.ERROR(f"  ✗ {trigger_name}: триггер не найден"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ✗ {trigger_name}: {str(e)}"))

