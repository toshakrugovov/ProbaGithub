"""
Прослойка данных (Data Access Layer) для безопасной работы с базой данных.
Обеспечивает защиту от SQL инъекций и централизованный доступ к данным.
"""
from django.db import models, connection
from django.db.models import Q, QuerySet
from django.core.exceptions import ValidationError, PermissionDenied
import logging
from typing import Optional, List, Dict, Any
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


class SafeQueryBuilder:
    """
    Безопасный построитель запросов с защитой от SQL инъекций.
    Всегда использует параметризованные запросы Django ORM.
    """
    
    @staticmethod
    def sanitize_string(value: str, max_length: Optional[int] = None) -> str:
        """
        Очищает строку от потенциально опасных символов.
        Django ORM уже защищает от SQL инъекций, но это дополнительная проверка.
        """
        if not isinstance(value, str):
            raise ValueError("Значение должно быть строкой")
        
        # Удаляем нулевые байты и другие опасные символы
        value = value.replace('\x00', '')
        value = value.replace('\r', '')
        value = value.strip()
        
        if max_length and len(value) > max_length:
            value = value[:max_length]
        
        return value
    
    @staticmethod
    def sanitize_integer(value: Any) -> int:
        """Безопасно конвертирует значение в целое число."""
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ValueError(f"Некорректное значение для целого числа: {value}")
    
    @staticmethod
    def sanitize_decimal(value: Any) -> Decimal:
        """Безопасно конвертирует значение в Decimal."""
        try:
            return Decimal(str(value))
        except (ValueError, TypeError, InvalidOperation):
            raise ValueError(f"Некорректное значение для Decimal: {value}")
    
    @staticmethod
    def build_filter_query(model_class, filters: Dict[str, Any]) -> Q:
        """
        Строит безопасный фильтр запроса используя Django ORM.
        
        Args:
            model_class: Класс модели Django
            filters: Словарь с фильтрами {поле: значение}
            
        Returns:
            Q объект для использования в filter()
        """
        query = Q()
        
        for field_name, value in filters.items():
            # Проверяем, что поле существует в модели
            if not hasattr(model_class, field_name):
                logger.warning(f"Поле {field_name} не найдено в модели {model_class.__name__}")
                continue
            
            field = model_class._meta.get_field(field_name)
            
            # Обрабатываем разные типы полей
            if isinstance(field, models.CharField) or isinstance(field, models.TextField):
                value = SafeQueryBuilder.sanitize_string(value)
                query &= Q(**{field_name: value})
            elif isinstance(field, models.IntegerField) or isinstance(field, models.BigIntegerField):
                value = SafeQueryBuilder.sanitize_integer(value)
                query &= Q(**{field_name: value})
            elif isinstance(field, models.DecimalField):
                value = SafeQueryBuilder.sanitize_decimal(value)
                query &= Q(**{field_name: value})
            else:
                # Для других типов полей используем как есть (Django ORM защитит)
                query &= Q(**{field_name: value})
        
        return query


class DataAccessLayer:
    """
    Прослойка данных для безопасного доступа к моделям.
    Все методы используют Django ORM, который автоматически защищает от SQL инъекций.
    """
    
    @staticmethod
    def safe_get(model_class, **kwargs):
        """
        Безопасное получение одного объекта модели.
        Использует get() с параметризованными запросами.
        """
        try:
            # Django ORM автоматически использует параметризованные запросы
            return model_class.objects.get(**kwargs)
        except model_class.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении объекта {model_class.__name__}: {str(e)}")
            raise
    
    @staticmethod
    def safe_filter(model_class, filters: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Безопасная фильтрация объектов модели.
        
        Args:
            model_class: Класс модели
            filters: Словарь с фильтрами
            **kwargs: Дополнительные фильтры
            
        Returns:
            QuerySet с отфильтрованными объектами
        """
        query = Q()
        
        if filters:
            query = SafeQueryBuilder.build_filter_query(model_class, filters)
        
        # Добавляем дополнительные фильтры из kwargs
        if kwargs:
            for key, value in kwargs.items():
                if hasattr(model_class, key):
                    query &= Q(**{key: value})
        
        return model_class.objects.filter(query)
    
    @staticmethod
    def safe_create(model_class, data: Dict[str, Any], **kwargs):
        """
        Безопасное создание объекта модели.
        
        Args:
            model_class: Класс модели
            data: Словарь с данными для создания
            **kwargs: Дополнительные поля
            
        Returns:
            Созданный объект модели
        """
        # Объединяем данные
        create_data = {**data, **kwargs}
        
        # Валидация данных
        instance = model_class(**create_data)
        instance.full_clean()  # Вызывает валидацию модели
        
        # Сохранение через ORM (защита от SQL инъекций)
        instance.save()
        return instance
    
    @staticmethod
    def safe_update(instance, data: Dict[str, Any], **kwargs):
        """
        Безопасное обновление объекта модели.
        
        Args:
            instance: Экземпляр модели
            data: Словарь с данными для обновления
            **kwargs: Дополнительные поля
            
        Returns:
            Обновленный объект модели
        """
        # Объединяем данные
        update_data = {**data, **kwargs}
        
        # Обновляем поля
        for key, value in update_data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        
        # Валидация
        instance.full_clean()
        
        # Сохранение через ORM
        instance.save()
        return instance
    
    @staticmethod
    def safe_delete(instance):
        """
        Безопасное удаление объекта модели.
        """
        try:
            instance.delete()
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении объекта: {str(e)}")
            raise
    
    @staticmethod
    def safe_bulk_create(model_class, objects_data: List[Dict[str, Any]]):
        """
        Безопасное массовое создание объектов.
        
        Args:
            model_class: Класс модели
            objects_data: Список словарей с данными для создания
            
        Returns:
            Список созданных объектов
        """
        objects = []
        for data in objects_data:
            obj = model_class(**data)
            obj.full_clean()
            objects.append(obj)
        
        return model_class.objects.bulk_create(objects)
    
    @staticmethod
    def safe_raw_query(query: str, params: Optional[List[Any]] = None):
        """
        Безопасное выполнение сырого SQL запроса с параметрами.
        ВАЖНО: Используйте только когда Django ORM недостаточно.
        Всегда используйте параметризованные запросы!
        
        Args:
            query: SQL запрос с плейсхолдерами %s
            params: Список параметров для подстановки
            
        Returns:
            Результат запроса
        """
        if params is None:
            params = []
        
        # Проверяем, что запрос использует параметризацию
        if '%s' not in query and '?' not in query:
            logger.warning("Сырой SQL запрос без параметров! Это может быть небезопасно.")
        
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()
    
    @staticmethod
    def validate_user_permission(user, required_permission: str = None):
        """
        Проверяет права пользователя перед выполнением операции.
        
        Args:
            user: Пользователь Django
            required_permission: Требуемое право доступа
            
        Raises:
            PermissionDenied: Если у пользователя нет прав
        """
        if not user or not user.is_authenticated:
            raise PermissionDenied("Пользователь не аутентифицирован")
        
        if required_permission:
            # Здесь можно добавить проверку конкретных прав
            if user.is_superuser:
                return True
            
            # Проверка прав через профиль пользователя
            if hasattr(user, 'profile') and user.profile:
                # Добавьте свою логику проверки прав
                pass
        
        return True


# Утилиты для работы с транзакциями
class TransactionManager:
    """
    Менеджер транзакций для безопасной работы с БД.
    """
    
    @staticmethod
    def execute_in_transaction(func, *args, **kwargs):
        """
        Выполняет функцию в транзакции БД.
        При ошибке автоматически откатывает изменения.
        """
        from django.db import transaction
        
        try:
            with transaction.atomic():
                return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в транзакции: {str(e)}")
            raise


# Декоратор для автоматической проверки прав доступа
def require_permission(permission: str = None):
    """
    Декоратор для проверки прав доступа перед выполнением функции.
    """
    def decorator(func):
        def wrapper(request, *args, **kwargs):
            DataAccessLayer.validate_user_permission(request.user, permission)
            return func(request, *args, **kwargs)
        return wrapper
    return decorator

