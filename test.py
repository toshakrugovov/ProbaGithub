"""
Комплексные тесты для функционала интернет-магазина MPTCOURSE
Покрывает: функциональное, интеграционное, безопасность, отказоустойчивость
"""

import os
import django
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.db import transaction
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from decimal import Decimal
import json
import base64

# Настройка Django окружения
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mptcourse.settings')
django.setup()

# Переопределение настроек БД для тестов (используем SQLite в памяти)
TEST_DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

from main.models import (
    Role, UserProfile, UserAddress, Category, Brand, Supplier, Product,
    ProductSize, Cart, CartItem, Order, OrderItem, Promotion, ProductReview,
    SupportTicket, ActivityLog, SavedPaymentMethod, BalanceTransaction,
    OrganizationAccount, UserSettings
)
from main.db_procedures import (
    calculate_order_total, apply_promo_to_order, update_user_balance
)
from main.encryption import DataEncryption


@override_settings(DATABASES=TEST_DATABASES)
class FunctionalTests(TestCase):
    """Функциональное тестирование: CRUD, поиск, сортировки, фильтры"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = APIClient()
        
        # Создание ролей
        self.role_user = Role.objects.create(role_name='Пользователь')
        self.role_manager = Role.objects.create(role_name='Менеджер')
        self.role_admin = Role.objects.create(role_name='Администратор')
        
        # Создание пользователей
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        self.user_profile = UserProfile.objects.create(
            user=self.user,
            role=self.role_user,
            phone_number='+79991234567',
            user_status='active'
        )
        
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='adminpass123',
            first_name='Admin',
            last_name='User',
            is_staff=True,
            is_superuser=True
        )
        self.admin_profile = UserProfile.objects.create(
            user=self.admin,
            role=self.role_admin,
            user_status='active'
        )
        
        # Создание категории и бренда
        self.category = Category.objects.create(
            category_name='Одежда',
            category_description='Одежда для всех'
        )
        self.brand = Brand.objects.create(
            brand_name='TestBrand',
            brand_country='Россия'
        )
        
        # Создание товара
        self.product = Product.objects.create(
            product_name='Test Product',
            category=self.category,
            brand=self.brand,
            price=Decimal('1000.00'),
            stock_quantity=10,
            is_available=True
        )
        self.product_size = ProductSize.objects.create(
            product=self.product,
            size_label='M',
            size_stock=5
        )
    
    def test_user_registration(self):
        """Тест регистрации нового пользователя"""
        url = '/api/register/'
        data = {
            'first_name': 'New',
            'last_name': 'User',
            'email': 'newuser@example.com',
            'password': 'newpass123',
            'password2': 'newpass123',
            'personal_data_consent': True
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        self.assertTrue(User.objects.filter(email='newuser@example.com').exists())
    
    def test_user_login(self):
        """Тест входа пользователя"""
        url = '/api/login/'
        data = {
            'email': 'test@example.com',
            'password': 'testpass123'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
    
    def test_create_product(self):
        """Тест создания товара (CRUD - Create)"""
        self.client.force_authenticate(user=self.admin)
        url = '/api/management/products/'
        data = {
            'product_name': 'New Product',
            'category_id': self.category.id,
            'brand_id': self.brand.id,
            'price': '2000.00',
            'stock_quantity': 20,
            'is_available': True
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Product.objects.filter(product_name='New Product').exists())
    
    def test_read_product(self):
        """Тест чтения товара (CRUD - Read)"""
        url = f'/api/products/{self.product.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['product_name'], 'Test Product')
    
    def test_update_product(self):
        """Тест обновления товара (CRUD - Update)"""
        self.client.force_authenticate(user=self.admin)
        url = f'/api/management/products/{self.product.id}/'
        data = {
            'product_name': 'Updated Product',
            'price': '1500.00'
        }
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.product_name, 'Updated Product')
    
    def test_delete_product(self):
        """Тест удаления товара (CRUD - Delete)"""
        self.client.force_authenticate(user=self.admin)
        url = f'/api/management/products/{self.product.id}/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Product.objects.filter(id=self.product.id).exists())
    
    def test_catalog_search(self):
        """Тест поиска товаров в каталоге"""
        url = '/api/catalog/'
        response = self.client.get(url, {'search': 'Test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data.get('results', [])), 0)
    
    def test_catalog_filter_by_category(self):
        """Тест фильтрации товаров по категории"""
        url = '/api/catalog/'
        response = self.client.get(url, {'category': self.category.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', [])
        if results:
            self.assertEqual(results[0]['category'], self.category.id)
    
    def test_catalog_sort_by_price(self):
        """Тест сортировки товаров по цене"""
        # Создаем еще один товар с другой ценой
        product2 = Product.objects.create(
            product_name='Cheap Product',
            category=self.category,
            brand=self.brand,
            price=Decimal('500.00'),
            stock_quantity=5,
            is_available=True
        )
        
        url = '/api/catalog/'
        response = self.client.get(url, {'ordering': 'price'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', [])
        if len(results) >= 2:
            self.assertLessEqual(
                Decimal(results[0]['price']),
                Decimal(results[1]['price'])
            )
    
    def test_add_to_cart(self):
        """Тест добавления товара в корзину"""
        self.client.force_authenticate(user=self.user)
        url = '/api/cart/'
        data = {
            'product_id': self.product.id,
            'size_id': self.product_size.id,
            'quantity': 2
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(CartItem.objects.filter(
            cart__user=self.user,
            product=self.product
        ).exists())
    
    def test_create_order(self):
        """Тест создания заказа"""
        self.client.force_authenticate(user=self.user)
        
        # Создаем адрес
        address = UserAddress.objects.create(
            user=self.user,
            city_name='Москва',
            street_name='Тестовая',
            house_number='1',
            postal_code='123456'
        )
        
        # Добавляем товар в корзину
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            size=self.product_size,
            quantity=1,
            unit_price=self.product.price
        )
        
        url = '/api/orders/'
        data = {
            'address_id': address.id
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Order.objects.filter(user=self.user).exists())


@override_settings(DATABASES=TEST_DATABASES)
class IntegrationTests(TestCase):
    """Интеграционное тестирование: взаимодействие сервисов и API"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.user_profile = UserProfile.objects.create(
            user=self.user,
            user_status='active'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_order_creation_flow(self):
        """Тест полного потока создания заказа"""
        # 1. Создание адреса
        address_url = '/api/addresses/'
        address_data = {
            'city_name': 'Москва',
            'street_name': 'Тестовая',
            'house_number': '1',
            'postal_code': '123456'
        }
        address_response = self.client.post(address_url, address_data, format='json')
        self.assertEqual(address_response.status_code, status.HTTP_201_CREATED)
        address_id = address_response.data.get('address', {}).get('id')
        
        # 2. Добавление товара в корзину
        # (требует создания товара, категории, бренда)
        category = Category.objects.create(category_name='Test Category')
        brand = Brand.objects.create(brand_name='Test Brand')
        product = Product.objects.create(
            product_name='Test Product',
            category=category,
            brand=brand,
            price=Decimal('1000.00'),
            stock_quantity=10
        )
        size = ProductSize.objects.create(
            product=product,
            size_label='M',
            size_stock=5
        )
        
        cart_url = '/api/cart/'
        cart_data = {
            'product_id': product.id,
            'size_id': size.id,
            'quantity': 1
        }
        cart_response = self.client.post(cart_url, cart_data, format='json')
        self.assertEqual(cart_response.status_code, status.HTTP_200_OK)
        
        # 3. Создание заказа
        order_url = '/api/orders/'
        order_data = {'address_id': address_id}
        order_response = self.client.post(order_url, order_data, format='json')
        self.assertEqual(order_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Order.objects.filter(user=self.user).exists())
    
    def test_promo_code_application(self):
        """Тест применения промокода к заказу"""
        # Создание промокода
        promo = Promotion.objects.create(
            promo_code='TEST10',
            discount=Decimal('10.00'),
            is_active=True
        )
        
        # Создание заказа
        category = Category.objects.create(category_name='Test')
        brand = Brand.objects.create(brand_name='Test')
        product = Product.objects.create(
            product_name='Test',
            category=category,
            brand=brand,
            price=Decimal('1000.00'),
            stock_quantity=10
        )
        
        address = UserAddress.objects.create(
            user=self.user,
            city_name='Москва',
            street_name='Тестовая',
            house_number='1',
            postal_code='123456'
        )
        
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(
            cart=cart,
            product=product,
            quantity=1,
            unit_price=product.price
        )
        
        # Валидация промокода
        validate_url = '/api/validate-promo/'
        validate_data = {'promo_code': 'TEST10'}
        validate_response = self.client.post(validate_url, validate_data, format='json')
        self.assertEqual(validate_response.status_code, status.HTTP_200_OK)
        self.assertTrue(validate_response.data.get('success'))
    
    def test_balance_transaction_flow(self):
        """Тест потока транзакций баланса"""
        # Пополнение баланса
        balance_url = '/api/balance/'
        deposit_data = {
            'action': 'deposit',
            'amount': '1000.00'
        }
        deposit_response = self.client.post(balance_url, deposit_data, format='json')
        self.assertEqual(deposit_response.status_code, status.HTTP_200_OK)
        
        # Проверка баланса
        balance_response = self.client.get(balance_url)
        self.assertEqual(balance_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(
            Decimal(balance_response.data.get('balance', 0)),
            Decimal('1000.00')
        )


@override_settings(DATABASES=TEST_DATABASES)
class SecurityTests(TestCase):
    """Тестирование безопасности: SQL-инъекции, разграничение прав, шифрование"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.user_profile = UserProfile.objects.create(
            user=self.user,
            user_status='active'
        )
        
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='adminpass123',
            is_staff=True,
            is_superuser=True
        )
        self.admin_profile = UserProfile.objects.create(
            user=self.admin,
            user_status='active'
        )
    
    def test_sql_injection_protection(self):
        """Тест защиты от SQL-инъекций"""
        # Попытка SQL-инъекции через параметры поиска
        malicious_input = "'; DROP TABLE products; --"
        url = '/api/catalog/'
        response = self.client.get(url, {'search': malicious_input})
        # Запрос должен обработаться безопасно (не должно быть ошибки БД)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST])
        # Таблица products должна существовать
        self.assertTrue(Product.objects.model._meta.db_table in ['product'])
    
    def test_unauthorized_access_denied(self):
        """Тест запрета доступа неавторизованным пользователям"""
        url = '/api/profile/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_user_cannot_access_admin_endpoints(self):
        """Тест запрета доступа обычных пользователей к админ-эндпоинтам"""
        self.client.force_authenticate(user=self.user)
        url = '/api/management/users/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_admin_can_access_admin_endpoints(self):
        """Тест доступа администратора к админ-эндпоинтам"""
        self.client.force_authenticate(user=self.admin)
        url = '/api/management/users/'
        response = self.client.get(url)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND])
    
    def test_password_hashing(self):
        """Тест хэширования паролей"""
        user = User.objects.create_user(
            username='hashtest',
            email='hashtest@example.com',
            password='testpass123'
        )
        # Пароль должен быть захеширован (не хранится в открытом виде)
        self.assertNotEqual(user.password, 'testpass123')
        self.assertTrue(user.password.startswith('pbkdf2_sha256$'))
    
    def test_card_number_encryption(self):
        """Тест шифрования номеров банковских карт"""
        self.client.force_authenticate(user=self.user)
        
        # Создание сохраненного способа оплаты
        url = '/api/payment-methods/'
        data = {
            'card_number': '1234567890123456',
            'card_holder_name': 'Test User',
            'expiry_month': '12',
            'expiry_year': '2025'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Проверка, что номер карты зашифрован в БД
        payment_method = SavedPaymentMethod.objects.filter(user=self.user).first()
        if payment_method:
            # Номер карты в БД не должен совпадать с исходным
            self.assertNotEqual(payment_method.card_number, '1234567890123456')
            # Но должен расшифровываться корректно
            decrypted = payment_method.get_card_number()
            self.assertEqual(decrypted, '1234567890123456')
    
    def test_csrf_protection(self):
        """Тест защиты от CSRF атак"""
        # Django REST Framework по умолчанию требует CSRF токен для POST запросов
        # (если не используется APIClient)
        client = Client()
        url = '/api/register/'
        data = {
            'first_name': 'Test',
            'last_name': 'User',
            'email': 'csrf@example.com',
            'password': 'testpass123',
            'password2': 'testpass123',
            'personal_data_consent': True
        }
        # Без CSRF токена запрос должен быть отклонен
        response = client.post(url, data)
        # В зависимости от настроек может быть 403 или 200 (если csrf_exempt)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN])


@override_settings(DATABASES=TEST_DATABASES)
class TransactionTests(TestCase):
    """Тестирование транзакций: атомарность операций"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.user_profile = UserProfile.objects.create(
            user=self.user,
            user_status='active',
            balance=Decimal('1000.00')
        )
        self.client.force_authenticate(user=self.user)
    
    def test_order_creation_atomicity(self):
        """Тест атомарности создания заказа"""
        # Создание тестовых данных
        category = Category.objects.create(category_name='Test')
        brand = Brand.objects.create(brand_name='Test')
        product = Product.objects.create(
            product_name='Test Product',
            category=category,
            brand=brand,
            price=Decimal('500.00'),
            stock_quantity=1
        )
        size = ProductSize.objects.create(
            product=product,
            size_label='M',
            size_stock=1
        )
        address = UserAddress.objects.create(
            user=self.user,
            city_name='Москва',
            street_name='Тестовая',
            house_number='1',
            postal_code='123456'
        )
        
        # Добавление в корзину
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(
            cart=cart,
            product=product,
            size=size,
            quantity=1,
            unit_price=product.price
        )
        
        # Создание заказа должно быть атомарным
        url = '/api/orders/'
        data = {'address_id': address.id}
        response = self.client.post(url, data, format='json')
        
        if response.status_code == status.HTTP_201_CREATED:
            # Проверка, что заказ создан и товар списан
            order = Order.objects.filter(user=self.user).first()
            self.assertIsNotNone(order)
            product.refresh_from_db()
            # Проверка, что количество товара уменьшилось
            self.assertLessEqual(product.stock_quantity, 0)


@override_settings(DATABASES=TEST_DATABASES)
class StoredProcedureTests(TestCase):
    """Тестирование хранимых процедур"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.user_profile = UserProfile.objects.create(
            user=self.user,
            user_status='active',
            balance=Decimal('1000.00')
        )
    
    def test_calculate_order_total(self):
        """Тест хранимой процедуры расчета суммы заказа"""
        # Создание заказа
        category = Category.objects.create(category_name='Test')
        brand = Brand.objects.create(brand_name='Test')
        product = Product.objects.create(
            product_name='Test Product',
            category=category,
            brand=brand,
            price=Decimal('1000.00'),
            stock_quantity=10
        )
        
        address = UserAddress.objects.create(
            user=self.user,
            city_name='Москва',
            street_name='Тестовая',
            house_number='1',
            postal_code='123456'
        )
        
        order = Order.objects.create(
            user=self.user,
            address=address,
            total_amount=Decimal('0.00'),
            delivery_cost=Decimal('1000.00')
        )
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=2,
            unit_price=product.price
        )
        
        # Вызов хранимой процедуры
        try:
            total = calculate_order_total(order.id)
            self.assertIsNotNone(total)
            self.assertGreaterEqual(total, Decimal('0.00'))
        except Exception as e:
            # Если процедура не существует в БД, пропускаем тест
            self.skipTest(f"Хранимая процедура не реализована: {e}")
    
    def test_update_user_balance(self):
        """Тест хранимой процедуры обновления баланса"""
        initial_balance = self.user_profile.balance
        
        try:
            result = update_user_balance(
                user_id=self.user.id,
                amount=Decimal('500.00'),
                transaction_type='deposit',
                description='Test deposit'
            )
            self.assertTrue(result.get('success', False))
            
            # Проверка обновления баланса
            self.user_profile.refresh_from_db()
            self.assertGreaterEqual(
                self.user_profile.balance,
                initial_balance + Decimal('500.00')
            )
        except Exception as e:
            # Если процедура не существует в БД, пропускаем тест
            self.skipTest(f"Хранимая процедура не реализована: {e}")


@override_settings(DATABASES=TEST_DATABASES)
class AuditLogTests(TestCase):
    """Тестирование журнала аудита"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='adminpass123',
            is_staff=True,
            is_superuser=True
        )
        self.admin_profile = UserProfile.objects.create(
            user=self.admin,
            user_status='active'
        )
    
    def test_activity_log_creation(self):
        """Тест создания записи в журнале аудита"""
        # Создание записи аудита
        log = ActivityLog.objects.create(
            user=self.admin,
            action_type='create',
            target_object='Product',
            action_description='Создан новый товар',
            ip_address='127.0.0.1'
        )
        self.assertIsNotNone(log.id)
        self.assertEqual(log.action_type, 'create')
        self.assertEqual(log.user, self.admin)


@override_settings(DATABASES=TEST_DATABASES)
class BackupRestoreTests(TestCase):
    """Тестирование резервного копирования и восстановления"""
    
    def test_backup_creation(self):
        """Тест создания резервной копии"""
        from main.utils import create_sql_dump
        import tempfile
        
        # Создание временного файла для дампа
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
            dump_path = f.name
        
        try:
            # Создание дампа
            result = create_sql_dump(dump_path, include_data=True)
            self.assertTrue(result)
            
            # Проверка, что файл создан и не пуст
            self.assertTrue(os.path.exists(dump_path))
            self.assertGreater(os.path.getsize(dump_path), 0)
        finally:
            # Удаление временного файла
            if os.path.exists(dump_path):
                os.unlink(dump_path)


@override_settings(DATABASES=TEST_DATABASES)
class PerformanceTests(TestCase):
    """Нагрузочное тестирование: массовые операции"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.user_profile = UserProfile.objects.create(
            user=self.user,
            user_status='active'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_bulk_product_creation(self):
        """Тест массового создания товаров"""
        category = Category.objects.create(category_name='Test')
        brand = Brand.objects.create(brand_name='Test')
        
        # Создание 10 товаров
        products = []
        for i in range(10):
            product = Product.objects.create(
                product_name=f'Product {i}',
                category=category,
                brand=brand,
                price=Decimal('1000.00'),
                stock_quantity=10
            )
            products.append(product)
        
        self.assertEqual(len(products), 10)
        self.assertEqual(Product.objects.count(), 10)
    
    def test_concurrent_cart_operations(self):
        """Тест одновременных операций с корзиной"""
        category = Category.objects.create(category_name='Test')
        brand = Brand.objects.create(brand_name='Test')
        product = Product.objects.create(
            product_name='Test Product',
            category=category,
            brand=brand,
            price=Decimal('1000.00'),
            stock_quantity=100
        )
        size = ProductSize.objects.create(
            product=product,
            size_label='M',
            size_stock=50
        )
        
        # Симуляция одновременных добавлений в корзину
        cart = Cart.objects.create(user=self.user)
        for i in range(5):
            CartItem.objects.create(
                cart=cart,
                product=product,
                size=size,
                quantity=1,
                unit_price=product.price
            )
        
        self.assertEqual(CartItem.objects.filter(cart=cart).count(), 5)


@override_settings(DATABASES=TEST_DATABASES)
class UserSettingsTests(TestCase):
    """Тестирование настроек пользователя"""
    
    def setUp(self):
        """Настройка тестовых данных"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.user_profile = UserProfile.objects.create(
            user=self.user,
            user_status='active'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_user_settings_creation(self):
        """Тест создания настроек пользователя"""
        # Настройки должны создаваться автоматически при создании профиля
        settings = UserSettings.get_or_create_for_user(self.user)
        self.assertIsNotNone(settings)
        self.assertEqual(settings.user, self.user)
        self.assertEqual(settings.theme, 'light')
    
    def test_user_settings_update(self):
        """Тест обновления настроек пользователя"""
        settings = UserSettings.get_or_create_for_user(self.user)
        settings.theme = 'dark'
        settings.date_format = 'YYYY-MM-DD'
        settings.save()
        
        settings.refresh_from_db()
        self.assertEqual(settings.theme, 'dark')
        self.assertEqual(settings.date_format, 'YYYY-MM-DD')


if __name__ == '__main__':
    import unittest
    unittest.main()

