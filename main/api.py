import base64
import binascii
import json

from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.exceptions import PermissionDenied, NotFound
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import (
    Role, UserProfile, UserAddress, Cart, CartItem, Order, OrderItem, Payment,
    Promotion, PromoUsage, SupportTicket, ActivityLog,
    SavedPaymentMethod, CardTransaction, BalanceTransaction, Receipt, ReceiptItem,
    OrganizationAccount, OrganizationTransaction, UserSettings,
    CourseCategory, Course, CourseFavorite, CoursePurchase, CourseReview,
)
from .serializers import (
    RoleSerializer, UserProfileSerializer, UserAddressSerializer,
    CartSerializer, CartItemSerializer, OrderSerializer, OrderItemSerializer,
    PaymentSerializer, PromotionSerializer,
    SupportTicketSerializer, ActivityLogSerializer, SavedPaymentMethodSerializer,
    CardTransactionSerializer, BalanceTransactionSerializer, ReceiptSerializer, ReceiptItemSerializer,
    OrganizationAccountSerializer, OrganizationTransactionSerializer,
    CourseCategorySerializer, CourseSerializer,
)
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models import Q, Sum, Count, Avg, Exists, OuterRef
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.conf import settings
from .helpers import _user_is_admin, _user_is_manager, _log_activity


def _decode_base64_image(data_string):
    if not data_string:
        raise ValueError('Пустые данные изображения')
    content_type = 'application/octet-stream'
    base64_data = data_string
    if data_string.startswith('data:') and ',' in data_string:
        header, base64_data = data_string.split(',', 1)
        if ';' in header:
            content_type = header.split(':', 1)[1].split(';', 1)[0]
    binary = base64.b64decode(base64_data)
    return binary, content_type


def _normalize_images_payload(payload):
    if payload is None:
        return None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return []
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []
    return payload


class ReadOnlyOrAuthenticated(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return True
        return request.user and request.user.is_authenticated


# ===== ViewSets =====
class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [ReadOnlyOrAuthenticated]


class UserProfileViewSet(viewsets.ModelViewSet):
    queryset = UserProfile.objects.select_related('user', 'role').all()
    serializer_class = UserProfileSerializer
    permission_classes = [ReadOnlyOrAuthenticated]


class UserAddressViewSet(viewsets.ModelViewSet):
    queryset = UserAddress.objects.select_related('user').all()
    serializer_class = UserAddressSerializer
    permission_classes = [ReadOnlyOrAuthenticated]


class CartViewSet(viewsets.ModelViewSet):
    queryset = Cart.objects.select_related('user').all()
    serializer_class = CartSerializer
    permission_classes = [ReadOnlyOrAuthenticated]


class CartItemViewSet(viewsets.ModelViewSet):
    queryset = CartItem.objects.select_related('cart', 'course').all()
    serializer_class = CartItemSerializer
    permission_classes = [ReadOnlyOrAuthenticated]


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related('user', 'address').all()
    serializer_class = OrderSerializer
    permission_classes = [ReadOnlyOrAuthenticated]

    # ОТКЛЮЧАЕМ создание заказов через ViewSet - только через OrderAPIView
    def create(self, request, *args, **kwargs):
        return Response({
            'error': 'Создание заказов через этот endpoint отключено. Используйте /api/orders/ (OrderAPIView)'
        }, status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    def update(self, request, *args, **kwargs):
        return Response({
            'error': 'Обновление заказов через этот endpoint отключено. Используйте /api/orders/<id>/ (OrderDetailAPIView)'
        }, status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    def destroy(self, request, *args, **kwargs):
        return Response({
            'error': 'Удаление заказов через этот endpoint отключено'
        }, status=status.HTTP_405_METHOD_NOT_ALLOWED)


class OrderItemViewSet(viewsets.ModelViewSet):
    queryset = OrderItem.objects.select_related('order', 'course').all()
    serializer_class = OrderItemSerializer
    permission_classes = [ReadOnlyOrAuthenticated]


class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.select_related('order').all()
    serializer_class = PaymentSerializer
    permission_classes = [ReadOnlyOrAuthenticated]


class PromotionViewSet(viewsets.ModelViewSet):
    queryset = Promotion.objects.all()
    serializer_class = PromotionSerializer
    permission_classes = [ReadOnlyOrAuthenticated]


class SupportTicketViewSet(viewsets.ModelViewSet):
    queryset = SupportTicket.objects.select_related('user').all()
    serializer_class = SupportTicketSerializer
    permission_classes = [ReadOnlyOrAuthenticated]


class ActivityLogViewSet(viewsets.ModelViewSet):
    queryset = ActivityLog.objects.select_related('user').all()
    serializer_class = ActivityLogSerializer
    permission_classes = [ReadOnlyOrAuthenticated]


@method_decorator(csrf_exempt, name='dispatch')
class CheckEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip()
        if not email:
            return Response({'exists': False, 'error': 'Email не указан'}, status=status.HTTP_400_BAD_REQUEST)
        exists = User.objects.filter(email=email).exists()
        return Response({'exists': exists})


@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip()
        password = request.data.get('password', '')

        if not email or not password:
            return Response({'success': False, 'error': 'Email и пароль обязательны'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            
            user = User.objects.filter(email=email).first()
            if not user:
                raise User.DoesNotExist()
            
            if not user.is_active:
                return Response({
                    'success': False, 
                    'error': 'Ваш аккаунт заблокирован. Обратитесь в поддержку: https://t.me/toshaplenka'
                }, status=status.HTTP_403_FORBIDDEN)
            
            try:
                profile = user.profile
                if profile.user_status == 'blocked':
                    return Response({
                        'success': False, 
                        'error': 'Ваш аккаунт заблокирован. Обратитесь в поддержку: https://t.me/toshaplenka'
                    }, status=status.HTTP_403_FORBIDDEN)
            except UserProfile.DoesNotExist:
               
                pass
            
            user = authenticate(request, username=user.username, password=password)
            if user is not None:
               
                if not user.is_active:
                    return Response({
                        'success': False, 
                        'error': 'Ваш аккаунт заблокирован. Обратитесь в поддержку: https://t.me/toshaplenka'
                    }, status=status.HTTP_403_FORBIDDEN)
                
                try:
                    profile = user.profile
                    if profile.user_status == 'blocked':
                        return Response({
                            'success': False, 
                            'error': 'Ваш аккаунт заблокирован. Обратитесь в поддержку: https://t.me/toshaplenka'
                        }, status=status.HTTP_403_FORBIDDEN)
                except UserProfile.DoesNotExist:
                    pass
                
                auth_login(request, user)
                return Response({
                    'success': True,
                    'message': 'Успешный вход',
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email
                    }
                })
            else:
                return Response({'success': False, 'error': 'Неверный пароль'}, status=status.HTTP_401_UNAUTHORIZED)
        except User.DoesNotExist:
            return Response({'success': False, 'error': 'Пользователь не найден'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            first_name = (request.data.get('first_name') or '').strip()
            last_name = (request.data.get('last_name') or '').strip()
            email = (request.data.get('email') or '').strip().lower()
            password = (request.data.get('password') or '').strip()
            password2 = (request.data.get('password2') or '').strip()
            phone_number = (request.data.get('phone_number') or '').strip()
            birth_date_str = (request.data.get('birth_date') or '').strip()
            secret_word = (request.data.get('secret_word') or '').strip()
            personal_data_consent = request.data.get('personal_data_consent', False)

        
            if not (first_name and last_name and email and password and password2):
                return Response({'success': False, 'error': 'Заполните все обязательные поля'}, status=status.HTTP_400_BAD_REQUEST)
            
            if User.objects.filter(email=email).exists():
                return Response({
                    'success': False, 
                    'error': 'Пользователь с таким email уже зарегистрирован. Используйте другой email или восстановите пароль.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
        
            if not personal_data_consent:
                return Response({'success': False, 'error': 'Необходимо согласие на обработку персональных данных'}, status=status.HTTP_400_BAD_REQUEST)
            if password != password2:
                return Response({'success': False, 'error': 'Пароли не совпадают'}, status=status.HTTP_400_BAD_REQUEST)
        
            if User.objects.filter(email=email).exists():
                return Response({
                    'success': False, 
                    'error': 'Пользователь с таким email уже зарегистрирован. Используйте другой email или восстановите пароль.'
                }, status=status.HTTP_400_BAD_REQUEST)

            username_base = email.split('@')[0]
            username = username_base
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{username_base}{counter}"
                counter += 1

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )

        
            try:
                user_role = Role.objects.get(id=1)
            except Role.DoesNotExist:
                # Базовая роль по умолчанию — USER
                user_role, _ = Role.objects.get_or_create(role_name='USER')

         
            profile_kwargs = {
                'user': user,
                'role': user_role,
                'full_name': f"{first_name} {last_name}".strip()
            }
            if phone_number:
                profile_kwargs['phone_number'] = phone_number
            if birth_date_str:
                try:
                    profile_kwargs['birth_date'] = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
                except Exception:
                    pass
            if secret_word:
                profile_kwargs['secret_word'] = secret_word

            UserProfile.objects.create(**profile_kwargs)

            return Response({'success': True, 'message': 'Регистрация успешна'}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """Восстановление пароля - проверяет все данные и устанавливает новый пароль"""
        try:
            import re
            phone = (request.data.get('phone') or '').strip()
            email = (request.data.get('email') or '').strip().lower()
            first_name = (request.data.get('first_name') or '').strip()
            last_name = (request.data.get('last_name') or '').strip()
            secret_word = (request.data.get('secret_word') or '').strip()
            new_password = (request.data.get('password') or '').strip()

            # Проверка обязательных полей
            if not (phone and email and first_name and last_name and secret_word and new_password):
                return Response({
                    'success': False,
                    'error': 'Заполните все поля, включая секретное слово'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Нормализация телефона
            normalized_phone = re.sub(r'\D', '', phone)
            if normalized_phone.startswith('8'):
                normalized_phone = '7' + normalized_phone[1:]
            if not normalized_phone.startswith('7') or len(normalized_phone) != 11:
                return Response({
                    'success': False,
                    'error': 'Неверный формат телефона'
                }, status=status.HTTP_400_BAD_REQUEST)

           
            user = User.objects.filter(email=email).first()
            if not user:
                return Response({
                    'success': False,
                    'error': 'Пользователь с таким email не найден'
                }, status=status.HTTP_404_NOT_FOUND)

           
            try:
                profile = user.profile
            except UserProfile.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Профиль пользователя не найден'
                }, status=status.HTTP_404_NOT_FOUND)

            # Проверка всех данных пользователя
            if (user.first_name.strip().lower() != first_name.strip().lower() or
                user.last_name.strip().lower() != last_name.strip().lower()):
                return Response({
                    'success': False,
                    'error': 'Неверные данные пользователя'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Проверка телефона
            profile_phone_raw = profile.phone_number or ''
            profile_phone = re.sub(r'\D', '', profile_phone_raw)
            if profile_phone.startswith('8'):
                profile_phone = '7' + profile_phone[1:]
            if not profile_phone.startswith('7') or len(profile_phone) != 11:
                profile_phone_normalized = ''
            else:
                profile_phone_normalized = profile_phone

            if profile_phone_normalized != normalized_phone:
                return Response({
                    'success': False,
                    'error': 'Неверный номер телефона'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Проверка секретного слова (ДО проверки пароля!)
            if not profile.secret_word:
                return Response({
                    'success': False,
                    'error': 'Секретное слово не установлено. Обратитесь в поддержку: https://t.me/toshaplenka'
                }, status=status.HTTP_400_BAD_REQUEST)

            if profile.secret_word.strip().lower() != secret_word.strip().lower():
                return Response({
                    'success': False,
                    'error': 'Неверное секретное слово'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Проверка силы пароля (только если все предыдущие проверки прошли)
            if not (re.search(r'[A-ZА-Я]', new_password) and
                    re.search(r'[a-zа-я]', new_password) and
                    re.search(r'\d', new_password) and
                    len(new_password) >= 8):
                return Response({
                    'success': False,
                    'error': 'Пароль должен содержать минимум 8 символов, буквы верхнего и нижнего регистра и цифры'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Установка нового пароля
            user.set_password(new_password)
            user.save()

            return Response({
                'success': True,
                'message': 'Пароль успешно изменен'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'success': False,
                'error': f'Ошибка при восстановлении пароля: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class VerifyResetDataView(APIView):
    """Проверка данных для восстановления пароля (без установки нового пароля)"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            import re
            phone = (request.data.get('phone') or '').strip()
            email = (request.data.get('email') or '').strip().lower()
            first_name = (request.data.get('first_name') or '').strip()
            last_name = (request.data.get('last_name') or '').strip()
            secret_word = (request.data.get('secret_word') or '').strip()

            # Проверка обязательных полей
            if not (phone and email and first_name and last_name and secret_word):
                return Response({
                    'success': False,
                    'error': 'Заполните все поля, включая секретное слово'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Нормализация телефона
            normalized_phone = re.sub(r'\D', '', phone)
            if normalized_phone.startswith('8'):
                normalized_phone = '7' + normalized_phone[1:]
            if not normalized_phone.startswith('7') or len(normalized_phone) != 11:
                return Response({
                    'success': False,
                    'error': 'Неверный формат телефона'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Поиск пользователя (используем filter().first() для обработки дубликатов)
            user = User.objects.filter(email=email).first()
            if not user:
                return Response({
                    'success': False,
                    'error': 'Пользователь с таким email не найден'
                }, status=status.HTTP_404_NOT_FOUND)

            # Проверка профиля
            try:
                profile = user.profile
            except UserProfile.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Профиль пользователя не найден'
                }, status=status.HTTP_404_NOT_FOUND)

            # Проверка всех данных пользователя
            if (user.first_name.strip().lower() != first_name.strip().lower() or
                user.last_name.strip().lower() != last_name.strip().lower()):
                return Response({
                    'success': False,
                    'error': 'Неверные имя или фамилия'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Проверка телефона
            profile_phone_raw = profile.phone_number or ''
            profile_phone = re.sub(r'\D', '', profile_phone_raw)
            if profile_phone.startswith('8'):
                profile_phone = '7' + profile_phone[1:]
            if not profile_phone.startswith('7') or len(profile_phone) != 11:
                profile_phone_normalized = ''
            else:
                profile_phone_normalized = profile_phone

            if profile_phone_normalized != normalized_phone:
                return Response({
                    'success': False,
                    'error': 'Неверный номер телефона'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Проверка секретного слова
            if not profile.secret_word:
                return Response({
                    'success': False,
                    'error': 'Секретное слово не установлено. Обратитесь в поддержку: https://t.me/toshaplenka'
                }, status=status.HTTP_400_BAD_REQUEST)

            if profile.secret_word.strip().lower() != secret_word.strip().lower():
                return Response({
                    'success': False,
                    'error': 'Неверное секретное слово'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Все проверки пройдены
            return Response({
                'success': True,
                'message': 'Данные проверены успешно'
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'success': False,
                'error': f'Ошибка при проверке данных: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===== Permissions для API =====
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


# ===== API для корзины (курсы) =====
@method_decorator(csrf_exempt, name='dispatch')
class CartAPIView(APIView):
    """API корзины (позиции = курсы)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        removed_items = []
        for item in cart.items.all():
            if not item.course:
                removed_items.append(item.id)
                item.delete()
        if removed_items:
            import logging
            logging.getLogger(__name__).info(f'Корзина пользователя {request.user.id}: удалено {len(removed_items)} несуществующих позиций')
        serializer = CartSerializer(cart)
        data = dict(serializer.data) if isinstance(serializer.data, dict) else serializer.data
        if isinstance(data, dict) and 'items' in data:
            total = sum(
                (Decimal(str(i.get('unit_price', 0))) * int(i.get('quantity', 0)) for i in data['items']),
                Decimal('0.00')
            )
            data['total_price'] = str(total.quantize(Decimal('0.01')))
        return Response(data)

    def post(self, request):
        course_id = request.data.get('course_id') or request.data.get('product_id')
        if not course_id:
            return Response({'success': False, 'error': 'course_id или product_id обязателен'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            course_id = int(course_id)
        except (ValueError, TypeError):
            return Response({'success': False, 'error': 'course_id должен быть числом'}, status=status.HTTP_400_BAD_REQUEST)
        course = get_object_or_404(Course, id=course_id, is_available=True)
        if CoursePurchase.objects.filter(user=request.user, course=course, status='paid').exists():
            return Response({'success': False, 'error': 'Вы уже купили этот курс. Нельзя купить его повторно.'}, status=status.HTTP_400_BAD_REQUEST)
        cart, _ = Cart.objects.get_or_create(user=request.user)
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            course=course,
            defaults={'unit_price': course.final_price, 'quantity': 1}
        )
        if not created:
            # Курс уже в корзине — только 1 шт, обновляем цену
            item.quantity = 1
            item.unit_price = course.final_price
            item.save()
        cart_serializer = CartSerializer(cart)
        return Response({'success': True, 'cart': cart_serializer.data})


@method_decorator(csrf_exempt, name='dispatch')
class CartItemAPIView(APIView):
    """API элементов корзины (курсы)"""
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, item_id):
        item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        # Курсы в корзине всегда в количестве 1
        if item.course_id:
            new_quantity = 1
        else:
            new_quantity = max(1, int(request.data.get('quantity', 1)))
            if getattr(item, 'size', None) and item.size.size_stock < new_quantity:
                return Response({
                    'success': False,
                    'error': f'Недостаточно на складе. Доступно: {item.size.size_stock}'
                }, status=status.HTTP_400_BAD_REQUEST)
            if getattr(item, 'product', None) and item.product.stock_quantity < new_quantity:
                return Response({
                    'success': False,
                    'error': f'Недостаточно на складе. Доступно: {item.product.stock_quantity}'
                }, status=status.HTTP_400_BAD_REQUEST)
        item.quantity = new_quantity
        item.save()
        return Response({'success': True, 'cart': CartSerializer(item.cart).data})

    def delete(self, request, item_id):
        """Удалить товар из корзины"""
        item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
        item.delete()
        return Response({'success': True}, status=status.HTTP_204_NO_CONTENT)


# ===== API для заказов =====
@method_decorator(csrf_exempt, name='dispatch')
class OrderAPIView(APIView):
    """API для работы с заказами"""
    permission_classes = [permissions.IsAuthenticated]

    def dispatch(self, request, *args, **kwargs):
        """Обычный dispatch - исключения обрабатывает Django"""
        return super().dispatch(request, *args, **kwargs)

    def handle_exception(self, exc):
        """Обработка исключений с детальным выводом"""
        import traceback
        error_trace = traceback.format_exc()
        
        # Определяем статус код
        if isinstance(exc, PermissionDenied):
            status_code = status.HTTP_403_FORBIDDEN
        elif isinstance(exc, NotFound):
            status_code = status.HTTP_404_NOT_FOUND
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        
        # Возвращаем детальную ошибку
        return Response({
            'success': False,
            'error': str(exc),
            'error_type': type(exc).__name__,
            'traceback': error_trace,
            'status_code': status_code
        }, status=status_code)

    def get(self, request):
        """Получить все заказы пользователя"""
        orders = Order.objects.filter(user=request.user).select_related('address').order_by('-created_at')
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Создать новый заказ (оформление заказа)"""
        import traceback
        import json
        from datetime import datetime
        import os
        import logging
        
        logger = logging.getLogger(__name__)
        
        try:
            # КРИТИЧЕСКАЯ ПРОВЕРКА: Пользователь должен быть авторизован
            if not request.user or not request.user.is_authenticated:
                logger.error("ОШИБКА: Пользователь не авторизован!")
                return Response({
                    'success': False,
                    'error': 'Вы должны быть авторизованы для создания заказа. Пожалуйста, войдите в систему.',
                    'requires_auth': True
                }, status=status.HTTP_401_UNAUTHORIZED)
            
            cart = Cart.objects.filter(user=request.user).first()
            
            # ПРОВЕРКА: Заказ не может быть создан без товаров в корзине
            if not cart:
                logger.error("ОШИБКА: Корзина не найдена!")
                raise ValueError('Корзина не найдена. Невозможно создать заказ без корзины.')
            
            cart_items_count = cart.items.count()
            
            if cart_items_count == 0:
                logger.error("ОШИБКА: Корзина пуста!")
                raise ValueError(f'Корзина пуста (товаров: {cart_items_count}). Невозможно создать заказ без товаров.')
            
            valid_items = cart.items.filter(course__isnull=False).count()
            if valid_items == 0:
                logger.error("ОШИБКА: В корзине нет валидных курсов!")
                raise ValueError('В корзине нет валидных курсов. Невозможно создать заказ.')
            
            address_id = request.data.get('address_id')
            saved_payment_id = request.data.get('saved_payment_id', '')
            payment_method = request.data.get('payment_method', 'sbp')
            card_number = request.data.get('card_number', '')
            card_holder_name = request.data.get('card_holder_name', '')
            expiry_month = request.data.get('expiry_month', '')
            expiry_year = request.data.get('expiry_year', '')
            save_card = request.data.get('save_card', False)

            # Онлайн-курсы: адрес доставки не обязателен
            address = None
            if address_id:
                try:
                    address_id = int(address_id)
                except (ValueError, TypeError):
                    return Response({
                        'success': False,
                        'error': 'Неверный формат адреса доставки'
                    }, status=status.HTTP_400_BAD_REQUEST)

            if address_id:
                try:
                    address = UserAddress.objects.get(id=address_id, user=request.user)
                except UserAddress.DoesNotExist:
                    return Response({
                        'success': False,
                        'error': f'Адрес доставки не найден (ID: {address_id})'
                    }, status=status.HTTP_404_NOT_FOUND)

            errors = []
            for item in cart.items.all():
                if not item.course:
                    errors.append(f"Курс в корзине не найден (позиция ID: {item.id})")
            if errors:
                return Response({'success': False, 'error': '; '.join(errors)}, status=status.HTTP_400_BAD_REQUEST)

            # Проверка промокода
            promo = None
            discount_amount = Decimal('0.00')
            try:
                cart_total = Decimal(str(cart.total_price())) if cart and cart.total_price() else Decimal('0.00')
            except (ValueError, TypeError, InvalidOperation):
                cart_total = Decimal('0.00')
            
            promo_code = request.data.get('promo_code', '').strip().upper()
            if promo_code:
                try:
                    promo = Promotion.objects.get(promo_code=promo_code, is_active=True)
                except Promotion.DoesNotExist:
                    return Response({
                        'success': False,
                        'error': 'Неверный промокод'
                    }, status=status.HTTP_400_BAD_REQUEST)
            
            if promo:
                today = timezone.now().date()
                # Проверка даты начала действия
                if promo.start_date and promo.start_date > today:
                    return Response({
                        'success': False,
                        'error': 'Промокод еще не действует'
                    }, status=status.HTTP_400_BAD_REQUEST)
                # Проверка даты окончания действия
                if promo.end_date and promo.end_date < today:
                    return Response({
                        'success': False,
                        'error': 'Промокод истек'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Проверяем, использовал ли пользователь уже этот промокод
                from .models import PromoUsage
                if PromoUsage.objects.filter(user=request.user, promotion=promo).exists():
                    return Response({
                        'success': False,
                        'error': 'Вы уже использовали этот промокод'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Рассчитываем скидку
                try:
                    discount_amount = (cart_total * (Decimal(str(promo.discount)) / Decimal('100'))).quantize(Decimal('0.01'))
                except (ValueError, TypeError, InvalidOperation):
                    discount_amount = Decimal('0.00')

            # Убеждаемся, что все значения Decimal
            try:
                cart_total = Decimal(str(cart_total)) if cart_total else Decimal('0.00')
                discount_amount = Decimal(str(discount_amount)) if discount_amount else Decimal('0.00')
            except (ValueError, TypeError, InvalidOperation):
                cart_total = Decimal('0.00')
                discount_amount = Decimal('0.00')
            
            delivery_cost = Decimal('0.00')
            subtotal_after_discount = (cart_total - discount_amount).quantize(Decimal('0.01'))
            pre_vat_amount = (subtotal_after_discount + delivery_cost).quantize(Decimal('0.01'))
            vat_rate = Decimal('20.00')
            vat_amount = (pre_vat_amount * vat_rate / Decimal('100')).quantize(Decimal('0.01'))
            amount_after_vat = (pre_vat_amount + vat_amount).quantize(Decimal('0.01'))
            tax_rate = Decimal('13.00')
            tax_amount = (amount_after_vat * tax_rate / Decimal('100')).quantize(Decimal('0.01'))
            final_amount = amount_after_vat.quantize(Decimal('0.01'))

            # Проверяем способ оплаты
            paid_from_balance = False
            if payment_method == 'balance':
                profile, _ = UserProfile.objects.get_or_create(user=request.user)
                if profile.balance < final_amount:
                    return Response({
                        'success': False,
                        'error': f'Недостаточно средств на балансе. Текущий баланс: {profile.balance} ₽, требуется: {final_amount} ₽'
                    }, status=status.HTTP_400_BAD_REQUEST)
                paid_from_balance = True

            # Вся логика оформления в транзакции
            try:
                for item in cart.items.all():
                    if not item.course:
                        return Response({
                            'success': False,
                            'error': f'Курс в корзине не найден (позиция: {item.id}). Обновите корзину.'
                        }, status=status.HTTP_400_BAD_REQUEST)
                
                with transaction.atomic():
                    if not cart:
                        raise ValueError('Корзина не найдена.')
                    cart_items = list(cart.items.select_related('course').all())
                    if not cart_items:
                        raise ValueError('Корзина пуста.')
                    valid_cart_items = [item for item in cart_items if item.course]
                    if not valid_cart_items:
                        raise ValueError('В корзине нет валидных курсов.')
                    cart_items = valid_cart_items
                    
                    try:
                        final_amount = Decimal(str(final_amount)) if final_amount else Decimal('0.00')
                        delivery_cost = Decimal(str(delivery_cost)) if delivery_cost else Decimal('0.00')
                        discount_amount = Decimal(str(discount_amount)) if discount_amount else Decimal('0.00')
                        vat_rate = Decimal(str(vat_rate)) if vat_rate else Decimal('20.00')
                        vat_amount = Decimal(str(vat_amount)) if vat_amount else Decimal('0.00')
                        tax_rate = Decimal(str(tax_rate)) if tax_rate else Decimal('13.00')
                        tax_amount = Decimal(str(tax_amount)) if tax_amount else Decimal('0.00')
                    except (ValueError, TypeError, InvalidOperation) as decimal_error:
                        return Response({
                            'success': False,
                            'error': f'Ошибка расчета суммы заказа: {str(decimal_error)}'
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    # Проверяем, что пользователь аутентифицирован
                    if not request.user or not request.user.is_authenticated:
                        return Response({
                            'success': False,
                            'error': 'Пользователь не аутентифицирован'
                        }, status=status.HTTP_401_UNAUTHORIZED)
                    
                    # КРИТИЧЕСКАЯ ПРОВЕРКА: Заказ НЕ создается без товаров!
                    # Проверяем ДО создания заказа, что есть товары
                    if not cart_items or len(cart_items) == 0:
                        raise ValueError(f'КРИТИЧЕСКАЯ ОШИБКА: Список товаров для создания заказа пуст. Невозможно создать заказ без товаров. Данные запроса: {request.data}')
                    
                    # Подготавливаем список курсов для заказа
                    order_items_prepared = []
                    for item in cart_items:
                        if not item.course:
                            raise ValueError(f'Курс в корзине не найден (позиция: {item.id}).')
                        try:
                            unit_price = Decimal(str(item.unit_price)) if item.unit_price else Decimal('0.00')
                        except (ValueError, TypeError, InvalidOperation):
                            unit_price = Decimal('0.00')
                        order_items_prepared.append({
                            'course': item.course,
                            'quantity': item.quantity,
                            'unit_price': unit_price
                        })
                    if not order_items_prepared:
                        raise ValueError('Нет позиций для заказа.')
                    if not request.user or not request.user.is_authenticated:
                        raise ValueError('Пользователь не авторизован.')
                    created_order_items = order_items_prepared
                    
                    # ТОЛЬКО ТЕПЕРЬ создаем заказ - после проверки всех товаров
                    
                    order_data = {
                        'user': request.user,
                        'address': address,
                        'total_amount': final_amount,
                        'delivery_cost': delivery_cost,
                        'discount_amount': discount_amount,
                        'vat_rate': vat_rate,
                        'tax_rate': tax_rate,
                        'paid_from_balance': paid_from_balance,
                        'order_status': 'delivered'
                    }
                    if promo:
                        order_data['promo_code'] = promo
                    
                    try:
                        order = Order.objects.create(**order_data)
                        order.refresh_from_db()
                        
                        if not order.id:
                            raise ValueError("ID заказа не был установлен после создания")
                        
                        if not order.user or order.user_id != request.user.id:
                            logger.error("ОШИБКА: user не установлен правильно в заказе!")
                            raise ValueError('Ошибка: пользователь не установлен в заказе')
                    except Exception as create_error:
                        import traceback
                        error_trace = traceback.format_exc()
                        logger.error(f"ОШИБКА при создании заказа: {str(create_error)}")
                        logger.error(f"Traceback: {error_trace}")
                        raise ValueError(f'Ошибка при создании заказа: {str(create_error)}')
                    
                    # ЖЕСТКАЯ ПРОВЕРКА ПЕРЕД СОЗДАНИЕМ ТОВАРОВ
                    if not created_order_items or len(created_order_items) == 0:
                        logger.error("КРИТИЧЕСКАЯ ОШИБКА: Нет товаров для создания!")
                        raise ValueError('КРИТИЧЕСКАЯ ОШИБКА: Нет товаров для создания. Невозможно создать заказ без товаров.')
                    
                    created_order_items_objects = []
                    cp_method = 'balance' if payment_method == 'balance' else ('card' if payment_method == 'card' else 'sbp')
                    for item_data in created_order_items:
                        order_item = OrderItem.objects.create(
                            order=order,
                            course=item_data['course'],
                            quantity=item_data['quantity'],
                            unit_price=item_data['unit_price'],
                        )
                        created_order_items_objects.append(order_item)
                        existing_count = CoursePurchase.objects.filter(
                            user=request.user, course=item_data['course'], status='paid'
                        ).count()
                        to_create = max(0, item_data['quantity'] - existing_count)
                        for _ in range(to_create):
                            CoursePurchase.objects.create(
                                user=request.user,
                                course=item_data['course'],
                                amount=item_data['unit_price'],
                                status='paid',
                                payment_method=cp_method,
                            )
                    if not created_order_items_objects:
                        raise ValueError('Не удалось создать позиции заказа.')
                    order.refresh_from_db()
                    order_items_from_db = list(OrderItem.objects.filter(order=order).select_related('course').all())
                    if len(order_items_from_db) == 0:
                        logger.error("КРИТИЧЕСКАЯ ОШИБКА: OrderItem не найдены в БД!")
                        raise ValueError('КРИТИЧЕСКАЯ ОШИБКА: OrderItem не найдены в БД. Невозможно создать заказ без товаров.')
                    
                    # ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: Проверяем, что user установлен
                    if not order.user or order.user_id != request.user.id:
                        logger.error("КРИТИЧЕСКАЯ ОШИБКА: user не установлен в заказе!")
                        raise ValueError('КРИТИЧЕСКАЯ ОШИБКА: Пользователь не установлен в заказе.')

                    # Обработка способа оплаты
                    saved_payment = None
                    payment_method_type = 'cash'
                    payment_status = 'pending'
                    
                    if payment_method == 'cash' or payment_method == 'sbp':
                        payment_method_type = 'sbp' if payment_method == 'sbp' else 'cash'
                        payment_status = 'pending'
                    elif payment_method == 'balance':
                        payment_method_type = 'balance'
                        payment_status = 'paid'
                        
                        profile, _ = UserProfile.objects.select_for_update().get_or_create(user=request.user)
                        if profile.balance < final_amount:
                            raise ValueError(f'Недостаточно средств на балансе. Текущий баланс: {profile.balance} ₽, требуется: {final_amount} ₽')
                        balance_before = profile.balance
                        profile.balance -= final_amount
                        profile.save()
                        
                        BalanceTransaction.objects.create(
                            user=request.user,
                            transaction_type='order_payment',
                            amount=final_amount,
                            description=f'Оплата заказа #{order.id}',
                            order=order,
                            status='completed'
                        )
                    elif payment_method == 'card':
                        payment_status = 'paid'
                        if saved_payment_id:
                            try:
                                saved_payment_id_int = int(saved_payment_id)
                                saved_payment = SavedPaymentMethod.objects.select_for_update().get(id=saved_payment_id_int, user=request.user)
                            except (ValueError, TypeError):
                                raise ValueError('Неверный формат ID карты')
                            except SavedPaymentMethod.DoesNotExist:
                                raise ValueError('Выбранная карта не найдена')
                            payment_method_type = saved_payment.card_type or 'card'
                            if saved_payment.balance < final_amount:
                                raise ValueError(f'Недостаточно средств на выбранной карте. Баланс карты: {saved_payment.balance} ₽, требуется: {final_amount} ₽')
                            saved_payment.balance -= final_amount
                            saved_payment.save()
                            CardTransaction.objects.create(
                                saved_payment_method=saved_payment,
                                transaction_type='withdrawal',
                                amount=final_amount,
                                description=f'Оплата заказа #{order.id}',
                                status='completed'
                            )
                        elif card_number and card_holder_name and expiry_month and expiry_year:
                            payment_method_type = 'visa' if card_number.startswith('4') else 'mastercard' if card_number.startswith('5') else 'card'
                            if save_card:
                                card_type = payment_method_type
                                card_last_4 = card_number[-4:] if len(card_number) >= 4 else card_number
                                is_default = not SavedPaymentMethod.objects.filter(user=request.user).exists()
                                saved_payment = SavedPaymentMethod.objects.create(
                                    user=request.user,
                                    card_number=card_last_4,
                                    card_holder_name=card_holder_name,
                                    expiry_month=expiry_month,
                                    expiry_year=expiry_year,
                                    card_type=card_type,
                                    is_default=is_default
                                )
                                if saved_payment.balance < final_amount:
                                    raise ValueError(f'Недостаточно средств на карте. Баланс карты: {saved_payment.balance} ₽, требуется: {final_amount} ₽')
                                saved_payment.balance -= final_amount
                                saved_payment.save()
                                CardTransaction.objects.create(
                                    saved_payment_method=saved_payment,
                                    transaction_type='withdrawal',
                                    amount=final_amount,
                                    description=f'Оплата заказа #{order.id}',
                                    status='completed'
                                )
                            else:
                                card_type = payment_method_type
                                card_last_4 = card_number[-4:] if len(card_number) >= 4 else card_number
                                temp_card = SavedPaymentMethod.objects.create(
                                    user=request.user,
                                    card_number=card_last_4,
                                    card_holder_name=card_holder_name,
                                    expiry_month=expiry_month,
                                    expiry_year=expiry_year,
                                    card_type=card_type,
                                    is_default=False
                                )
                                if temp_card.balance < final_amount:
                                    raise ValueError(f'Недостаточно средств на карте. Баланс карты: {temp_card.balance} ₽, требуется: {final_amount} ₽')
                                temp_card.balance -= final_amount
                                temp_card.save()
                                CardTransaction.objects.create(
                                    saved_payment_method=temp_card,
                                    transaction_type='withdrawal',
                                    amount=final_amount,
                                    description=f'Оплата заказа #{order.id}',
                                    status='completed'
                                )
                                saved_payment = temp_card
                        else:
                            payment_method_type = 'sbp'
                            payment_status = 'pending'
                    
                    # Создаем запись о платеже
                    payment_data = {
                        'order': order,
                        'payment_method': payment_method_type,
                        'payment_amount': final_amount,
                        'payment_status': payment_status,
                        'saved_payment_method': saved_payment
                    }
                    if promo:
                        payment_data['promo_code'] = promo
                    
                    try:
                        payment = Payment.objects.create(**payment_data)
                    except Exception as payment_error:
                        # Не вызываем order.delete() — транзакция уже failed, rollback отменит заказ
                        raise ValueError(f'Ошибка при создании платежа: {str(payment_error)}')

                    if payment_status == 'paid' and order.order_status != 'delivered':
                        order.order_status = 'delivered'
                        order.save(update_fields=['order_status'])
                    
                    # Отмечаем промокод как использованный
                    if promo:
                        PromoUsage.objects.get_or_create(
                            user=request.user,
                            promotion=promo,
                            defaults={'order': order}
                        )
                    
                    # Переводим средства на счет организации (при оплате картой или с баланса)
                    if payment_status == 'paid' and payment_method_type not in ('cash', 'sbp'):
                        org_account = OrganizationAccount.get_account()
                        # Блокируем строку счёта для обновления в рамках транзакции
                        org_account = OrganizationAccount.objects.select_for_update().get(pk=org_account.pk)
                        balance_before = org_account.balance
                        tax_reserve_before = org_account.tax_reserve
                        org_account.balance += final_amount
                        org_account.tax_reserve += tax_amount
                        org_account.save()
                        OrganizationTransaction.objects.create(
                            organization_account=org_account,
                            transaction_type='order_payment',
                            amount=final_amount,
                            description=f'Поступление от заказа #{order.id}',
                            order=order,
                            created_by=request.user,
                            balance_before=balance_before,
                            balance_after=org_account.balance,
                            tax_reserve_before=tax_reserve_before,
                            tax_reserve_after=org_account.tax_reserve,
                        )

                    order_items_list = created_order_items_objects
                    
                    # Очищаем корзину только после успешного создания всех товаров
                    if cart:
                        cart.items.all().delete()

                    # Формируем чек
                    try:
                        if not order_items_list or len(order_items_list) == 0:
                            logger.error("ОШИБКА: order_items_list пуст при создании чека!")
                        else:
                            delivery_vat = (delivery_cost * vat_rate / Decimal('100')).quantize(Decimal('0.01'))
                            receipt_total = Decimal(str(final_amount)).quantize(Decimal('0.01'))
                            receipt_subtotal = Decimal(str(cart_total)) if cart_total else Decimal('0.00')
                            receipt_subtotal = receipt_subtotal.quantize(Decimal('0.01'))
                            receipt_delivery = Decimal(str(delivery_cost)).quantize(Decimal('0.01'))
                            receipt_discount = Decimal(str(discount_amount)).quantize(Decimal('0.01'))
                            receipt_vat = Decimal(str(vat_amount)).quantize(Decimal('0.01'))
                            
                            receipt_payment_method = 'card'
                            if payment_method_type == 'cash':
                                receipt_payment_method = 'cash'
                            elif payment_method_type == 'sbp':
                                receipt_payment_method = 'sbp'
                            elif payment_method_type == 'balance':
                                receipt_payment_method = 'balance'
                            elif payment_method_type in ['card', 'visa', 'mastercard']:
                                receipt_payment_method = 'card'
                            
                            receipt = Receipt.objects.create(
                                user=request.user,
                                order=order,
                                status='executed',
                                total_amount=receipt_total,
                                subtotal=receipt_subtotal,
                                delivery_cost=receipt_delivery,
                                discount_amount=receipt_discount,
                                vat_rate=vat_rate,
                                payment_method=receipt_payment_method
                            )
                            for item in order_items_list:
                                unit_price = Decimal(str(item.unit_price)).quantize(Decimal('0.01'))
                                quantity = int(item.quantity)
                                article = str(item.course.id) if item.course else ''
                                ReceiptItem.objects.create(
                                    receipt=receipt,
                                    course=item.course,
                                    article=article,
                                    quantity=quantity,
                                    unit_price=unit_price,
                                )
                            if receipt_delivery and receipt_delivery > 0:
                                ReceiptItem.objects.create(
                                    receipt=receipt,
                                    course=None,
                                    line_description='Доставка',
                                    article='DELIVERY',
                                    quantity=1,
                                    unit_price=receipt_delivery,
                                )
                    except Exception as receipt_error:
                        logger.error(f"ОШИБКА при создании чека: {str(receipt_error)}")
                        # НЕ прерываем выполнение - чек не критичен, заказ уже создан
                    
                    try:
                        _log_activity(request.user, 'create', f'order_{order.id}', f'Создан заказ на сумму {final_amount} ₽', request)
                    except Exception:
                        pass
                    
                    # Убеждаемся, что ID заказа доступен
                    if not order.id:
                        order.refresh_from_db()
                    
                    try:
                        # Обновляем заказ из БД с prefetch для items
                        order.refresh_from_db()
                        order = Order.objects.prefetch_related('items', 'items__course').get(id=order.id)
                        logger.error(f"Заказ обновлен из БД: id={order.id}, user_id={order.user_id if order.user else 'None'}")
                        logger.error(f"Количество items в заказе (prefetch): {order.items.count()}")
                        
                        serializer = OrderSerializer(order)
                        order_data = serializer.data
                        if 'id' not in order_data:
                            order_data['id'] = order.id
                        
                        order_data['items_count'] = len(order_data.get('items', []))
                    except Exception as ser_error:
                        logger.error(f"Ошибка при сериализации заказа: {ser_error}")
                        order_data = {
                            'id': order.id,
                            'total_amount': str(order.total_amount),
                            'order_status': order.order_status,
                            'created_at': order.created_at.isoformat() if order.created_at else None,
                            'items': [],
                            'items_count': 0
                        }
                    
                    order_id = order.id
                    if not order_id:
                        order.refresh_from_db()
                        order_id = order.id
                    
                    if not order_id:
                        raise ValueError("Не удалось получить ID созданного заказа")
                    
                    # ФИНАЛЬНАЯ ПРОВЕРКА: Проверяем количество товаров в заказе перед возвратом
                    order.refresh_from_db()
                    final_check_items = OrderItem.objects.filter(order=order).count()
                    if final_check_items == 0:
                        logger.error("КРИТИЧЕСКАЯ ОШИБКА: Заказ создан без товаров!")
                        raise ValueError('КРИТИЧЕСКАЯ ОШИБКА: Заказ создан без товаров.')
                    
                    if not order.user or order.user_id != request.user.id:
                        logger.error("КРИТИЧЕСКАЯ ОШИБКА: user не установлен!")
                        raise ValueError('КРИТИЧЕСКАЯ ОШИБКА: Заказ создан без пользователя.')
                    
                    return Response({
                        'success': True,
                        'order': order_data,
                        'order_id': order_id
                    }, status=status.HTTP_201_CREATED)
            except ValueError as e:
                logger.error(f"ОШИБКА ValueError при создании заказа: {str(e)}")
                import traceback
                error_trace = traceback.format_exc()
                return Response({
                    'success': False,
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'traceback': error_trace if settings.DEBUG else None,
                    'request_data': dict(request.data) if settings.DEBUG else None
                }, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logger.error(f"ОШИБКА Exception при создании заказа: {str(e)}")
                logger.error(f"Traceback: {error_trace}")
                return Response({
                    'success': False,
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'traceback': error_trace if settings.DEBUG else None
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except ValueError as e:
            # ValueError выбрасывается при отсутствии товаров - показываем детальную ошибку
            import traceback
            error_trace = traceback.format_exc()
            logger.error("=" * 80)
            logger.error("ОШИБКА ValueError ВНЕ ТРАНЗАКЦИИ")
            logger.error("=" * 80)
            logger.error(f"Ошибка: {str(e)}")
            logger.error(f"Тип: {type(e).__name__}")
            logger.error(f"Traceback:\n{error_trace}")
            logger.error(f"Данные запроса: {request.data}")
            logger.error("=" * 80)
            return Response({
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__,
                'traceback': error_trace if settings.DEBUG else None,
                'request_data': dict(request.data) if settings.DEBUG else None
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error("=" * 80)
            logger.error("ОШИБКА Exception ВНЕ ТРАНЗАКЦИИ")
            logger.error("=" * 80)
            logger.error(f"Ошибка: {str(e)}")
            logger.error(f"Тип: {type(e).__name__}")
            logger.error(f"Traceback:\n{error_trace}")
            logger.error(f"Данные запроса: {request.data}")
            logger.error("=" * 80)
            return Response({
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__,
                'traceback': error_trace if settings.DEBUG else None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class OrderDetailAPIView(APIView):
    """API для работы с конкретным заказом"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        """Получить заказ"""
        order = get_object_or_404(Order, id=order_id, user=request.user)
        serializer = OrderSerializer(order)
        return Response(serializer.data)

    def post(self, request, order_id):
        """Отменить заказ"""
        order = get_object_or_404(Order, id=order_id, user=request.user)
        
        if not order.can_be_cancelled:
            return Response({
                'success': False,
                'error': 'Заказ нельзя отменить'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # Проверяем, были ли средства переведены на счет организации
                org_payment_transaction = OrganizationTransaction.objects.filter(
                    order=order,
                    transaction_type='order_payment'
                ).first()
                
                # Если заказ был в статусе "processing" (в обработке) и средства НЕ были переведены на счет организации
                # (т.е. оплата была наличными и заказ не был доставлен) - ничего не начисляется и не списывается
                if order.order_status == 'processing' and not org_payment_transaction:
                    # Просто отменяем заказ, не трогая счет организации
                    order.order_status = 'cancelled'
                    order.can_be_cancelled = False
                    order.save()

                # Возвращаем товары на склад (только для товаров с размерами/остатками; для курсов — не требуется)
                for item in order.items.all():
                    if getattr(item, 'size', None):
                        item.size.size_stock += item.quantity
                        item.size.save()
                    if getattr(item, 'product', None):
                        item.product.stock_quantity += item.quantity
                        item.product.save()

                    # Возвращаем деньги клиенту (если заказ был оплачен НЕ наличными)
                    # Для наличных платежей при отмене в статусе "processing" ничего не возвращаем
                    payment = order.payment_set.filter(payment_status='paid').first()
                    if not payment:
                        payment = order.payment_set.first()
                    is_cash = payment and (payment.payment_method == 'cash' or (payment.payment_status == 'pending' and payment.payment_method not in ['balance', 'card', 'visa', 'mastercard']))
                    was_paid = order.paid_from_balance or (payment and payment.payment_status == 'paid')
                    
                    # Возвращаем деньги клиенту если:
                    # 1. Заказ был оплачен НЕ наличными И средства были переведены на счет организации И заказ НЕ был доставлен
                    # 2. Если заказ был доставлен - деньги остаются на счете организации (не возвращаем)
                    should_refund = False
                    if was_paid and not is_cash:
                        # Не наличные - возвращаем если средства были переведены и заказ не был доставлен
                        should_refund = org_payment_transaction and not was_delivered
                    # Наличные - не возвращаем, деньги остаются на счете организации
                    
                    if should_refund:
                        if order.paid_from_balance:
                            profile, _ = UserProfile.objects.select_for_update().get_or_create(user=order.user)
                            balance_before = profile.balance
                            profile.balance += order.total_amount
                            profile.save()
                            BalanceTransaction.objects.create(
                                user=order.user,
                                transaction_type='order_refund',
                                amount=order.total_amount,
                                description=f'Возврат средств по заказу #{order.id}',
                                order=order,
                                status='completed'
                            )
                        elif payment and payment.saved_payment_method:
                            try:
                                card = payment.saved_payment_method
                                card.balance += order.total_amount
                                card.save()
                                CardTransaction.objects.create(
                                    saved_payment_method=card,
                                    transaction_type='deposit',
                                    amount=order.total_amount,
                                    description=f'Возврат средств по заказу #{order.id}',
                                    status='completed'
                                )
                            except Exception:
                                profile, _ = UserProfile.objects.select_for_update().get_or_create(user=order.user)
                                balance_before = profile.balance
                                profile.balance += order.total_amount
                                profile.save()
                                BalanceTransaction.objects.create(
                                    user=order.user,
                                    transaction_type='order_refund',
                                    amount=order.total_amount,
                                    description=f'Возврат средств по заказу #{order.id} (карта недоступна)',
                                    order=order,
                                    status='completed'
                                )
                        else:
                            profile, _ = UserProfile.objects.select_for_update().get_or_create(user=order.user)
                            balance_before = profile.balance
                            profile.balance += order.total_amount
                            profile.save()
                            BalanceTransaction.objects.create(
                                user=order.user,
                                transaction_type='order_refund',
                                amount=order.total_amount,
                                description=f'Возврат средств по заказу #{order.id}',
                                order=order,
                                status='completed'
                            )
                    
                    _log_activity(request.user, 'update', f'order_{order.id}', 'Заказ отменен пользователем', request)
                    serializer = OrderSerializer(order)
                    return Response({
                        'success': True,
                        'order': serializer.data
                    })
                
                # Логика отмены заказа для заказов в других статусах или если средства были переведены
                order.order_status = 'cancelled'
                order.can_be_cancelled = False
                order.save()

                # Возвращаем товары на склад (только для товаров; для курсов — не требуется)
                for item in order.items.all():
                    if getattr(item, 'size', None):
                        item.size.size_stock += item.quantity
                        item.size.save()
                    if getattr(item, 'product', None):
                        item.product.stock_quantity += item.quantity
                        item.product.save()
                
                # Проверяем, был ли заказ доставлен
                # Если заказ был доставлен - средства остаются на счете организации, даже при отмене
                was_delivered = order.order_status == 'delivered'
                
                # Возвращаем средства со счета организации только если:
                # 1. Средства были переведены на счет организации
                # 2. Заказ НЕ был доставлен (если был доставлен - деньги остаются на счете)
                if org_payment_transaction and not was_delivered:
                    org_account = OrganizationAccount.get_account()
                    balance_before = org_account.balance
                    tax_reserve_before = org_account.tax_reserve
                    
                    # Проверяем, что на счете достаточно средств для возврата
                    if org_account.balance < order.total_amount:
                        raise ValueError(f"Недостаточно средств на счете организации для возврата. Баланс: {org_account.balance} ₽, требуется: {order.total_amount} ₽")
                    
                    # Возвращаем сумму заказа
                    org_account.balance -= order.total_amount
                    
                    # Возвращаем налог из резерва
                    if org_account.tax_reserve >= order.tax_amount:
                        org_account.tax_reserve -= order.tax_amount
                    else:
                        # Если резерв меньше суммы налога, возвращаем что есть
                        org_account.tax_reserve = Decimal('0.00')
                    
                    org_account.save()
                    
                    OrganizationTransaction.objects.create(
                        organization_account=org_account,
                        transaction_type='order_refund',
                        amount=order.total_amount,
                        description=f'Возврат средств по отмене заказа #{order.id}',
                        order=order,
                        created_by=request.user,
                        balance_before=balance_before,
                        balance_after=org_account.balance,
                        tax_reserve_before=tax_reserve_before,
                        tax_reserve_after=org_account.tax_reserve,
                    )

                # Возвращаем средства пользователю (если заказ был оплачен)
                payment = order.payment_set.filter(payment_status='paid').first()
                was_paid = order.paid_from_balance or (payment and payment.payment_status == 'paid')
                
                if was_paid:
                    # Если оплата была с баланса - возвращаем на баланс
                    if order.paid_from_balance:
                        profile, _ = UserProfile.objects.select_for_update().get_or_create(user=order.user)
                        balance_before = profile.balance
                        profile.balance += order.total_amount
                        profile.save()
                        
                        BalanceTransaction.objects.create(
                            user=order.user,
                            transaction_type='order_refund',
                            amount=order.total_amount,
                            description=f'Возврат средств по заказу #{order.id}',
                            order=order,
                            status='completed'
                        )
                    # Если оплата была картой - возвращаем на карту
                    elif payment and payment.saved_payment_method:
                        try:
                            card = payment.saved_payment_method
                            card.balance += order.total_amount
                            card.save()
                            
                            CardTransaction.objects.create(
                                saved_payment_method=card,
                                transaction_type='deposit',
                                amount=order.total_amount,
                                description=f'Возврат средств по заказу #{order.id}',
                                status='completed'
                            )
                        except Exception:
                            # Если не удалось вернуть на карту, возвращаем на баланс
                            profile, _ = UserProfile.objects.select_for_update().get_or_create(user=order.user)
                            balance_before = profile.balance
                            profile.balance += order.total_amount
                            profile.save()
                            
                            BalanceTransaction.objects.create(
                                user=order.user,
                                transaction_type='order_refund',
                                amount=order.total_amount,
                                description=f'Возврат средств по заказу #{order.id} (карта недоступна)',
                                order=order,
                                status='completed'
                            )
                    # Если оплата была наличными или другим способом - возвращаем на баланс
                    else:
                        profile, _ = UserProfile.objects.select_for_update().get_or_create(user=order.user)
                        balance_before = profile.balance
                        profile.balance += order.total_amount
                        profile.save()
                        
                        BalanceTransaction.objects.create(
                            user=order.user,
                            transaction_type='order_refund',
                            amount=order.total_amount,
                            description=f'Возврат средств по заказу #{order.id}',
                            order=order,
                                status='completed'
                            )

                _log_activity(request.user, 'update', f'order_{order.id}', 'Заказ отменен пользователем', request)
                
                serializer = OrderSerializer(order)
                return Response({
                    'success': True,
                    'order': serializer.data
                })
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Ошибка при отмене заказа: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===== API для карт и платежей =====
@method_decorator(csrf_exempt, name='dispatch')
class PaymentMethodAPIView(APIView):
    """API для работы с сохраненными способами оплаты"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Получить все сохраненные карты пользователя"""
        cards = SavedPaymentMethod.objects.filter(user=request.user)
        serializer = SavedPaymentMethodSerializer(cards, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Добавить новую карту"""
        card_number = request.data.get('card_number', '').strip()
        card_holder_name = request.data.get('card_holder_name', '').strip()
        expiry_month = request.data.get('expiry_month', '').strip()
        expiry_year = request.data.get('expiry_year', '').strip()

        if not all([card_number, card_holder_name, expiry_month, expiry_year]):
            return Response({
                'success': False,
                'error': 'Заполните все поля карты'
            }, status=status.HTTP_400_BAD_REQUEST)

        card_type = 'visa' if card_number.startswith('4') else 'mastercard' if card_number.startswith('5') else 'card'
        card_last_4 = card_number[-4:] if len(card_number) >= 4 else card_number
        is_default = not SavedPaymentMethod.objects.filter(user=request.user).exists()

        card = SavedPaymentMethod.objects.create(
            user=request.user,
            card_number=card_last_4,
            card_holder_name=card_holder_name,
            expiry_month=expiry_month,
            expiry_year=expiry_year,
            card_type=card_type,
            is_default=is_default
        )

        serializer = SavedPaymentMethodSerializer(card)
        return Response({
            'success': True,
            'card': serializer.data
        }, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name='dispatch')
class PaymentMethodDetailAPIView(APIView):
    """API для работы с конкретной картой"""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, card_id):
        """Удалить карту"""
        card = get_object_or_404(SavedPaymentMethod, id=card_id, user=request.user)
        card.delete()
        return Response({'success': True}, status=status.HTTP_204_NO_CONTENT)

    def post(self, request, card_id):
        """Установить карту как основную"""
        SavedPaymentMethod.objects.filter(user=request.user).update(is_default=False)
        card = get_object_or_404(SavedPaymentMethod, id=card_id, user=request.user)
        card.is_default = True
        card.save()
        serializer = SavedPaymentMethodSerializer(card)
        return Response({
            'success': True,
            'card': serializer.data
        })


# ===== API для баланса =====
@method_decorator(csrf_exempt, name='dispatch')
class BalanceAPIView(APIView):
    """API для работы с балансом пользователя"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Получить баланс и транзакции"""
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        transactions = BalanceTransaction.objects.filter(user=request.user).order_by('-created_at')[:20]
        
        return Response({
            'balance': str(profile.balance),
            'transactions': BalanceTransactionSerializer(transactions, many=True).data
        })

    def post(self, request):
        """Пополнить баланс с карты"""
        card_id = request.data.get('card_id')
        amount_str = request.data.get('amount', '0')

        if not card_id:
            return Response({
                'success': False,
                'error': 'Выберите карту'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(amount_str)
        except (ValueError, InvalidOperation):
            return Response({
                'success': False,
                'error': 'Неверная сумма'
            }, status=status.HTTP_400_BAD_REQUEST)

        if amount <= 0:
            return Response({
                'success': False,
                'error': 'Сумма должна быть больше нуля'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            card = SavedPaymentMethod.objects.select_for_update().get(id=card_id, user=request.user)
            if card.balance < amount:
                return Response({
                    'success': False,
                    'error': f'Недостаточно средств на карте. Баланс карты: {card.balance} ₽'
                }, status=status.HTTP_400_BAD_REQUEST)

            with transaction.atomic():
                card.balance -= amount
                card.save()

                profile, _ = UserProfile.objects.select_for_update().get_or_create(user=request.user)
                balance_before = profile.balance
                profile.balance += amount
                profile.save()

                BalanceTransaction.objects.create(
                    user=request.user,
                    transaction_type='deposit',
                    amount=amount,
                    description=f'Пополнение баланса с карты {card.mask_card_number()}',
                    status='completed'
                )

                CardTransaction.objects.create(
                    saved_payment_method=card,
                    transaction_type='withdrawal',
                    amount=amount,
                    description='Пополнение баланса пользователя',
                    status='completed'
                )

            return Response({
                'success': True,
                'balance': str(profile.balance),
                'message': f'Баланс пополнен на {amount} ₽'
            })
        except SavedPaymentMethod.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Карта не найдена'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Ошибка при пополнении баланса: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===== API для получения доступных промокодов =====
@method_decorator(csrf_exempt, name='dispatch')
class AvailablePromotionsAPIView(APIView):
    """API для получения доступных промокодов (которые пользователь еще не использовал)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Получить список доступных промокодов"""
        today = timezone.now().date()
        
        # Получаем все активные промокоды
        all_promos = Promotion.objects.filter(
            is_active=True
        ).filter(
            Q(start_date__isnull=True) | Q(start_date__lte=today)
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        )
        
        # Получаем использованные промокоды пользователя
        used_promo_ids = set(
            PromoUsage.objects.filter(user=request.user)
            .values_list('promotion_id', flat=True)
        )
        
        promotions_data = []
        for promo in all_promos:
            is_used = promo.id in used_promo_ids
            promotions_data.append({
                'id': promo.id,
                'promo_code': promo.promo_code,
                'promo_description': promo.promo_description,
                'discount': str(promo.discount),
                'start_date': promo.start_date.isoformat() if promo.start_date else None,
                'end_date': promo.end_date.isoformat() if promo.end_date else None,
                'is_used': is_used,
            })
        
        return Response({
            'success': True,
            'promotions': promotions_data
        })


# ===== API для валидации промокода =====
@method_decorator(csrf_exempt, name='dispatch')
class ValidatePromoAPIView(APIView):
    """API для валидации промокода"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Проверить промокод"""
        promo_code = request.data.get('promo_code', '').strip().upper()
        cart_total_str = request.data.get('cart_total', '0')

        if not promo_code:
            return Response({
                'success': False,
                'error': 'Введите промокод'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_total = Decimal(cart_total_str)
        except (ValueError, InvalidOperation):
            cart_total = Decimal('0')

        try:
            promo = Promotion.objects.get(promo_code=promo_code, is_active=True)
            today = timezone.now().date()
            
            if promo.start_date and promo.start_date > today:
                return Response({
                    'success': False,
                    'error': 'Промокод еще не действует'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if promo.end_date and promo.end_date < today:
                return Response({
                    'success': False,
                    'error': 'Промокод истек'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Проверяем, использовал ли пользователь уже этот промокод
            if PromoUsage.objects.filter(user=request.user, promotion=promo).exists():
                return Response({
                    'success': False,
                    'error': 'Вы уже использовали этот промокод'
                }, status=status.HTTP_400_BAD_REQUEST)

            discount_amount = cart_total * (promo.discount / Decimal('100'))
            delivery_cost = Decimal('1000.00')
            subtotal_after_discount = cart_total - discount_amount
            pre_vat_amount = subtotal_after_discount + delivery_cost
            vat_rate = Decimal('20.00')
            vat_amount = (pre_vat_amount * vat_rate / Decimal('100')).quantize(Decimal('0.01'))
            total_with_vat = pre_vat_amount + vat_amount

            return Response({
                'success': True,
                'discount': str(discount_amount),
                'discount_percent': str(promo.discount),
                'subtotal': str(subtotal_after_discount),
                'delivery': str(delivery_cost),
                'vat_amount': str(vat_amount),
                'total': str(total_with_vat)
            })
        except Promotion.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Неверный промокод'
            }, status=status.HTTP_404_NOT_FOUND)



# ===== API для управления заказами (Менеджер/Админ) =====
@method_decorator(csrf_exempt, name='dispatch')
class OrderManagementAPIView(APIView):
    """API для управления заказами"""
    permission_classes = [IsManagerOrReadOnly]

    def get(self, request):
        """Получить список заказов с фильтрацией"""
        # Разрешаем доступ и админам, и менеджерам
        if not (_user_is_manager(request.user) or _user_is_admin(request.user)):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        status_filter = request.GET.get('status')
        page = int(request.GET.get('page', 1))

        qs = Order.objects.select_related('user', 'address').prefetch_related('items').all()

        if status_filter:
            qs = qs.filter(order_status=status_filter)

        qs = qs.order_by('-created_at')
        paginator = Paginator(qs, 25)
        page_obj = paginator.get_page(page)

        serializer = OrderSerializer(page_obj.object_list, many=True)
        return Response({
            'success': True,
            'orders': serializer.data,
            'page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count
        })


@method_decorator(csrf_exempt, name='dispatch')
class OrderManagementDetailAPIView(APIView):
    """API для работы с конкретным заказом"""
    permission_classes = [IsManagerOrReadOnly]

    def get(self, request, order_id):
        """Получить заказ"""
        # Разрешаем доступ и админам, и менеджерам
        if not (_user_is_manager(request.user) or _user_is_admin(request.user)):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        order = get_object_or_404(Order, id=order_id)
        serializer = OrderSerializer(order)
        return Response(serializer.data)

    def post(self, request, order_id):
        """Изменить статус заказа"""
        # Разрешаем доступ и админам, и менеджерам
        if not (_user_is_manager(request.user) or _user_is_admin(request.user)):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        order = get_object_or_404(Order, id=order_id)
        new_status = request.data.get('status', '').strip()

        if new_status not in dict(Order.ORDER_STATUSES):
            return Response({
                'success': False,
                'error': 'Неверный статус заказа'
            }, status=status.HTTP_400_BAD_REQUEST)

        old_status = order.order_status
        order.order_status = new_status
        order.save()

        # Назначение курьера (модель Delivery удалена — только курсы)
        # carrier_name при необходимости можно хранить в Order или не использовать

        _log_activity(request.user, 'update', f'order_{order_id}', f'Изменен статус заказа: {old_status} -> {new_status}', request)
        serializer = OrderSerializer(order)
        return Response({
            'success': True,
            'order': serializer.data
        })

    def patch(self, request, order_id):
        """Изменить статус заказа (PATCH метод)"""
        # Разрешаем доступ и админам, и менеджерам
        if not (_user_is_manager(request.user) or _user_is_admin(request.user)):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        order = get_object_or_404(Order, id=order_id)
        new_status = request.data.get('status', '').strip()
        
        if not new_status:
            new_status = request.data.get('order_status', '').strip()

        if new_status not in dict(Order.ORDER_STATUSES):
            return Response({
                'success': False,
                'error': 'Неверный статус заказа'
            }, status=status.HTTP_400_BAD_REQUEST)

        old_status = order.order_status
        order.order_status = new_status
        order.save()

        # Назначение курьера (модель Delivery удалена)

        _log_activity(request.user, 'update', f'order_{order_id}', f'Изменен статус заказа: {old_status} -> {new_status}', request)
        serializer = OrderSerializer(order)
        return Response({
            'success': True,
            'order': serializer.data
        })


# ===== API для управления пользователями (Только Админ) =====
@method_decorator(csrf_exempt, name='dispatch')
class UserManagementAPIView(APIView):
    """API для управления пользователями (только для админов)"""
    permission_classes = [IsAdminOrReadOnly]

    def delete(self, request):
        """Массовое удаление пользователей"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен. Требуется роль администратора'
            }, status=status.HTTP_403_FORBIDDEN)

        ids = request.data.get('ids', [])
        if not ids or not isinstance(ids, list):
            return Response({
                'success': False,
                'error': 'Необходимо передать массив ID пользователей'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            deleted_count = 0
            errors = []
            for user_id in ids:
                try:
                    user = User.objects.get(id=user_id)
                    # Не позволяем удалять самого себя
                    if user.id == request.user.id:
                        errors.append(f'Нельзя удалить самого себя (ID: {user_id})')
                        continue
                    user.delete()
                    deleted_count += 1
                    _log_activity(request.user, 'delete', f'user_{user_id}', f'Удален пользователь: {user.username}', request)
                except User.DoesNotExist:
                    errors.append(f'Пользователь с ID {user_id} не найден')
                except Exception as e:
                    errors.append(f'Ошибка при удалении пользователя {user_id}: {str(e)}')

            return Response({
                'success': True,
                'deleted_count': deleted_count,
                'errors': errors if errors else None
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Ошибка при массовом удалении: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        """Создать нового пользователя"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен. Требуется роль администратора'
            }, status=status.HTTP_403_FORBIDDEN)

        username = request.data.get('username', '').strip()
        email = request.data.get('email', '').strip()
        password = request.data.get('password', '').strip()
        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()
        role_id = request.data.get('role_id')
        user_status = request.data.get('user_status', 'active')
        secret_word = request.data.get('secret_word', '').strip()

        if not username or not email or not password:
            return Response({
                'success': False,
                'error': 'Логин, email и пароль обязательны'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Проверяем, не существует ли уже пользователь с таким username или email
        if User.objects.filter(username=username).exists():
            return Response({
                'success': False,
                'error': 'Пользователь с таким логином уже существует'
            }, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response({
                'success': False,
                'error': 'Пользователь с таким email уже существует'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Создаем пользователя
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )

            # Создаем профиль
            profile = UserProfile.objects.create(
                user=user,
                role_id=role_id if role_id else None,
                user_status=user_status,
                full_name=f"{first_name} {last_name}".strip(),
                secret_word=secret_word if secret_word else None
            )

            _log_activity(request.user, 'create', f'user_{user.id}', f'Создан пользователь: {username}', request)

            return Response({
                'success': True,
                'user_id': user.id,
                'message': f'Пользователь {username} успешно создан'
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Ошибка при создании пользователя: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request):
        """Получить список пользователей с фильтрацией"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен. Требуется роль администратора'
            }, status=status.HTTP_403_FORBIDDEN)

        q = request.GET.get('q', '').strip()
        status_filter = request.GET.get('status')
        role_filter = request.GET.get('role')
        activity_filter = request.GET.get('activity')
        page = int(request.GET.get('page', 1))

        qs = User.objects.select_related('profile').all().order_by('-date_joined')

        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
        if status_filter:
            qs = qs.filter(profile__user_status=status_filter)
        if role_filter:
            qs = qs.filter(profile__role_id=role_filter)
        if activity_filter == 'active':
            month_ago = timezone.now() - timedelta(days=30)
            qs = qs.filter(order__created_at__gte=month_ago).distinct()
        elif activity_filter == 'inactive':
            month_ago = timezone.now() - timedelta(days=30)
            qs = qs.exclude(order__created_at__gte=month_ago).distinct()

        paginator = Paginator(qs, 25)
        page_obj = paginator.get_page(page)

        users_data = []
        for user in page_obj.object_list:
            try:
                profile = user.profile
                users_data.append({
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'date_joined': user.date_joined,
                    'is_active': user.is_active,
                    'profile': {
                        'user_status': profile.user_status,
                        'role': profile.role.role_name if profile.role else None,
                        'phone_number': profile.phone_number,
                        'balance': str(profile.balance)
                    }
                })
            except UserProfile.DoesNotExist:
                users_data.append({
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'date_joined': user.date_joined,
                    'is_active': user.is_active,
                    'profile': None
                })

        return Response({
            'success': True,
            'users': users_data,
            'page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count
        })


@method_decorator(csrf_exempt, name='dispatch')
class UserManagementDetailAPIView(APIView):
    """API для работы с конкретным пользователем"""
    permission_classes = [IsAdminOrReadOnly]

    def get(self, request, user_id):
        """Получить пользователя"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        user = get_object_or_404(User, id=user_id)
        try:
            profile = user.profile
            role_name = profile.role.role_name if profile.role else None
        except UserProfile.DoesNotExist:
            profile = None
            role_name = None

        return Response({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'date_joined': user.date_joined,
                'is_active': user.is_active,
                'profile': {
                    'user_status': profile.user_status if profile else 'active',
                    'role': role_name,
                    'phone_number': profile.phone_number if profile else None,
                    'balance': str(profile.balance) if profile else '0.00'
                }
            }
        })

    def put(self, request, user_id):
        """Обновить пользователя"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        user = get_object_or_404(User, id=user_id)
        profile, _ = UserProfile.objects.get_or_create(user=user)

        # Обновление данных пользователя
        if 'first_name' in request.data:
            user.first_name = request.data.get('first_name', '').strip()
        if 'last_name' in request.data:
            user.last_name = request.data.get('last_name', '').strip()
        if 'email' in request.data:
            user.email = request.data.get('email', '').strip()
        if 'is_active' in request.data:
            user.is_active = request.data.get('is_active', True)
        user.save()

        # Обновление профиля
        if 'user_status' in request.data:
            old_status = profile.user_status
            profile.user_status = request.data.get('user_status', 'active')
            # Синхронизируем is_active с user_status
            if profile.user_status == 'blocked':
                user.is_active = False
                user.save()
            elif profile.user_status == 'active':
                user.is_active = True
                user.save()
            profile.save()
            _log_activity(request.user, 'update', f'user_{user_id}', f'Изменен статус: {old_status} -> {profile.user_status}', request)

        if 'role_id' in request.data:
            role_id = request.data.get('role_id')
            old_role = profile.role.role_name if profile.role else None
            if role_id:
                try:
                    role = Role.objects.get(id=role_id)
                    profile.role = role
                    profile.save()
                    new_role = role.role_name
                    _log_activity(request.user, 'update', f'user_{user_id}', f'Изменена роль: {old_role} -> {new_role}', request)
                except Role.DoesNotExist:
                    pass
            else:
                profile.role = None
                profile.save()

        _log_activity(request.user, 'update', f'user_{user_id}', f'Обновлен пользователь: {user.username}', request)

        return Response({
            'success': True,
            'message': 'Пользователь обновлен'
        })

    def post(self, request, user_id):
        """Блокировка/разблокировка пользователя"""
        if not _user_is_manager(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        user = get_object_or_404(User, id=user_id)
        profile, _ = UserProfile.objects.get_or_create(user=user)

        old_status = profile.user_status
        if old_status == 'blocked':
            profile.user_status = 'active'
            user.is_active = True
        else:
            profile.user_status = 'blocked'
            user.is_active = False

        user.save()
        profile.save()

        _log_activity(request.user, 'update', f'user_{user_id}', f'Изменен статус пользователя: {old_status} -> {profile.user_status}', request)

        return Response({
            'success': True,
            'user_status': profile.user_status,
            'message': f'Пользователь {"заблокирован" if profile.user_status == "blocked" else "разблокирован"}'
        })

    def delete(self, request, user_id):
        """Удалить пользователя"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        user = get_object_or_404(User, id=user_id)
        username = user.username
        user_id_val = user.id
        user.delete()
        _log_activity(request.user, 'delete', f'user_{user_id_val}', f'Удален пользователь: {username}', request)
        return Response({
            'success': True,
            'message': f'Пользователь {username} удален'
        }, status=status.HTTP_204_NO_CONTENT)


# ===== API для поддержки =====
@method_decorator(csrf_exempt, name='dispatch')
class SupportTicketAPIView(APIView):
    """API для работы с обращениями в поддержку"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Получить все обращения пользователя или все (для менеджеров)"""
        if _user_is_manager(request.user):
            # Менеджеры видят все обращения
            tickets = SupportTicket.objects.select_related('user').all().order_by('-created_at')
        else:
            # Пользователи видят только свои
            tickets = SupportTicket.objects.filter(user=request.user).order_by('-created_at')

        serializer = SupportTicketSerializer(tickets, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Создать новое обращение"""
        subject = request.data.get('subject', '').strip()
        message_text = request.data.get('message_text', '').strip()

        if not subject or not message_text:
            return Response({
                'success': False,
                'error': 'Заполните тему и сообщение'
            }, status=status.HTTP_400_BAD_REQUEST)

        ticket = SupportTicket.objects.create(
            user=request.user,
            subject=subject,
            message_text=message_text,
            ticket_status='new'
        )

        _log_activity(request.user, 'create', f'ticket_{ticket.id}', f'Создано обращение в поддержку: {subject}', request)
        serializer = SupportTicketSerializer(ticket)
        return Response({
            'success': True,
            'ticket': serializer.data
        }, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name='dispatch')
class SupportTicketDetailAPIView(APIView):
    """API для работы с конкретным обращением"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, ticket_id):
        """Получить обращение"""
        if _user_is_manager(request.user):
            ticket = get_object_or_404(SupportTicket, id=ticket_id)
        else:
            ticket = get_object_or_404(SupportTicket, id=ticket_id, user=request.user)

        serializer = SupportTicketSerializer(ticket)
        return Response(serializer.data)

    def put(self, request, ticket_id):
        """Обновить обращение (ответ менеджера)"""
        if not _user_is_manager(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        ticket = get_object_or_404(SupportTicket, id=ticket_id)
        response_text = request.data.get('response_text', '').strip()
        ticket_status = request.data.get('ticket_status', ticket.ticket_status)
        
        # Обработка назначения ответственного
        assigned_to_id = request.data.get('assigned_to_id')
        old_assigned = ticket.assigned_to.username if ticket.assigned_to else None
        
        if assigned_to_id is not None:
            if assigned_to_id:
                try:
                    assigned_user = User.objects.get(pk=assigned_to_id)
                    ticket.assigned_to = assigned_user
                    new_assigned = assigned_user.username
                    if old_assigned != new_assigned:
                        _log_activity(request.user, 'update', f'ticket_{ticket_id}', f'Назначен ответственный: {new_assigned}', request)
                except User.DoesNotExist:
                    return Response({
                        'success': False,
                        'error': 'Пользователь не найден'
                    }, status=status.HTTP_404_NOT_FOUND)
            else:
                ticket.assigned_to = None
                if old_assigned:
                    _log_activity(request.user, 'update', f'ticket_{ticket_id}', 'Снят ответственный', request)

        if response_text:
            ticket.response_text = response_text
        
        # Валидация статуса - разрешенные значения
        allowed_statuses = ['new', 'in_progress', 'resolved']
        if ticket_status in allowed_statuses:
            old_status = ticket.ticket_status
            ticket.ticket_status = ticket_status
            if old_status != ticket_status:
                _log_activity(request.user, 'update', f'ticket_{ticket_id}', f'Изменен статус: {old_status} -> {ticket.ticket_status}', request)

        ticket.save()
        _log_activity(request.user, 'update', f'ticket_{ticket_id}', 'Обновлено обращение в поддержку', request)

        serializer = SupportTicketSerializer(ticket)
        return Response({
            'success': True,
            'ticket': serializer.data
        })


# ===== API для каталога (курсы) =====
@method_decorator(csrf_exempt, name='dispatch')
class CatalogAPIView(APIView):
    """API каталога курсов с фильтрацией и поиском"""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        q = request.GET.get('q', '').strip()
        category_id = request.GET.get('category')
        min_price = request.GET.get('min_price')
        max_price = request.GET.get('max_price')
        sort = request.GET.get('sort', '')
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))

        qs = Course.objects.filter(is_available=True).select_related('category').prefetch_related('images')

        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        if category_id:
            qs = qs.filter(category_id=category_id)
        if min_price:
            try:
                qs = qs.filter(price__gte=Decimal(min_price))
            except (ValueError, InvalidOperation):
                pass
        if max_price:
            try:
                qs = qs.filter(price__lte=Decimal(max_price))
            except (ValueError, InvalidOperation):
                pass
        if sort == 'price_asc':
            qs = qs.order_by('price')
        elif sort == 'price_desc':
            qs = qs.order_by('-price')
        elif sort == 'popular':
            qs = qs.order_by('-added_at')
        else:
            qs = qs.order_by('-added_at')

        paginator = Paginator(qs, per_page)
        page_obj = paginator.get_page(page)
        serializer = CourseSerializer(page_obj.object_list, many=True)
        categories = CourseCategory.objects.all().order_by('category_name')
        data = {
            'success': True,
            'products': serializer.data,
            'courses': serializer.data,
            'categories': CourseCategorySerializer(categories, many=True).data,
            'page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count
        }
        if request.user.is_authenticated:
            data['purchased_course_ids'] = list(
                CoursePurchase.objects.filter(user=request.user, status='paid').values_list('course_id', flat=True)
            )
        else:
            data['purchased_course_ids'] = []
        return Response(data)


# ===== API избранного (курсы) =====
@method_decorator(csrf_exempt, name='dispatch')
class FavoritesAPIView(APIView):
    """API избранных курсов"""
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request):
        favorites = CourseFavorite.objects.filter(user=request.user).select_related('course', 'course__category')
        courses = [fav.course for fav in favorites]
        return Response(CourseSerializer(courses, many=True).data)

    def post(self, request):
        course_id = request.data.get('course_id') or request.data.get('product_id')
        if course_id is None:
            return Response({'success': False, 'error': 'course_id или product_id обязателен'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            course_id = int(course_id)
        except (ValueError, TypeError):
            return Response({'success': False, 'error': 'course_id должен быть числом'}, status=status.HTTP_400_BAD_REQUEST)
        course = get_object_or_404(Course, id=course_id)
        CourseFavorite.objects.get_or_create(user=request.user, course=course)
        return Response({'success': True, 'message': 'Курс добавлен в избранное'})


@method_decorator(csrf_exempt, name='dispatch')
class FavoriteDetailAPIView(APIView):
    """Удаление курса из избранного (product_id в URL = course_id)"""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, product_id):
        fav = get_object_or_404(CourseFavorite, user=request.user, course_id=product_id)
        fav.delete()
        return Response({'success': True, 'message': 'Курс удалён из избранного'}, status=status.HTTP_204_NO_CONTENT)


# ===== API управления курсами (менеджер/админ) =====
@method_decorator(csrf_exempt, name='dispatch')
class CourseManagementAPIView(APIView):
    permission_classes = [IsManagerOrReadOnly]

    def get(self, request):
        if not _user_is_manager(request.user):
            return Response({'success': False, 'error': 'Доступ запрещен'}, status=status.HTTP_403_FORBIDDEN)
        q = request.GET.get('q', '').strip()
        category_id = request.GET.get('category')
        page = int(request.GET.get('page', 1))
        qs = Course.objects.select_related('category').prefetch_related('images').all()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        if category_id:
            qs = qs.filter(category_id=category_id)
        qs = qs.order_by('-added_at')
        paginator = Paginator(qs, 25)
        page_obj = paginator.get_page(page)
        return Response({
            'success': True,
            'courses': CourseSerializer(page_obj.object_list, many=True).data,
            'page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_count': paginator.count
        })


@method_decorator(csrf_exempt, name='dispatch')
class CourseManagementDetailAPIView(APIView):
    permission_classes = [IsManagerOrReadOnly]

    def get(self, request, course_id):
        if not _user_is_manager(request.user):
            return Response({'success': False, 'error': 'Доступ запрещен'}, status=status.HTTP_403_FORBIDDEN)
        course = get_object_or_404(Course, pk=course_id)
        return Response({'success': True, 'course': CourseSerializer(course).data})

    def delete(self, request, course_id):
        if not (_user_is_manager(request.user) or _user_is_admin(request.user)):
            return Response({'success': False, 'error': 'Доступ запрещен'}, status=status.HTTP_403_FORBIDDEN)
        course = get_object_or_404(Course, pk=course_id)
        title = course.title
        course.delete()
        _log_activity(request.user, 'delete', f'course_{course_id}', f'Удален курс: {title}', request)
        return Response({'success': True}, status=status.HTTP_204_NO_CONTENT)


@method_decorator(csrf_exempt, name='dispatch')
class CourseCategoryManagementAPIView(APIView):
    permission_classes = [IsManagerOrReadOnly]

    def get(self, request):
        if not _user_is_manager(request.user):
            return Response({'success': False, 'error': 'Доступ запрещен'}, status=status.HTTP_403_FORBIDDEN)
        categories = CourseCategory.objects.all().order_by('category_name')
        return Response({
            'success': True,
            'categories': CourseCategorySerializer(categories, many=True).data
        })


@method_decorator(csrf_exempt, name='dispatch')
class CourseCategoryManagementDetailAPIView(APIView):
    permission_classes = [IsManagerOrReadOnly]

    def get(self, request, category_id):
        if not _user_is_manager(request.user):
            return Response({'success': False, 'error': 'Доступ запрещен'}, status=status.HTTP_403_FORBIDDEN)
        category = get_object_or_404(CourseCategory, pk=category_id)
        return Response({'success': True, 'category': CourseCategorySerializer(category).data})


@method_decorator(csrf_exempt, name='dispatch')
class CourseReviewAPIView(APIView):
    """API отзывов по курсу: GET список, POST добавить/обновить"""
    permission_classes = [permissions.AllowAny]

    def get(self, request, course_id):
        course = get_object_or_404(Course, pk=course_id)
        reviews = CourseReview.objects.filter(course=course).select_related('user').order_by('-created_at')
        limit = int(request.GET.get('limit', 20))
        reviews_limited = list(reviews[:limit])
        reviews_data = [{
            'id': r.id,
            'user': r.user.username if r.user else '',
            'user_name': (r.user.get_full_name() or r.user.username) if r.user else 'Анонимный пользователь',
            'rating': r.rating,
            'review_text': r.review_text or '',
            'text': r.review_text or '',
            'created_at': r.created_at.strftime('%d.%m.%Y %H:%M') if r.created_at else ''
        } for r in reviews_limited]
        avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
        total_reviews = reviews.count()
        user_can_review = False
        if request.user.is_authenticated:
            user_can_review = OrderItem.objects.filter(
                order__user=request.user,
                course=course
            ).annotate(
                has_paid=Exists(
                    Payment.objects.filter(order=OuterRef('order'), payment_status='paid')
            )).filter(
                Q(has_paid=True) |
                Q(order__order_status__in=['paid', 'shipped', 'delivered'])
            ).exists()
        return Response({
            'success': True,
            'reviews': reviews_data,
            'avg_rating': round(float(avg_rating), 1),
            'total_reviews': total_reviews,
            'has_more': total_reviews > limit,
            'user_can_review': user_can_review
        })

    def post(self, request, course_id):
        """Добавить или обновить отзыв (только авторизованный, купивший курс)."""
        if not request.user.is_authenticated:
            return Response({'success': False, 'message': 'Необходима авторизация'}, status=status.HTTP_401_UNAUTHORIZED)
        course = get_object_or_404(Course, pk=course_id)
        rating = int(request.data.get('rating', 0))
        review_text = (request.data.get('review_text') or request.data.get('text') or '').strip()
        if not 1 <= rating <= 5:
            return Response({'success': False, 'message': 'Оценка должна быть от 1 до 5'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from .utils import filter_profanity
            review_text = filter_profanity(review_text)
        except Exception:
            pass
        user_has_purchased = OrderItem.objects.filter(
            order__user=request.user,
            course=course
        ).annotate(
            has_paid=Exists(
                Payment.objects.filter(order=OuterRef('order'), payment_status='paid')
            )
        ).filter(
            Q(has_paid=True) |
            Q(order__order_status__in=['paid', 'shipped', 'delivered'])
        ).exists()
        if not user_has_purchased:
            return Response({'success': False, 'message': 'Вы можете оставить отзыв только на купленный курс'}, status=status.HTTP_403_FORBIDDEN)
        existing = CourseReview.objects.filter(user=request.user, course=course).first()
        if existing:
            existing.rating = rating
            existing.review_text = review_text
            existing.save()
            return Response({'success': True, 'message': 'Отзыв обновлен'})
        CourseReview.objects.create(user=request.user, course=course, rating=rating, review_text=review_text)
        return Response({'success': True, 'message': 'Отзыв добавлен'})


# ===== API для счета организации (Только Админ) =====
@method_decorator(csrf_exempt, name='dispatch')
class OrganizationAccountAPIView(APIView):
    """API для управления счетом организации"""
    permission_classes = [IsAdminOrReadOnly]

    def get(self, request):
        """Получить информацию о счете организации"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        org_account = OrganizationAccount.get_account()
        transactions = OrganizationTransaction.objects.filter(
            organization_account=org_account
        ).select_related('order', 'created_by').order_by('-created_at')[:50]

        serializer = OrganizationAccountSerializer(org_account)
        transactions_serializer = OrganizationTransactionSerializer(transactions, many=True)

        return Response({
            'success': True,
            'account': serializer.data,
            'transactions': transactions_serializer.data
        })

    def post(self, request):
        """Вывод средств или оплата налога"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        action = request.data.get('action')
        org_account = OrganizationAccount.get_account()

        if action == 'withdraw':
            # Вывод средств на карту админа
            try:
                amount = Decimal(request.data.get('amount', '0'))
            except (ValueError, InvalidOperation):
                return Response({
                    'success': False,
                    'error': 'Неверный формат суммы'
                }, status=status.HTTP_400_BAD_REQUEST)

            card_id = request.data.get('card_id')

            if amount <= 0:
                return Response({
                    'success': False,
                    'error': 'Сумма должна быть больше нуля'
                }, status=status.HTTP_400_BAD_REQUEST)

            org_account.refresh_from_db()

            if not org_account.can_withdraw(amount):
                return Response({
                    'success': False,
                    'error': f'Недостаточно средств на счете организации. Доступно: {org_account.balance} ₽, запрошено: {amount} ₽'
                }, status=status.HTTP_400_BAD_REQUEST)

            if not card_id:
                return Response({
                    'success': False,
                    'error': 'Выберите карту для вывода средств'
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                card = SavedPaymentMethod.objects.get(id=card_id, user=request.user)
            except SavedPaymentMethod.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Карта не найдена'
                }, status=status.HTTP_404_NOT_FOUND)

            try:
                with transaction.atomic():
                    org_account = OrganizationAccount.objects.select_for_update().get(pk=org_account.pk)
                    
                    if not org_account.can_withdraw(amount):
                        return Response({
                            'success': False,
                            'error': f'Недостаточно средств на счете организации. Доступно: {org_account.balance} ₽, запрошено: {amount} ₽'
                        }, status=status.HTTP_400_BAD_REQUEST)

                    balance_before = org_account.balance
                    tax_reserve_before = org_account.tax_reserve

                    org_account.balance -= amount
                    org_account.save()
                    balance_after = org_account.balance

                    card.balance += amount
                    card.save()

                    OrganizationTransaction.objects.create(
                        organization_account=org_account,
                        transaction_type='withdrawal',
                        amount=amount,
                        description=f'Вывод средств на карту {card.mask_card_number}',
                        created_by=request.user,
                        balance_before=balance_before,
                        balance_after=balance_after,
                        tax_reserve_before=tax_reserve_before,
                        tax_reserve_after=tax_reserve_before,
                    )

                    _log_activity(request.user, 'update', 'org_account', f'Вывод средств {amount} ₽ на карту', request)

                    return Response({
                        'success': True,
                        'message': f'Средства в размере {amount} ₽ выведены на карту'
                    })
            except Exception as e:
                return Response({
                    'success': False,
                    'error': f'Ошибка при выводе средств: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        elif action == 'pay_tax':
            # Оплата налога
            try:
                amount = Decimal(request.data.get('amount', '0'))
            except (ValueError, InvalidOperation):
                return Response({
                    'success': False,
                    'error': 'Неверный формат суммы'
                }, status=status.HTTP_400_BAD_REQUEST)

            if amount <= 0:
                return Response({
                    'success': False,
                    'error': 'Сумма должна быть больше нуля'
                }, status=status.HTTP_400_BAD_REQUEST)

            org_account.refresh_from_db()

            if not org_account.can_pay_tax(amount):
                if org_account.tax_reserve < amount:
                    error_msg = f'Недостаточно средств в резерве на налоги. Доступно: {org_account.tax_reserve} ₽, запрошено: {amount} ₽'
                elif org_account.balance < amount:
                    error_msg = f'Недостаточно средств на счете организации. Доступно: {org_account.balance} ₽, запрошено: {amount} ₽'
                else:
                    error_msg = f'Недостаточно средств для оплаты налога'
                return Response({
                    'success': False,
                    'error': error_msg
                }, status=status.HTTP_400_BAD_REQUEST)

            try:
                with transaction.atomic():
                    org_account = OrganizationAccount.objects.select_for_update().get(pk=org_account.pk)
                    
                    if not org_account.can_pay_tax(amount):
                        if org_account.tax_reserve < amount:
                            error_msg = f'Недостаточно средств в резерве на налоги. Доступно: {org_account.tax_reserve} ₽, запрошено: {amount} ₽'
                        elif org_account.balance < amount:
                            error_msg = f'Недостаточно средств на счете организации. Доступно: {org_account.balance} ₽, запрошено: {amount} ₽'
                        else:
                            error_msg = f'Недостаточно средств для оплаты налога'
                        return Response({
                            'success': False,
                            'error': error_msg
                        }, status=status.HTTP_400_BAD_REQUEST)
                    
                    balance_before = org_account.balance
                    tax_reserve_before = org_account.tax_reserve
                    
                    org_account.balance -= amount
                    org_account.tax_reserve -= amount
                    org_account.save()

                    OrganizationTransaction.objects.create(
                        organization_account=org_account,
                        transaction_type='tax_payment',
                        amount=amount,
                        description=f'Оплата налога',
                        created_by=request.user,
                        balance_before=balance_before,
                        balance_after=org_account.balance,
                        tax_reserve_before=tax_reserve_before,
                        tax_reserve_after=org_account.tax_reserve,
                    )

                    _log_activity(request.user, 'update', 'org_account', f'Оплата налога {amount} ₽', request)

                    return Response({
                        'success': True,
                        'message': f'Налог в размере {amount} ₽ оплачен'
                    })
            except Exception as e:
                return Response({
                    'success': False,
                    'error': f'Ошибка при оплате налога: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'success': False,
            'error': 'Неверное действие'
        }, status=status.HTTP_400_BAD_REQUEST)


# ===== API для управления промокодами (Только Админ) =====
@method_decorator(csrf_exempt, name='dispatch')
class PromotionManagementAPIView(APIView):
    """API для управления промокодами (только для админов)"""
    permission_classes = [IsAdminOrReadOnly]

    def delete(self, request):
        """Массовое удаление промокодов"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен. Требуется роль администратора'
            }, status=status.HTTP_403_FORBIDDEN)

        ids = request.data.get('ids', [])
        if not ids or not isinstance(ids, list):
            return Response({
                'success': False,
                'error': 'Необходимо передать массив ID промокодов'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            deleted_count = 0
            errors = []
            for promo_id in ids:
                try:
                    promo = Promotion.objects.get(id=promo_id)
                    promo_code = promo.promo_code
                    promo.delete()
                    deleted_count += 1
                    _log_activity(request.user, 'delete', f'promotion_{promo_id}', f'Удален промокод: {promo_code}', request)
                except Promotion.DoesNotExist:
                    errors.append(f'Промокод с ID {promo_id} не найден')
                except Exception as e:
                    errors.append(f'Ошибка при удалении промокода {promo_id}: {str(e)}')

            return Response({
                'success': True,
                'deleted_count': deleted_count,
                'errors': errors if errors else None
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Ошибка при массовом удалении: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request):
        """Получить список промокодов с фильтрацией"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        q = request.GET.get('q', '').strip()
        page = int(request.GET.get('page', 1))

        qs = Promotion.objects.all().order_by('-start_date', 'promo_code')

        if q:
            qs = qs.filter(Q(promo_code__icontains=q) | Q(promo_description__icontains=q))

        paginator = Paginator(qs, 25)
        page_obj = paginator.get_page(page)

        promotions_data = []
        for promo in page_obj.object_list:
            promotions_data.append({
                'id': promo.id,
                'promo_code': promo.promo_code,
                'promo_description': promo.promo_description,
                'discount': float(promo.discount),
                'start_date': promo.start_date.isoformat() if promo.start_date else None,
                'end_date': promo.end_date.isoformat() if promo.end_date else None,
                'is_active': promo.is_active
            })

        return Response({
            'success': True,
            'promotions': promotions_data,
            'pagination': {
                'page': page_obj.number,
                'pages': paginator.num_pages,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        })

    def post(self, request):
        """Создать новый промокод"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        promo_code = request.data.get('promo_code', '').strip().upper()
        promo_description = request.data.get('promo_description', '').strip()
        discount_str = request.data.get('discount', '0')
        start_date_str = request.data.get('start_date', '').strip()
        end_date_str = request.data.get('end_date', '').strip()
        is_active = request.data.get('is_active', True)

        if not promo_code:
            return Response({
                'success': False,
                'error': 'Код промокода обязателен'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            discount = Decimal(discount_str) if discount_str else Decimal('0')
        except (ValueError, InvalidOperation):
            discount = Decimal('0')

        start_date = None
        end_date = None
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        promotion = Promotion.objects.create(
            promo_code=promo_code,
            promo_description=promo_description,
            discount=discount,
            start_date=start_date,
            end_date=end_date,
            is_active=is_active
        )

        _log_activity(request.user, 'create', f'promotion_{promotion.id}', f'Создан промокод: {promo_code}', request)

        return Response({
            'success': True,
            'promotion_id': promotion.id,
            'message': 'Промокод создан'
        }, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name='dispatch')
class PromotionManagementDetailAPIView(APIView):
    """API для работы с конкретным промокодом"""
    permission_classes = [IsAdminOrReadOnly]

    def get(self, request, promo_id):
        """Получить промокод"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        promotion = get_object_or_404(Promotion, id=promo_id)
        serializer = PromotionSerializer(promotion)
        return Response({
            'success': True,
            'promotion': serializer.data
        })

    def put(self, request, promo_id):
        """Обновить промокод"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        promotion = get_object_or_404(Promotion, id=promo_id)

        promo_code = request.data.get('promo_code', '').strip().upper()
        promo_description = request.data.get('promo_description', '').strip()
        discount_str = request.data.get('discount', '0')
        start_date_str = request.data.get('start_date', '').strip()
        end_date_str = request.data.get('end_date', '').strip()
        is_active = request.data.get('is_active', True)

        if not promo_code:
            return Response({
                'success': False,
                'error': 'Код промокода обязателен'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            discount = Decimal(discount_str) if discount_str else Decimal('0')
        except (ValueError, InvalidOperation):
            discount = Decimal('0')

        start_date = None
        end_date = None
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        promotion.promo_code = promo_code
        promotion.promo_description = promo_description
        promotion.discount = discount
        promotion.start_date = start_date
        promotion.end_date = end_date
        promotion.is_active = is_active
        promotion.save()

        _log_activity(request.user, 'update', f'promotion_{promo_id}', f'Обновлен промокод: {promo_code}', request)

        return Response({
            'success': True,
            'message': 'Промокод обновлен'
        })

    def delete(self, request, promo_id):
        """Удалить промокод"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        promotion = get_object_or_404(Promotion, id=promo_id)
        promo_code = promotion.promo_code
        promotion.delete()

        _log_activity(request.user, 'delete', f'promotion_{promo_id}', f'Удален промокод: {promo_code}', request)

        return Response({
            'success': True,
            'message': f'Промокод {promo_code} удален'
        }, status=status.HTTP_204_NO_CONTENT)


# ===== API для управления ролями (Только Админ) =====
@method_decorator(csrf_exempt, name='dispatch')
class RoleManagementAPIView(APIView):
    """API для управления ролями (только для админов)"""
    permission_classes = [IsAdminOrReadOnly]

    def get(self, request):
        """Получить список ролей"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        roles = Role.objects.all().order_by('role_name')
        serializer = RoleSerializer(roles, many=True)
        return Response({
            'success': True,
            'roles': serializer.data
        })

    def post(self, request):
        """Создать новую роль"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        role_name = request.data.get('role_name', '').strip()

        if not role_name:
            return Response({
                'success': False,
                'error': 'Название роли обязательно'
            }, status=status.HTTP_400_BAD_REQUEST)

        if Role.objects.filter(role_name=role_name).exists():
            return Response({
                'success': False,
                'error': 'Роль с таким названием уже существует'
            }, status=status.HTTP_400_BAD_REQUEST)

        role = Role.objects.create(role_name=role_name)
        _log_activity(request.user, 'create', f'role_{role.id}', f'Создана роль: {role_name}', request)

        return Response({
            'success': True,
            'role_id': role.id,
            'message': 'Роль создана'
        }, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name='dispatch')
class RoleManagementDetailAPIView(APIView):
    """API для работы с конкретной ролью"""
    permission_classes = [IsAdminOrReadOnly]

    def delete(self, request, role_id):
        """Удалить роль"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        role = get_object_or_404(Role, id=role_id)
        role_name = role.role_name
        role.delete()

        _log_activity(request.user, 'delete', f'role_{role_id}', f'Удалена роль: {role_name}', request)

        return Response({
            'success': True,
            'message': f'Роль {role_name} удалена'
        }, status=status.HTTP_204_NO_CONTENT)


# ===== API для управления бэкапами (Только Админ) =====
@method_decorator(csrf_exempt, name='dispatch')
class BackupManagementAPIView(APIView):
    """API для управления бэкапами (только для админов)"""
    permission_classes = [IsAdminOrReadOnly]

    def get(self, request):
        """Получить список бэкапов"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        from .models import DatabaseBackup
        page = int(request.GET.get('page', 1))
        qs = DatabaseBackup.objects.select_related('created_by').all().order_by('-created_at')

        paginator = Paginator(qs, 25)
        page_obj = paginator.get_page(page)

        backups_data = []
        for backup in page_obj.object_list:
            backups_data.append({
                'id': backup.id,
                'backup_name': backup.backup_name,
                'created_at': backup.created_at.isoformat(),
                'created_by': backup.created_by.username if backup.created_by else 'Система',
                'file_size_mb': backup.get_file_size_mb(),
                'schedule': backup.schedule,
                'schedule_display': backup.get_schedule_display(),
                'is_automatic': backup.is_automatic,
                'notes': backup.notes
            })

        return Response({
            'success': True,
            'backups': backups_data,
            'pagination': {
                'page': page_obj.number,
                'pages': paginator.num_pages,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        })

    def post(self, request):
        """Создать бэкап"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            from .models import DatabaseBackup
            import shutil
            import os
            from django.conf import settings

            backup_name = request.data.get('backup_name', '').strip()
            schedule = request.data.get('schedule', 'now')
            notes = request.data.get('notes', '').strip() or None

            # Получаем настройки базы данных
            db_config = settings.DATABASES['default']
            db_engine = db_config.get('ENGINE', '')
            
            # Закрываем все соединения с БД перед созданием бэкапа
            from django.db import connections
            for conn in connections.all():
                conn.close()
            
            # Создаем директорию для бэкапов, если её нет
            backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            
            # Генерируем имя файла бэкапа
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Определяем тип базы данных и создаем бэкап
            if 'sqlite' in db_engine.lower():
                # SQLite - создаем полный бэкап всех данных
                db_path = db_config['NAME']
                # Преобразуем Path объект в строку, если необходимо
                from pathlib import Path as PathLib
                if isinstance(db_path, PathLib):
                    db_path = str(db_path)
                elif not isinstance(db_path, str):
                    db_path = str(db_path)
                
                # Если путь относительный, делаем его абсолютным
                if not os.path.isabs(db_path):
                    from django.conf import settings
                    base_dir = getattr(settings, 'BASE_DIR', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    db_path = os.path.join(base_dir, db_path)
                
                if not os.path.exists(db_path):
                    return Response({
                        'success': False,
                        'error': f'База данных не найдена: {db_path}'
                    }, status=status.HTTP_404_NOT_FOUND)
                
                backup_filename = f'db_backup_{timestamp}.sqlite3'
                backup_path = os.path.join(backup_dir, backup_filename)
                
                # Используем VACUUM INTO для создания полного бэкапа
                # Это гарантирует, что все данные из WAL файла будут включены в бэкап
                import sqlite3
                temp_backup = os.path.join(backup_dir, f'temp_backup_{timestamp}.sqlite3')
                
                try:
                    # Подключаемся к БД и выполняем VACUUM INTO
                    # Это создаст полный бэкап со всеми данными, включая данные из WAL
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    # Выполняем VACUUM INTO для создания полного бэкапа
                    # Это гарантирует включение всех данных, включая логи (ActivityLog),
                    # избранное (Favorite), корзины (Cart), заказы (Order), чеки (Receipt) и все остальное
                    cursor.execute(f"VACUUM INTO '{temp_backup}'")
                    conn.commit()
                    conn.close()
                    
                    # Переименовываем временный файл в финальный
                    shutil.move(temp_backup, backup_path)
                    
                except Exception as e:
                    # Если VACUUM INTO не сработал, используем стандартное копирование
                    # но сначала выполняем CHECKPOINT для слияния WAL
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
                    return Response({
                        'success': False,
                        'error': 'Ошибка: файл бэкапа не был создан'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
                # Проверяем размер файла
                backup_size = os.path.getsize(backup_path)
                original_size = os.path.getsize(db_path)
                
                if backup_size == 0:
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    return Response({
                        'success': False,
                        'error': 'Ошибка: файл бэкапа пустой'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
                # Проверяем целостность бэкапа
                try:
                    conn = sqlite3.connect(backup_path)
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA integrity_check")
                    result = cursor.fetchone()
                    conn.close()
                    
                    if result and result[0] != 'ok':
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        return Response({
                            'success': False,
                            'error': f'Ошибка: бэкап поврежден: {result[0]}'
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                except Exception as e:
                    # Если не удалось проверить, продолжаем, но предупреждаем
                    pass
                    
            elif 'postgresql' in db_engine.lower() or 'postgres' in db_engine.lower():
                # PostgreSQL - создаем полный SQL дамп через pg_dump
                # Это сохраняет ВСЕ данные: таблицы, индексы, последовательности, функции, триггеры, ограничения
                # Включая: избранное (Favorite), корзины (Cart), заказы (Order), логи (ActivityLog) и все остальное
                import subprocess
                db_name = db_config['NAME']
                db_user = db_config.get('USER', 'postgres')
                db_password = db_config.get('PASSWORD', '')
                db_host = db_config.get('HOST', 'localhost')
                db_port = db_config.get('PORT', '5432')
                
                backup_filename = f'db_backup_{timestamp}.sql'
                backup_path = os.path.join(backup_dir, backup_filename)
                
                # Формируем команду pg_dump с флагами для полного бэкапа
                # --verbose: подробный вывод (для отладки)
                # --no-owner: не включать команды OWNER (для совместимости между разными пользователями)
                # --no-acl: не включать команды ACL (для совместимости)
                # --clean: включить команды DROP перед CREATE (для чистого восстановления)
                # --if-exists: использовать IF EXISTS в командах DROP (безопаснее)
                # --format=plain: текстовый формат SQL (для читаемости и восстановления)
                # --encoding=UTF8: явно указываем кодировку
                # --data-only: НЕ используем, так как нам нужна структура тоже
                # --schema-only: НЕ используем, так как нам нужны данные тоже
                cmd = ['pg_dump', '--verbose', '--no-owner', '--no-acl', '--clean', '--if-exists', '--encoding=UTF8']
                if db_host:
                    cmd.extend(['-h', db_host])
                if db_port:
                    cmd.extend(['-p', str(db_port)])
                if db_user:
                    cmd.extend(['-U', db_user])
                cmd.extend(['-d', db_name])
                
                # Устанавливаем переменную окружения для пароля
                env = os.environ.copy()
                if db_password:
                    env['PGPASSWORD'] = db_password
                
                # Устанавливаем кодировку UTF-8
                env['PYTHONIOENCODING'] = 'utf-8'
                if 'LANG' not in env:
                    env['LANG'] = 'en_US.UTF-8'
                env['PGCLIENTENCODING'] = 'UTF8'
                
                # Создаем полный дамп всех данных в файл
                try:
                    with open(backup_path, 'w', encoding='utf-8') as f:
                        result = subprocess.run(
                            cmd,
                            stdout=f,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding='utf-8',
                            errors='replace',
                            env=env,
                            timeout=600  # 10 минут таймаут для больших БД
                        )
                    
                    if result.returncode != 0:
                        error_msg = (result.stderr or 'Неизвестная ошибка').strip()
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        return Response({
                            'success': False,
                            'error': f'Ошибка при создании бэкапа PostgreSQL: {error_msg}'
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    
                    if not os.path.exists(backup_path) or os.path.getsize(backup_path) == 0:
                        return Response({
                            'success': False,
                            'error': 'Ошибка: файл бэкапа не был создан или пустой'
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    
                    backup_size = os.path.getsize(backup_path)
                    
                    # Проверяем, что в дампе есть данные (минимальный размер для валидного дампа)
                    if backup_size < 1024:  # Минимум 1KB
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        return Response({
                            'success': False,
                            'error': f'Ошибка: файл бэкапа слишком мал (размер: {backup_size} байт). Возможно, база данных пуста или произошла ошибка.'
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    
                except subprocess.TimeoutExpired:
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    return Response({
                        'success': False,
                        'error': 'Таймаут при создании бэкапа (превышено 10 минут). База данных слишком большая или произошла ошибка.'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                except FileNotFoundError:
                    return Response({
                        'success': False,
                        'error': 'pg_dump не найден. Установите PostgreSQL client tools. В Docker это должно быть установлено автоматически.'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                except Exception as e:
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    return Response({
                        'success': False,
                        'error': f'Ошибка при создании бэкапа PostgreSQL: {str(e)}'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                return Response({
                    'success': False,
                    'error': f'Неподдерживаемый тип базы данных: {db_engine}'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Получаем размер файла (используем уже проверенный размер)
            file_size = backup_size

            # Создаем запись в базе данных
            if not backup_name:
                backup_name = f'Бэкап от {datetime.now().strftime("%d.%m.%Y %H:%M")}'

            is_automatic = schedule != 'now'

            backup = DatabaseBackup.objects.create(
                backup_name=backup_name,
                created_by=request.user,
                file_size=file_size,
                schedule=schedule,
                notes=notes,
                is_automatic=is_automatic
            )

            # Сохраняем путь к файлу
            backup.backup_file.name = f'backups/{backup_filename}'
            backup.save()

            _log_activity(request.user, 'create', f'backup_{backup.id}', f'Создан бэкап базы данных: {backup_name}', request)

            return Response({
                'success': True,
                'backup_id': backup.id,
                'message': f'Бэкап "{backup_name}" успешно создан'
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Ошибка при создании бэкапа: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class BackupManagementDetailAPIView(APIView):
    """API для работы с конкретным бэкапом"""
    permission_classes = [IsAdminOrReadOnly]

    def delete(self, request, backup_id):
        """Удалить бэкап"""
        if not _user_is_admin(request.user):
            return Response({
                'success': False,
                'error': 'Доступ запрещен'
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            from .models import DatabaseBackup
            import os
            from django.conf import settings

            backup = get_object_or_404(DatabaseBackup, id=backup_id)
            backup_name = backup.backup_name

            # Удаляем файл, если он существует
            if backup.backup_file:
                file_path = os.path.join(settings.MEDIA_ROOT, backup.backup_file.name)
                if os.path.exists(file_path):
                    os.remove(file_path)

            backup.delete()

            _log_activity(request.user, 'delete', f'backup_{backup_id}', f'Удален бэкап: {backup_name}', request)

            return Response({
                'success': True,
                'message': f'Бэкап "{backup_name}" удален'
            }, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Ошибка при удалении бэкапа: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserSettingsAPIView(APIView):
    """API для получения и обновления настроек пользователя"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Получить настройки пользователя"""
        try:
            settings = UserSettings.get_or_create_for_user(request.user)
            return Response({
                'success': True,
                'settings': {
                    'theme': settings.theme,
                    'date_format': settings.date_format,
                    'number_format': settings.number_format,
                    'page_size': settings.page_size,
                    'saved_filters': settings.saved_filters or {}
                }
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Ошибка при получении настроек: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        """Обновить настройки пользователя"""
        try:
            settings = UserSettings.get_or_create_for_user(request.user)
            
            # Обновляем только переданные поля
            if 'theme' in request.data:
                settings.theme = request.data['theme']
            if 'date_format' in request.data:
                settings.date_format = request.data['date_format']
            if 'number_format' in request.data:
                settings.number_format = request.data['number_format']
            if 'page_size' in request.data:
                page_size = int(request.data['page_size'])
                if page_size > 0:
                    settings.page_size = page_size
            if 'saved_filters' in request.data:
                # Объединяем существующие фильтры с новыми (чтобы не потерять другие сохраненные фильтры)
                current_filters = settings.saved_filters or {}
                if isinstance(request.data['saved_filters'], dict):
                    current_filters.update(request.data['saved_filters'])
                    settings.saved_filters = current_filters
                else:
                    settings.saved_filters = request.data['saved_filters']
            
            settings.save()
            
            return Response({
                'success': True,
                'message': 'Настройки сохранены',
                'settings': {
                    'theme': settings.theme,
                    'date_format': settings.date_format,
                    'number_format': settings.number_format,
                    'page_size': settings.page_size,
                    'saved_filters': settings.saved_filters or {}
                }
            })
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Ошибка при сохранении настроек: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
