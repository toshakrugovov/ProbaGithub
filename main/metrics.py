"""
Кастомные метрики для мониторинга работы интернет-магазина MPTCOURSE.
Метрики экспортируются в формате Prometheus для визуализации в Grafana.
Реализация без использования prometheus_client библиотеки.

ВАЖНО: Все метрики экспортируются как GAUGE (текущее значение).
Их можно использовать напрямую в Grafana БЕЗ rate():
  - mptcourse_users_total{job="django"}
  - mptcourse_orders_count{job="django"} by (status)
  - mptcourse_products_total{job="django"}

Для получения целых чисел за период используйте increase():
  - sum(increase(django_http_requests_total{job="django"}[5m]))
"""

from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from collections import defaultdict

from .models import (
    User, UserProfile, Order, Course, Cart, CartItem,
    CourseFavorite, OrderItem
)


class Gauge:
    """
    Простой класс для хранения метрик типа Gauge.
    Gauge - это метрика, которая может увеличиваться и уменьшаться.
    """
    def __init__(self, name, description, labels=None):
        self.name = name
        self.description = description
        self.label_names = labels or []  # Список имен лейблов
        self.values = {}  # {(label1=value1, label2=value2): value}
    
    def labels(self, **kwargs):
        """Создает метрику с конкретными значениями лейблов"""
        return LabeledGauge(self, kwargs)
    
    def set(self, value, **label_values):
        """Устанавливает значение метрики"""
        if label_values:
            key = tuple(sorted(label_values.items()))
            self.values[key] = float(value)
        else:
            # Метрика без лейблов
            self.values[()] = float(value)
    
    def get_prometheus_format(self):
        """Возвращает метрику в формате Prometheus"""
        lines = []
        # HELP строка
        lines.append(f"# HELP {self.name} {self.description}")
        # TYPE строка
        lines.append(f"# TYPE {self.name} gauge")
        
        # Значения метрики
        for label_tuple, value in self.values.items():
            if label_tuple:
                # Есть лейблы
                label_str = ",".join([f'{k}="{v}"' for k, v in sorted(label_tuple)])
                lines.append(f"{self.name}{{{label_str}}} {value}")
            else:
                # Нет лейблов
                lines.append(f"{self.name} {value}")
        
        return "\n".join(lines) + "\n"


class LabeledGauge:
   
    def __init__(self, gauge, label_values):
        self.gauge = gauge
        self.label_values = label_values
    
    def set(self, value):
    
        self.gauge.set(value, **self.label_values)


class UserMetrics:
    
    
    def __init__(self):
     
        self.total_users = Gauge(
            'mptcourse_users_total',
            'Общее количество зарегистрированных пользователей',
            ['status']  # status: 'all', 'active', 'blocked'
        )
        
        
        self.active_users = Gauge(
            'mptcourse_active_users_count',
            'Количество активных пользователей за последние 30 дней'
        )
        
     
        self.users_with_profiles = Gauge(
            'mptcourse_users_with_profiles',
            'Количество пользователей с заполненными профилями'
        )
    
    def update_metrics(self):
      
        try:
            
            total_count = User.objects.count()
            self.total_users.set(total_count, status='all')
            
           
            active_count = User.objects.filter(is_active=True).count()
            self.total_users.set(active_count, status='active')
            
            blocked_count = User.objects.filter(is_active=False).count()
            self.total_users.set(blocked_count, status='blocked')
            
   
            thirty_days_ago = timezone.now() - timedelta(days=30)
            recent_users = User.objects.filter(
                Q(date_joined__gte=thirty_days_ago) | 
                Q(profile__registered_at__gte=thirty_days_ago)
            ).distinct().count()
            self.active_users.set(recent_users)
            
            # Пользователи с профилями
            users_with_profiles_count = UserProfile.objects.count()
            self.users_with_profiles.set(users_with_profiles_count)
            
        except Exception as e:
            # В случае ошибки не прерываем работу, просто логируем
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при обновлении метрик пользователей: {e}")


class OrderMetrics:

    
    def __init__(self):
     
        self.orders_by_status = Gauge(
            'mptcourse_orders_count',
            'Количество заказов по статусам',
            ['status']  
        )
        
      
        self.total_orders_amount = Gauge(
            'mptcourse_orders_total_amount',
            'Общая сумма всех заказов в рублях'
        )
        
     
        self.orders_last_24h = Gauge(
            'mptcourse_orders_last_24h',
            'Количество заказов за последние 24 часа'
        )
        
        self.average_order_amount = Gauge(
            'mptcourse_average_order_amount',
            'Средняя стоимость заказа в рублях'
        )
        
        self.delivered_orders_amount = Gauge(
            'mptcourse_delivered_orders_amount',
            'Общая сумма доставленных заказов в рублях'
        )
    
    def update_metrics(self):
  
        try:
         
            statuses = ['processing', 'paid', 'shipped', 'delivered', 'cancelled']
            for status in statuses:
                count = Order.objects.filter(order_status=status).count()
                self.orders_by_status.set(count, status=status)
            
           
            total_amount_result = Order.objects.aggregate(
                total=Sum('total_amount')
            )
            total_amount = float(total_amount_result['total'] or Decimal('0'))
            self.total_orders_amount.set(total_amount)
            
        
            twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
            orders_24h = Order.objects.filter(created_at__gte=twenty_four_hours_ago).count()
            self.orders_last_24h.set(orders_24h)
            
           
            avg_result = Order.objects.aggregate(avg=Avg('total_amount'))
            if avg_result['avg'] is not None:
                avg_amount = float(avg_result['avg'])
            else:
                avg_amount = 0.0
            self.average_order_amount.set(avg_amount)
            
        
            delivered_amount_result = Order.objects.filter(
                order_status='delivered'
            ).aggregate(total=Sum('total_amount'))
            delivered_amount = float(delivered_amount_result['total'] or Decimal('0'))
            self.delivered_orders_amount.set(delivered_amount)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при обновлении метрик заказов: {e}")


class CatalogMetrics:
    
    def __init__(self):
     
        self.total_products = Gauge(
            'mptcourse_products_total',
            'Общее количество товаров в каталоге'
        )
        
    
        self.available_products = Gauge(
            'mptcourse_products_available',
            'Количество товаров в наличии'
        )
        

        self.products_in_carts = Gauge(
            'mptcourse_products_in_carts',
            'Общее количество товаров в корзинах пользователей'
        )
        
       
        self.unique_products_in_carts = Gauge(
            'mptcourse_unique_products_in_carts',
            'Количество уникальных товаров в корзинах'
        )
        
  
        self.products_in_favorites = Gauge(
            'mptcourse_products_in_favorites',
            'Общее количество товаров в избранном у всех пользователей'
        )
        
      
        self.unique_products_in_favorites = Gauge(
            'mptcourse_unique_products_in_favorites',
            'Количество уникальных товаров в избранном'
        )
        
        # Общая стоимость товаров в корзинах
        self.carts_total_value = Gauge(
            'mptcourse_carts_total_value',
            'Общая стоимость всех товаров в корзинах в рублях'
        )
    
    def update_metrics(self):
        """Обновляет все метрики каталога"""
        try:
            # Общее количество курсов
            total_products = Course.objects.count()
            self.total_products.set(total_products)
            
            # Доступные курсы
            available_products = Course.objects.filter(is_available=True).count()
            self.available_products.set(available_products)
            
            # Курсы в корзинах
            cart_items = CartItem.objects.all()
            total_items_in_carts = cart_items.aggregate(
                total=Sum('quantity')
            )['total'] or 0
            self.products_in_carts.set(total_items_in_carts)
            
            # Уникальные курсы в корзинах
            unique_products = cart_items.values('course').distinct().count()
            self.unique_products_in_carts.set(unique_products)
            
            # Курсы в избранном
            total_favorites = CourseFavorite.objects.count()
            self.products_in_favorites.set(total_favorites)
            
            # Уникальные курсы в избранном
            unique_favorites = CourseFavorite.objects.values('course').distinct().count()
            self.unique_products_in_favorites.set(unique_favorites)
            
            # Общая стоимость товаров в корзинах
            carts_value = Decimal('0')
            for cart in Cart.objects.all():
                carts_value += cart.total_price()
            self.carts_total_value.set(float(carts_value))
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при обновлении метрик каталога: {e}")


# Создаем глобальные экземпляры метрик
user_metrics = UserMetrics()
order_metrics = OrderMetrics()
catalog_metrics = CatalogMetrics()


def update_all_metrics():
    """Обновляет все метрики приложения"""
    user_metrics.update_metrics()
    order_metrics.update_metrics()
    catalog_metrics.update_metrics()


def get_all_metrics_prometheus_format():
    """
    Возвращает все метрики в формате Prometheus.
    
    Returns:
        str: Строка с метриками в формате Prometheus
    """
    # Обновляем метрики перед экспортом
    update_all_metrics()
    
    # Собираем все метрики
    metrics_output = []
    
    # Метрики пользователей
    metrics_output.append(user_metrics.total_users.get_prometheus_format())
    metrics_output.append(user_metrics.active_users.get_prometheus_format())
    metrics_output.append(user_metrics.users_with_profiles.get_prometheus_format())
    
    # Метрики заказов
    metrics_output.append(order_metrics.orders_by_status.get_prometheus_format())
    metrics_output.append(order_metrics.total_orders_amount.get_prometheus_format())
    metrics_output.append(order_metrics.orders_last_24h.get_prometheus_format())
    metrics_output.append(order_metrics.average_order_amount.get_prometheus_format())
    metrics_output.append(order_metrics.delivered_orders_amount.get_prometheus_format())
    
    # Метрики каталога
    metrics_output.append(catalog_metrics.total_products.get_prometheus_format())
    metrics_output.append(catalog_metrics.available_products.get_prometheus_format())
    metrics_output.append(catalog_metrics.products_in_carts.get_prometheus_format())
    metrics_output.append(catalog_metrics.unique_products_in_carts.get_prometheus_format())
    metrics_output.append(catalog_metrics.products_in_favorites.get_prometheus_format())
    metrics_output.append(catalog_metrics.unique_products_in_favorites.get_prometheus_format())
    metrics_output.append(catalog_metrics.carts_total_value.get_prometheus_format())
    
    return "".join(metrics_output)
