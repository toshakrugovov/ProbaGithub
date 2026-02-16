"""
Команда для исправления некорректных значений Decimal в базе данных
"""
from django.core.management.base import BaseCommand
from django.db import connection
from decimal import Decimal, InvalidOperation


class Command(BaseCommand):
    help = 'Исправляет некорректные значения Decimal в базе данных'

    def handle(self, *args, **options):
        self.stdout.write('Начинаем исправление некорректных значений Decimal...')
        
        fixed_count = 0
        
        with connection.cursor() as cursor:
            # Исправляем CartItem
            self.stdout.write('Проверка CartItem...')
            try:
                cursor.execute("""
                    UPDATE main_cartitem 
                    SET unit_price = 0.00 
                    WHERE unit_price IS NULL OR unit_price = '' OR CAST(unit_price AS TEXT) = ''
                """)
                fixed_count += cursor.rowcount
                if cursor.rowcount > 0:
                    self.stdout.write(f'  Исправлено CartItem: {cursor.rowcount}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Ошибка при обработке CartItem: {str(e)}'))
            # Исправляем OrderItem
            self.stdout.write('Проверка OrderItem...')
            try:
                cursor.execute("""
                    UPDATE main_orderitem 
                    SET unit_price = 0.00 
                    WHERE unit_price IS NULL OR unit_price = '' OR CAST(unit_price AS TEXT) = ''
                """)
                fixed_count += cursor.rowcount
                if cursor.rowcount > 0:
                    self.stdout.write(f'  Исправлено OrderItem: {cursor.rowcount}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Ошибка при обработке OrderItem: {str(e)}'))
            
            # Исправляем ReceiptItem
            self.stdout.write('Проверка ReceiptItem...')
            try:
                cursor.execute("""
                    UPDATE main_receiptitem 
                    SET unit_price = 0.00 
                    WHERE unit_price IS NULL OR unit_price = '' OR CAST(unit_price AS TEXT) = ''
                """)
                fixed_count += cursor.rowcount
                cursor.execute("""
                    UPDATE main_receiptitem 
                    SET line_total = 0.00 
                    WHERE line_total IS NULL OR line_total = '' OR CAST(line_total AS TEXT) = ''
                """)
                fixed_count += cursor.rowcount
                cursor.execute("""
                    UPDATE main_receiptitem 
                    SET vat_amount = 0.00 
                    WHERE vat_amount IS NULL OR vat_amount = '' OR CAST(vat_amount AS TEXT) = ''
                """)
                fixed_count += cursor.rowcount
                if cursor.rowcount > 0:
                    self.stdout.write(f'  Исправлено ReceiptItem')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Ошибка при обработке ReceiptItem: {str(e)}'))
            
            # Исправляем UserProfile
            self.stdout.write('Проверка UserProfile...')
            try:
                cursor.execute("""
                    UPDATE main_userprofile 
                    SET balance = 0.00 
                    WHERE balance IS NULL OR balance = '' OR CAST(balance AS TEXT) = ''
                """)
                fixed_count += cursor.rowcount
                if cursor.rowcount > 0:
                    self.stdout.write(f'  Исправлено UserProfile: {cursor.rowcount}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Ошибка при обработке UserProfile: {str(e)}'))
            
            # Исправляем SavedPaymentMethod
            self.stdout.write('Проверка SavedPaymentMethod...')
            try:
                cursor.execute("""
                    UPDATE main_savedpaymentmethod 
                    SET balance = 0.00 
                    WHERE balance IS NULL OR balance = '' OR CAST(balance AS TEXT) = ''
                """)
                fixed_count += cursor.rowcount
                if cursor.rowcount > 0:
                    self.stdout.write(f'  Исправлено SavedPaymentMethod: {cursor.rowcount}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Ошибка при обработке SavedPaymentMethod: {str(e)}'))
            
            # Исправляем OrganizationAccount
            self.stdout.write('Проверка OrganizationAccount...')
            try:
                cursor.execute("""
                    UPDATE main_organizationaccount 
                    SET balance = 0.00 
                    WHERE balance IS NULL OR balance = '' OR CAST(balance AS TEXT) = ''
                """)
                fixed_count += cursor.rowcount
                cursor.execute("""
                    UPDATE main_organizationaccount 
                    SET tax_reserve = 0.00 
                    WHERE tax_reserve IS NULL OR tax_reserve = '' OR CAST(tax_reserve AS TEXT) = ''
                """)
                fixed_count += cursor.rowcount
                if cursor.rowcount > 0:
                    self.stdout.write(f'  Исправлено OrganizationAccount')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Ошибка при обработке OrganizationAccount: {str(e)}'))
        
        if fixed_count > 0:
            self.stdout.write(self.style.SUCCESS(f'\n✓ Исправлено записей: {fixed_count}'))
        else:
            self.stdout.write(self.style.SUCCESS('\n✓ Некорректных значений не найдено'))

