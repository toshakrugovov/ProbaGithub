"""
Миксины и поля для автоматического шифрования чувствительных данных в моделях.
"""
from django.db import models
from django.conf import settings
from .encryption import DataEncryption
import logging

logger = logging.getLogger(__name__)


class EncryptedCharField(models.TextField):
    """
    Поле модели, которое автоматически шифрует данные при сохранении
    и расшифровывает при чтении.
    """
    
    def __init__(self, *args, **kwargs):
        # Всегда используем TextField для хранения зашифрованных данных
        # (они могут быть длиннее оригинальных)
        kwargs.setdefault('max_length', None)
        super().__init__(*args, **kwargs)
    
    def from_db_value(self, value, expression, connection):
        """Расшифровывает значение при чтении из БД."""
        if value is None:
            return value
        
        if getattr(settings, 'ENABLE_DATA_ENCRYPTION', True):
            try:
                return DataEncryption.decrypt_field(value)
            except Exception as e:
                logger.warning(f"Не удалось расшифровать поле: {str(e)}")
                # Возвращаем исходное значение для обратной совместимости
                return value
        return value
    
    def to_python(self, value):
        """Конвертирует значение в Python объект."""
        if value is None:
            return value
        return str(value)
    
    def get_prep_value(self, value):
        """Шифрует значение перед сохранением в БД."""
        if value is None:
            return value
        
        if getattr(settings, 'ENABLE_DATA_ENCRYPTION', True):
            try:
                return DataEncryption.encrypt_field(str(value))
            except Exception as e:
                logger.error(f"Ошибка при шифровании поля: {str(e)}")
                raise
        return str(value)


class EncryptedTextField(models.TextField):
    """
    Текстовое поле модели с автоматическим шифрованием.
    """
    
    def from_db_value(self, value, expression, connection):
        """Расшифровывает значение при чтении из БД."""
        if value is None:
            return value
        
        if getattr(settings, 'ENABLE_DATA_ENCRYPTION', True):
            try:
                return DataEncryption.decrypt_field(value)
            except Exception as e:
                logger.warning(f"Не удалось расшифровать поле: {str(e)}")
                return value
        return value
    
    def to_python(self, value):
        """Конвертирует значение в Python объект."""
        if value is None:
            return value
        return str(value)
    
    def get_prep_value(self, value):
        """Шифрует значение перед сохранением в БД."""
        if value is None:
            return value
        
        if getattr(settings, 'ENABLE_DATA_ENCRYPTION', True):
            try:
                return DataEncryption.encrypt_field(str(value))
            except Exception as e:
                logger.error(f"Ошибка при шифровании поля: {str(e)}")
                raise
        return str(value)


class EncryptedModelMixin:
    """
    Миксин для моделей, которые содержат чувствительные данные.
    Автоматически шифрует/расшифровывает указанные поля.
    """
    
    # Список полей, которые нужно шифровать
    # Переопределите в дочерних классах
    encrypted_fields = []
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._encryption_enabled = getattr(settings, 'ENABLE_DATA_ENCRYPTION', True)
    
    def save(self, *args, **kwargs):
        """Переопределяем save для шифрования полей перед сохранением."""
        if self._encryption_enabled and self.encrypted_fields:
            for field_name in self.encrypted_fields:
                if hasattr(self, field_name):
                    value = getattr(self, field_name)
                    if value:
                        try:
                            encrypted = DataEncryption.encrypt_field(str(value))
                            setattr(self, field_name, encrypted)
                        except Exception as e:
                            logger.error(f"Ошибка при шифровании поля {field_name}: {str(e)}")
        
        super().save(*args, **kwargs)
    
    def _decrypt_field(self, field_name):
        """Расшифровывает поле при чтении."""
        if not self._encryption_enabled:
            return getattr(self, field_name)
        
        value = getattr(self, field_name)
        if value and field_name in self.encrypted_fields:
            try:
                return DataEncryption.decrypt_field(value)
            except Exception as e:
                logger.warning(f"Не удалось расшифровать поле {field_name}: {str(e)}")
                return value
        return value

