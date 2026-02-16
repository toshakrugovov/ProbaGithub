"""
Команда для заполнения корзины товарами для указанного пользователя
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from main.models import Cart, CartItem, Product, ProductSize
from decimal import Decimal


class Command(BaseCommand):
    help = 'Заполняет корзину товарами для указанного пользователя'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Имя пользователя')
        parser.add_argument('--clear', action='store_true', help='Очистить корзину перед добавлением')

    def handle(self, *args, **options):
        username = options['username']
        
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Пользователь "{username}" не найден'))
            return
        
        cart, created = Cart.objects.get_or_create(user=user)
        
        if options['clear']:
            CartItem.objects.filter(cart=cart).delete()
            self.stdout.write('Корзина очищена')
        
        # Получаем доступные товары
        products = Product.objects.filter(is_available=True)[:3]
        
        if not products.exists():
            self.stdout.write(self.style.ERROR('Нет доступных товаров'))
            return
        
        added_count = 0
        for product in products:
            size = ProductSize.objects.filter(product=product).first()
            item, created = CartItem.objects.get_or_create(
                cart=cart,
                product=product,
                size=size,
                defaults={
                    'quantity': 1,
                    'unit_price': product.final_price
                }
            )
            if created:
                added_count += 1
                self.stdout.write(f'  Добавлен товар: {product.product_name}')
        
        self.stdout.write(self.style.SUCCESS(f'\n✓ В корзину добавлено товаров: {added_count}'))
        self.stdout.write(f'Всего товаров в корзине: {cart.items.count()}')

