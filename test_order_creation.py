#!/usr/bin/env python
"""
Тестовый скрипт для проверки создания заказа
"""
import os
import sys
import django

# Настройка Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mptcourse.settings')
django.setup()

from main.models import User, Cart, CartItem, Product, UserAddress, Order, OrderItem, Payment
from decimal import Decimal
from django.db import transaction

def test_order_creation():
    """Тестирует создание заказа"""
    try:
        # Получаем первого пользователя
        user = User.objects.first()
        if not user:
            print("❌ Пользователь не найден")
            return
        
        print(f"✅ Пользователь: {user.username} (ID: {user.id})")
        
        # Проверяем корзину
        cart = Cart.objects.filter(user=user).first()
        if not cart:
            print("❌ Корзина не найдена")
            return
        
        print(f"✅ Корзина найдена (ID: {cart.id})")
        
        cart_items = cart.items.all()
        print(f"✅ Элементов в корзине: {cart_items.count()}")
        
        for item in cart_items:
            print(f"  - Товар: {item.product.product_name if item.product else 'None'} (ID: {item.product.id if item.product else None})")
            print(f"    Размер: {item.size.size_label if item.size else 'None'}")
            print(f"    Количество: {item.quantity}, Цена: {item.unit_price}")
        
        # Проверяем адрес
        address = UserAddress.objects.filter(user=user).first()
        if not address:
            print("❌ Адрес не найден")
            return
        
        print(f"✅ Адрес найден (ID: {address.id})")
        
        # Рассчитываем суммы
        cart_total = Decimal('0.00')
        for item in cart_items:
            if item.unit_price and item.quantity:
                cart_total += Decimal(str(item.unit_price)) * int(item.quantity)
        
        print(f"✅ Сумма корзины: {cart_total}")
        
        delivery_cost = Decimal('1000.00')
        discount_amount = Decimal('0.00')
        subtotal_after_discount = (cart_total - discount_amount).quantize(Decimal('0.01'))
        pre_vat_amount = (subtotal_after_discount + delivery_cost).quantize(Decimal('0.01'))
        vat_rate = Decimal('20.00')
        vat_amount = (pre_vat_amount * vat_rate / Decimal('100')).quantize(Decimal('0.01'))
        amount_after_vat = (pre_vat_amount + vat_amount).quantize(Decimal('0.01'))
        tax_rate = Decimal('13.00')
        tax_amount = (amount_after_vat * tax_rate / Decimal('100')).quantize(Decimal('0.01'))
        final_amount = amount_after_vat.quantize(Decimal('0.01'))
        
        print(f"✅ Итоговая сумма: {final_amount}")
        
        # Пытаемся создать заказ
        print("\n🔄 Создание заказа...")
        try:
            with transaction.atomic():
                order_data = {
                    'user': user,
                    'address': address,
                    'total_amount': final_amount,
                    'delivery_cost': delivery_cost,
                    'discount_amount': discount_amount,
                    'vat_rate': vat_rate,
                    'vat_amount': vat_amount,
                    'tax_rate': tax_rate,
                    'tax_amount': tax_amount,
                    'paid_from_balance': False,
                    'order_status': 'processing'
                }
                
                print(f"📝 Данные заказа: {order_data}")
                
                order = Order.objects.create(**order_data)
                print(f"✅ Заказ создан (ID: {order.id})")
                
                # Создаем позиции заказа
                order_items_list = []
                for item in cart_items:
                    if not item.product:
                        print(f"⚠️ Пропуск элемента: товар отсутствует")
                        continue
                    
                    unit_price = Decimal(str(item.unit_price)) if item.unit_price else Decimal('0.00')
                    
                    order_item = OrderItem.objects.create(
                        order=order,
                        product=item.product,
                        size=item.size,
                        quantity=item.quantity,
                        unit_price=unit_price,
                    )
                    order_items_list.append(order_item)
                    print(f"✅ Позиция заказа создана (ID: {order_item.id})")
                
                if not order_items_list:
                    raise Exception("Не удалось создать позиции заказа")
                
                # Создаем платеж
                payment_data = {
                    'order': order,
                    'payment_method': 'cash',
                    'payment_amount': final_amount,
                    'payment_status': 'pending',
                    'saved_payment_method': None
                }
                
                payment = Payment.objects.create(**payment_data)
                print(f"✅ Платеж создан (ID: {payment.id})")
                
                print(f"\n✅✅✅ ЗАКАЗ УСПЕШНО СОЗДАН! ID: {order.id}")
                return order
                
        except Exception as e:
            import traceback
            print(f"\n❌ ОШИБКА ПРИ СОЗДАНИИ ЗАКАЗА:")
            print(f"Тип: {type(e).__name__}")
            print(f"Сообщение: {str(e)}")
            print(f"Traceback:\n{traceback.format_exc()}")
            raise
            
    except Exception as e:
        import traceback
        print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА:")
        print(f"Тип: {type(e).__name__}")
        print(f"Сообщение: {str(e)}")
        print(f"Traceback:\n{traceback.format_exc()}")
        return None

if __name__ == '__main__':
    test_order_creation()

