"""
Дополнительные API endpoints для полного перевода сайта на API
Этот файл будет постепенно интегрирован в api.py
"""
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from datetime import timedelta, datetime
import json

from .models import (
    Role, UserProfile, UserAddress, Category, Brand, Supplier, Product, ProductSize,
    Tag, ProductTag, Favorite, Cart, CartItem, Order, OrderItem, Payment,
    Delivery, Promotion, ProductReview, SupportTicket, ActivityLog,
    SavedPaymentMethod, CardTransaction, BalanceTransaction, Receipt, ReceiptItem,
    OrganizationAccount, OrganizationTransaction
)
from .helpers import _user_is_admin, _user_is_manager, _log_activity
from .serializers import (
    UserProfileSerializer, UserAddressSerializer, ProductSerializer, 
    CartSerializer, CartItemSerializer, OrderSerializer, OrderItemSerializer
)


# ===== Permissions =====
class IsAdminOrReadOnly(permissions.BasePermission):
    """Только администратор может изменять"""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return _user_is_admin(request.user)


class IsManagerOrReadOnly(permissions.BasePermission):
    """Менеджер или администратор может изменять"""
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return _user_is_manager(request.user)


class IsOwnerOrAdmin(permissions.BasePermission):
    """Владелец ресурса или администратор"""
    def has_object_permission(self, request, view, obj):
        if _user_is_admin(request.user):
            return True
        if hasattr(obj, 'user'):
            return obj.user == request.user
        if hasattr(obj, 'cart') and hasattr(obj.cart, 'user'):
            return obj.cart.user == request.user
        return False


# ===== API для профиля пользователя =====
@method_decorator(csrf_exempt, name='dispatch')
class ProfileAPIView(APIView):
    """API для работы с профилем пользователя"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Получить профиль текущего пользователя"""
        try:
            profile = request.user.profile
            serializer = UserProfileSerializer(profile)
            return Response(serializer.data)
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)
            serializer = UserProfileSerializer(profile)
            return Response(serializer.data)

    def put(self, request):
        """Обновить профиль"""
        try:
            profile = request.user.profile
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)

        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()
        phone_number = request.data.get('phone_number', '').strip()
        birth_date_str = request.data.get('birth_date', '').strip()
        secret_word = request.data.get('secret_word', '').strip()

        if not first_name or not last_name:
            return Response({
                'success': False,
                'error': 'Имя и Фамилия обязательны'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Обновляем User
        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.save()

        # Обновляем профиль
        profile.phone_number = phone_number
        if birth_date_str:
            try:
                profile.birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    'success': False,
                    'error': 'Неверный формат даты рождения. Используйте ГГГГ-ММ-ДД.'
                }, status=status.HTTP_400_BAD_REQUEST)
        if secret_word:
            profile.secret_word = secret_word
        profile.save()

        serializer = UserProfileSerializer(profile)
        return Response({
            'success': True,
            'profile': serializer.data
        })


# ===== API для адресов =====
@method_decorator(csrf_exempt, name='dispatch')
class AddressAPIView(APIView):
    """API для работы с адресами пользователя"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Получить все адреса пользователя"""
        addresses = UserAddress.objects.filter(user=request.user)
        serializer = UserAddressSerializer(addresses, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Создать новый адрес"""
        address_title = request.data.get('address_title', '').strip()
        city_name = request.data.get('city_name', '').strip()
        street_name = request.data.get('street_name', '').strip()
        house_number = request.data.get('house_number', '').strip()
        apartment_number = request.data.get('apartment_number', '').strip()
        postal_code = request.data.get('postal_code', '').strip()
        is_primary = request.data.get('is_primary', False)

        if not all([city_name, street_name, house_number, postal_code]):
            return Response({
                'success': False,
                'error': 'Заполните все обязательные поля'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Если это основной адрес, снимаем флаг с других
        if is_primary:
            UserAddress.objects.filter(user=request.user).update(is_primary=False)

        address = UserAddress.objects.create(
            user=request.user,
            address_title=address_title or None,
            city_name=city_name,
            street_name=street_name,
            house_number=house_number,
            apartment_number=apartment_number or None,
            postal_code=postal_code,
            is_primary=is_primary
        )

        serializer = UserAddressSerializer(address)
        return Response({
            'success': True,
            'address': serializer.data
        }, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name='dispatch')
class AddressDetailAPIView(APIView):
    """API для работы с конкретным адресом"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, address_id):
        """Получить адрес"""
        address = get_object_or_404(UserAddress, id=address_id, user=request.user)
        serializer = UserAddressSerializer(address)
        return Response(serializer.data)

    def put(self, request, address_id):
        """Обновить адрес"""
        address = get_object_or_404(UserAddress, id=address_id, user=request.user)
        
        address.address_title = request.data.get('address_title', address.address_title).strip() or None
        address.city_name = request.data.get('city_name', address.city_name).strip()
        address.street_name = request.data.get('street_name', address.street_name).strip()
        address.house_number = request.data.get('house_number', address.house_number).strip()
        address.apartment_number = request.data.get('apartment_number', address.apartment_number).strip() or None
        address.postal_code = request.data.get('postal_code', address.postal_code).strip()
        is_primary = request.data.get('is_primary', address.is_primary)

        if not all([address.city_name, address.street_name, address.house_number, address.postal_code]):
            return Response({
                'success': False,
                'error': 'Заполните все обязательные поля'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Если это основной адрес, снимаем флаг с других
        if is_primary:
            UserAddress.objects.filter(user=request.user).exclude(id=address_id).update(is_primary=False)
        
        address.is_primary = is_primary
        address.save()

        serializer = UserAddressSerializer(address)
        return Response({
            'success': True,
            'address': serializer.data
        })

    def delete(self, request, address_id):
        """Удалить адрес"""
        address = get_object_or_404(UserAddress, id=address_id, user=request.user)
        address.delete()
        return Response({'success': True}, status=status.HTTP_204_NO_CONTENT)


# ===== API для корзины =====
@method_decorator(csrf_exempt, name='dispatch')
class CartAPIView(APIView):
    """API для работы с корзиной"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Получить корзину пользователя"""
        cart, _ = Cart.objects.get_or_create(user=request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    def post(self, request):
        """Добавить товар в корзину"""
        product_id = request.data.get('product_id')
        size_id = request.data.get('size_id')
        quantity = int(request.data.get('quantity', 1))

        if not product_id:
            return Response({
                'success': False,
                'error': 'product_id обязателен'
            }, status=status.HTTP_400_BAD_REQUEST)

        product = get_object_or_404(Product, id=product_id)
        
        if not product.is_available:
            return Response({
                'success': False,
                'error': 'Товар недоступен'
            }, status=status.HTTP_400_BAD_REQUEST)

        size = None
        if size_id:
            size = get_object_or_404(ProductSize, id=size_id, product=product)
            if size.size_stock < quantity:
                return Response({
                    'success': False,
                    'error': f'Недостаточно товара на складе. Доступно: {size.size_stock}'
                }, status=status.HTTP_400_BAD_REQUEST)
        elif product.stock_quantity < quantity:
            return Response({
                'success': False,
                'error': f'Недостаточно товара на складе. Доступно: {product.stock_quantity}'
            }, status=status.HTTP_400_BAD_REQUEST)

        cart, _ = Cart.objects.get_or_create(user=request.user)

        # Проверяем, есть ли уже такой товар с этим размером
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            size=size,
            defaults={'unit_price': product.final_price, 'quantity': quantity}
        )

        if not created:
            new_quantity = item.quantity + quantity
            if size and size.size_stock < new_quantity:
                return Response({
                    'success': False,
                    'error': f'Недостаточно товара на складе. Доступно: {size.size_stock}'
                }, status=status.HTTP_400_BAD_REQUEST)
            elif not size and product.stock_quantity < new_quantity:
                return Response({
                    'success': False,
                    'error': f'Недостаточно товара на складе. Доступно: {product.stock_quantity}'
                }, status=status.HTTP_400_BAD_REQUEST)
            item.quantity = new_quantity
            item.save()

        cart_serializer = CartSerializer(cart)
        return Response({
            'success': True,
            'cart': cart_serializer.data
        })


@method_decorator(csrf_exempt, name='dispatch')
class CartItemAPIView(APIView):
    """API для работы с элементами корзины"""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, item_id):
        """Обновить количество товара в корзине"""
        item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        new_quantity = int(request.data.get('quantity', 1))

        if new_quantity <= 0:
            return Response({
                'success': False,
                'error': 'Количество должно быть больше нуля'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Проверка количества на складе
        if item.size:
            if item.size.size_stock < new_quantity:
                return Response({
                    'success': False,
                    'error': f'Недостаточно товара на складе. Доступно: {item.size.size_stock}'
                }, status=status.HTTP_400_BAD_REQUEST)
        elif item.product.stock_quantity < new_quantity:
            return Response({
                'success': False,
                'error': f'Недостаточно товара на складе. Доступно: {item.product.stock_quantity}'
            }, status=status.HTTP_400_BAD_REQUEST)

        item.quantity = new_quantity
        item.save()

        cart_serializer = CartSerializer(item.cart)
        return Response({
            'success': True,
            'cart': cart_serializer.data
        })

    def delete(self, request, item_id):
        """Удалить товар из корзины"""
        item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        item.delete()
        return Response({'success': True}, status=status.HTTP_204_NO_CONTENT)

