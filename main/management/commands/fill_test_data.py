"""
Команда для заполнения базы данных тестовыми данными
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from main.models import (
    Role, UserProfile, UserAddress, Category, Brand, Supplier, Product, ProductImage,
    ProductSize, Tag, ProductTag, Favorite, Cart, CartItem, Order, OrderItem,
    Payment, Delivery, Promotion, ProductReview, SupportTicket, ActivityLog,
    SavedPaymentMethod, CardTransaction, BalanceTransaction, Receipt, ReceiptItem,
    ReceiptConfig, OrganizationAccount, OrganizationTransaction
)


class Command(BaseCommand):
    help = 'Заполняет базу данных тестовыми данными'

    def handle(self, *args, **options):
        self.stdout.write('Начинаем заполнение базы данных тестовыми данными...')
        
        # 1. Создаем обязательные записи
        self.stdout.write('1. Создание обязательных записей...')
        org_account, _ = OrganizationAccount.objects.get_or_create(
            pk=1,
            defaults={'balance': Decimal('0.00'), 'tax_reserve': Decimal('0.00')}
        )
        self.stdout.write(self.style.SUCCESS(f'   ✓ OrganizationAccount создан (id={org_account.id})'))
        
        receipt_config, _ = ReceiptConfig.objects.get_or_create(
            pk=1,
            defaults={
                'company_name': 'ООО «MPTCOURSE»',
                'company_inn': '7700000000',
                'company_address': 'г. Москва, ул. Примерная, д. 1',
                'cashier_name': 'Кассир',
                'shift_number': '1',
                'kkt_rn': '0000000000000000',
                'kkt_sn': '1234567890',
                'fn_number': '0000000000000000',
                'site_fns': 'www.nalog.ru'
            }
        )
        self.stdout.write(self.style.SUCCESS(f'   ✓ ReceiptConfig создан (id={receipt_config.id})'))
        
        # 2. Создаем роли (нормализованные ADMIN / MANAGER / USER)
        self.stdout.write('2. Создание ролей...')
        admin_role, _ = Role.objects.get_or_create(role_name='ADMIN')
        manager_role, _ = Role.objects.get_or_create(role_name='MANAGER')
        customer_role, _ = Role.objects.get_or_create(role_name='USER')
        self.stdout.write(self.style.SUCCESS('   ✓ Роли созданы'))
        
        # 3. Создаем пользователей
        self.stdout.write('3. Создание пользователей...')
        
        # Администратор
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@mptcourse.ru',
                'first_name': 'Администратор',
                'last_name': 'Системы',
                'is_staff': True,
                'is_superuser': True,
                'is_active': True
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
        
        admin_profile, _ = UserProfile.objects.get_or_create(
            user=admin_user,
            defaults={
                'role': admin_role,
                'phone_number': '+7 (999) 123-45-67',
                'balance': Decimal('100000.00'),
                'user_status': 'active'
            }
        )
        self.stdout.write(self.style.SUCCESS(f'   ✓ Администратор создан (username: admin, password: admin123)'))
        
        # Менеджер
        manager_user, created = User.objects.get_or_create(
            username='manager',
            defaults={
                'email': 'manager@mptcourse.ru',
                'first_name': 'Менеджер',
                'last_name': 'Магазина',
                'is_staff': True,
                'is_active': True
            }
        )
        if created:
            manager_user.set_password('manager123')
            manager_user.save()
        
        manager_profile, _ = UserProfile.objects.get_or_create(
            user=manager_user,
            defaults={
                'role': manager_role,
                'phone_number': '+7 (999) 234-56-78',
                'balance': Decimal('50000.00'),
                'user_status': 'active'
            }
        )
        self.stdout.write(self.style.SUCCESS(f'   ✓ Менеджер создан (username: manager, password: manager123)'))
        
        # Обычный пользователь
        customer_user, created = User.objects.get_or_create(
            username='customer',
            defaults={
                'email': 'customer@example.com',
                'first_name': 'Иван',
                'last_name': 'Иванов',
                'is_active': True
            }
        )
        if created:
            customer_user.set_password('customer123')
            customer_user.save()
        
        customer_profile, _ = UserProfile.objects.get_or_create(
            user=customer_user,
            defaults={
                'role': customer_role,
                'phone_number': '+7 (999) 345-67-89',
                'balance': Decimal('5000.00'),
                'user_status': 'active'
            }
        )
        self.stdout.write(self.style.SUCCESS(f'   ✓ Пользователь создан (username: customer, password: customer123)'))
        
        # 4. Создаем адреса
        self.stdout.write('4. Создание адресов доставки...')
        address1, _ = UserAddress.objects.get_or_create(
            user=customer_user,
            city_name='Москва',
            street_name='Тверская',
            house_number='1',
            defaults={
                'address_title': 'Дом',
                'apartment_number': '10',
                'postal_code': '101000',
                'is_primary': True
            }
        )
        address2, _ = UserAddress.objects.get_or_create(
            user=customer_user,
            city_name='Москва',
            street_name='Арбат',
            house_number='20',
            defaults={
                'address_title': 'Работа',
                'apartment_number': '5',
                'postal_code': '119002',
                'is_primary': False
            }
        )
        self.stdout.write(self.style.SUCCESS('   ✓ Адреса созданы'))
        
        # 5. Создаем категории
        self.stdout.write('5. Создание категорий...')
        category_clothes, _ = Category.objects.get_or_create(
            category_name='Одежда',
            defaults={'category_description': 'Одежда для всех'}
        )
        category_shoes, _ = Category.objects.get_or_create(
            category_name='Обувь',
            defaults={'category_description': 'Обувь для всех'}
        )
        category_accessories, _ = Category.objects.get_or_create(
            category_name='Аксессуары',
            defaults={'category_description': 'Аксессуары и дополнения'}
        )
        self.stdout.write(self.style.SUCCESS('   ✓ Категории созданы'))
        
        # 6. Создаем бренды
        self.stdout.write('6. Создание брендов...')
        brand_nike, _ = Brand.objects.get_or_create(
            brand_name='Nike',
            defaults={'brand_country': 'USA', 'brand_description': 'Just Do It'}
        )
        brand_adidas, _ = Brand.objects.get_or_create(
            brand_name='Adidas',
            defaults={'brand_country': 'Germany', 'brand_description': 'Impossible is Nothing'}
        )
        brand_puma, _ = Brand.objects.get_or_create(
            brand_name='Puma',
            defaults={'brand_country': 'Germany', 'brand_description': 'Forever Faster'}
        )
        self.stdout.write(self.style.SUCCESS('   ✓ Бренды созданы'))
        
        # 7. Создаем поставщиков
        self.stdout.write('7. Создание поставщиков...')
        supplier1, _ = Supplier.objects.get_or_create(
            supplier_name='ООО "СпортТовары"',
            defaults={
                'contact_person': 'Иван Петров',
                'contact_phone': '+7 (495) 123-45-67',
                'contact_email': 'info@sporttovary.ru',
                'supply_country': 'Россия',
                'delivery_cost': Decimal('500.00'),
                'supplier_type': 'wholesale'
            }
        )
        self.stdout.write(self.style.SUCCESS('   ✓ Поставщики созданы'))
        
        # 8. Создаем товары
        self.stdout.write('8. Создание товаров...')
        products_data = [
            {
                'product_name': 'Футболка Nike Dri-FIT',
                'category': category_clothes,
                'brand': brand_nike,
                'supplier': supplier1,
                'price': Decimal('2999.00'),
                'discount': Decimal('10.00'),
                'stock_quantity': 50,
                'product_description': 'Спортивная футболка с технологией Dri-FIT',
                'sizes': ['S', 'M', 'L', 'XL']
            },
            {
                'product_name': 'Кроссовки Adidas Ultraboost',
                'category': category_shoes,
                'brand': brand_adidas,
                'supplier': supplier1,
                'price': Decimal('12999.00'),
                'discount': Decimal('15.00'),
                'stock_quantity': 30,
                'product_description': 'Беговые кроссовки с технологией Boost',
                'sizes': ['40', '41', '42', '43', '44', '45']
            },
            {
                'product_name': 'Шорты Puma Training',
                'category': category_clothes,
                'brand': brand_puma,
                'supplier': supplier1,
                'price': Decimal('2499.00'),
                'discount': Decimal('0.00'),
                'stock_quantity': 40,
                'product_description': 'Тренировочные шорты',
                'sizes': ['S', 'M', 'L']
            },
            {
                'product_name': 'Кепка Nike',
                'category': category_accessories,
                'brand': brand_nike,
                'supplier': supplier1,
                'price': Decimal('1999.00'),
                'discount': Decimal('5.00'),
                'stock_quantity': 25,
                'product_description': 'Бейсболка с логотипом Nike',
                'sizes': ['One Size']
            },
            {
                'product_name': 'Рюкзак Adidas',
                'category': category_accessories,
                'brand': brand_adidas,
                'supplier': supplier1,
                'price': Decimal('4999.00'),
                'discount': Decimal('20.00'),
                'stock_quantity': 20,
                'product_description': 'Спортивный рюкзак',
                'sizes': ['One Size']
            }
        ]
        
        created_products = []
        for prod_data in products_data:
            sizes = prod_data.pop('sizes')
            product, created = Product.objects.get_or_create(
                product_name=prod_data['product_name'],
                defaults=prod_data
            )
            if created:
                # Создаем размеры
                for size_label in sizes:
                    ProductSize.objects.get_or_create(
                        product=product,
                        size_label=size_label,
                        defaults={
                            'size_stock': product.stock_quantity // len(sizes),
                            'size_type': 'clothing' if size_label in ['S', 'M', 'L', 'XL'] else 'shoes' if size_label.isdigit() else 'accessories'
                        }
                    )
                created_products.append(product)
        
        self.stdout.write(self.style.SUCCESS(f'   ✓ Создано товаров: {len(created_products)}'))
        
        # 9. Создаем теги
        self.stdout.write('9. Создание тегов...')
        tag_new, _ = Tag.objects.get_or_create(tag_name='Новинка')
        tag_sale, _ = Tag.objects.get_or_create(tag_name='Распродажа')
        tag_popular, _ = Tag.objects.get_or_create(tag_name='Популярное')
        
        # Привязываем теги к товарам
        if created_products:
            ProductTag.objects.get_or_create(product=created_products[0], tag=tag_new)
            ProductTag.objects.get_or_create(product=created_products[1], tag=tag_popular)
            ProductTag.objects.get_or_create(product=created_products[2], tag=tag_sale)
        self.stdout.write(self.style.SUCCESS('   ✓ Теги созданы'))
        
        # 10. Создаем промокоды
        self.stdout.write('10. Создание промокодов...')
        promo1, _ = Promotion.objects.get_or_create(
            promo_code='WELCOME10',
            defaults={
                'promo_description': 'Скидка 10% для новых клиентов',
                'discount': Decimal('10.00'),
                'is_active': True
            }
        )
        promo2, _ = Promotion.objects.get_or_create(
            promo_code='SUMMER20',
            defaults={
                'promo_description': 'Летняя скидка 20%',
                'discount': Decimal('20.00'),
                'is_active': True
            }
        )
        self.stdout.write(self.style.SUCCESS('   ✓ Промокоды созданы'))
        
        # 11. Создаем сохраненные способы оплаты
        self.stdout.write('11. Создание сохраненных способов оплаты...')
        saved_payment, _ = SavedPaymentMethod.objects.get_or_create(
            user=customer_user,
            card_number='1234',
            defaults={
                'card_holder_name': 'IVAN IVANOV',
                'expiry_month': '12',
                'expiry_year': '2025',
                'card_type': 'visa',
                'is_default': True,
                'balance': Decimal('10000.00')
            }
        )
        self.stdout.write(self.style.SUCCESS('   ✓ Сохраненные способы оплаты созданы'))
        
        # 12. Создаем корзину с товарами для пользователя
        self.stdout.write('12. Создание корзины с товарами...')
        cart, _ = Cart.objects.get_or_create(user=customer_user)
        
        # Очищаем старые элементы корзины
        CartItem.objects.filter(cart=cart).delete()
        
        if created_products:
            # Добавляем первый товар с размером
            product1 = created_products[0]
            size1 = ProductSize.objects.filter(product=product1).first()
            if size1:
                CartItem.objects.create(
                    cart=cart,
                    product=product1,
                    size=size1,
                    quantity=2,
                    unit_price=product1.final_price
                )
            
            # Добавляем второй товар
            product2 = created_products[1]
            size2 = ProductSize.objects.filter(product=product2).first()
            if size2:
                CartItem.objects.create(
                    cart=cart,
                    product=product2,
                    size=size2,
                    quantity=1,
                    unit_price=product2.final_price
                )
        
        self.stdout.write(self.style.SUCCESS('   ✓ Корзина создана'))
        
        # 13. Создаем отзывы
        self.stdout.write('13. Создание отзывов...')
        if created_products:
            ProductReview.objects.get_or_create(
                user=customer_user,
                product=created_products[0],
                defaults={
                    'rating_value': 5,
                    'review_text': 'Отличный товар! Очень доволен покупкой.'
                }
            )
        self.stdout.write(self.style.SUCCESS('   ✓ Отзывы созданы'))
        
        # 14. Создаем избранное
        self.stdout.write('14. Создание избранного...')
        if created_products:
            Favorite.objects.get_or_create(
                user=customer_user,
                product=created_products[1]
            )
        self.stdout.write(self.style.SUCCESS('   ✓ Избранное создано'))
        
        self.stdout.write(self.style.SUCCESS('\n✓ База данных успешно заполнена тестовыми данными!'))
        self.stdout.write('\nДанные для входа:')
        self.stdout.write('  Администратор: admin / admin123')
        self.stdout.write('  Менеджер: manager / manager123')
        self.stdout.write('  Пользователь: customer / customer123')
        self.stdout.write('\nПромокоды:')
        self.stdout.write('  WELCOME10 - скидка 10%')
        self.stdout.write('  SUMMER20 - скидка 20%')

