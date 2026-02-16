"""
Модуль для шифрования чувствительных данных в базе данных.
Использует Fernet (симметричное шифрование) из библиотеки cryptography.
"""
import os
import base64
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Опциональный импорт cryptography
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False
    logger.warning('Библиотека cryptography не установлена. Шифрование отключено.')


class DataEncryption:
    """
    Класс для шифрования и расшифровки данных.
    Использует ключ из настроек Django или генерирует новый.
    """
    
    _fernet_instance = None
    
    @classmethod
    def _get_encryption_key(cls):
        """
        Получает ключ шифрования из настроек или генерирует новый.
        Ключ должен быть в settings.ENCRYPTION_KEY или в переменной окружения.
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            return None
            
        # Пытаемся получить ключ из настроек
        key = getattr(settings, 'ENCRYPTION_KEY', None)
        
        if not key:
            # Пытаемся получить из переменной окружения
            key = os.environ.get('ENCRYPTION_KEY', None)
        
        if not key:
            # Генерируем ключ на основе SECRET_KEY Django
            secret_key = settings.SECRET_KEY.encode()
            salt = b'mptcourse_salt_2024'  # Соль для генерации ключа
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(secret_key))
        else:
            # Если ключ уже есть, убеждаемся что он в правильном формате
            if isinstance(key, str):
                key = key.encode()
            # Если ключ не в base64, конвертируем
            try:
                base64.urlsafe_b64decode(key)
            except Exception:
                # Генерируем ключ из строки
                secret_key = key
                salt = b'mptcourse_salt_2024'
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=100000,
                )
                key = base64.urlsafe_b64encode(kdf.derive(secret_key))
        
        return key
    
    @classmethod
    def _get_fernet(cls):
        """Получает экземпляр Fernet для шифрования/расшифровки."""
        if not CRYPTOGRAPHY_AVAILABLE:
            return None
        if cls._fernet_instance is None:
            key = cls._get_encryption_key()
            if key:
                cls._fernet_instance = Fernet(key)
        return cls._fernet_instance
    
    @classmethod
    def encrypt(cls, data):
        """
        Шифрует данные.
        
        Args:
            data: Строка или bytes для шифрования
            
        Returns:
            bytes: Зашифрованные данные в base64
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            # Если cryptography не установлен, возвращаем данные как есть
            if isinstance(data, str):
                return data.encode('utf-8')
            return data
            
        if data is None:
            return None
        
        try:
            if isinstance(data, str):
                data = data.encode('utf-8')
            
            fernet = cls._get_fernet()
            if fernet:
                encrypted = fernet.encrypt(data)
                return encrypted
            # Если fernet не доступен, возвращаем данные как есть
            return data
        except Exception as e:
            logger.error(f"Ошибка при шифровании данных: {str(e)}")
            # Возвращаем данные как есть вместо ошибки
            if isinstance(data, str):
                return data.encode('utf-8')
            return data
    
    @classmethod
    def decrypt(cls, encrypted_data):
        """
        Расшифровывает данные.
        
        Args:
            encrypted_data: Зашифрованные данные (bytes или base64 строка)
            
        Returns:
            str: Расшифрованная строка
        """
        if not CRYPTOGRAPHY_AVAILABLE:
            # Если cryptography не установлен, возвращаем данные как есть
            if encrypted_data is None:
                return None
            if isinstance(encrypted_data, bytes):
                try:
                    return encrypted_data.decode('utf-8')
                except:
                    return str(encrypted_data)
            return str(encrypted_data)
            
        if encrypted_data is None:
            return None
        
        try:
            if isinstance(encrypted_data, str):
                # Пытаемся декодировать из base64 строки
                try:
                    encrypted_data = base64.urlsafe_b64decode(encrypted_data.encode())
                except Exception:
                    encrypted_data = encrypted_data.encode()
            
            fernet = cls._get_fernet()
            if fernet:
                decrypted = fernet.decrypt(encrypted_data)
                return decrypted.decode('utf-8')
            # Если fernet не доступен, возвращаем данные как есть
            if isinstance(encrypted_data, bytes):
                try:
                    return encrypted_data.decode('utf-8')
                except:
                    pass
            return str(encrypted_data)
        except Exception as e:
            logger.error(f"Ошибка при расшифровке данных: {str(e)}")
            # Возвращаем исходные данные, если расшифровка не удалась
            # (для обратной совместимости с незашифрованными данными)
            if isinstance(encrypted_data, bytes):
                try:
                    return encrypted_data.decode('utf-8')
                except:
                    pass
            return str(encrypted_data)
    
    @classmethod
    def encrypt_field(cls, value):
        """
        Шифрует значение поля модели.
        Возвращает base64 строку для хранения в БД.
        """
        if value is None or value == '':
            return None
        
        if not CRYPTOGRAPHY_AVAILABLE:
            # Если cryptography не установлен, возвращаем значение как есть
            return str(value)
        
        encrypted = cls.encrypt(str(value))
        # Конвертируем в строку для хранения в БД
        if isinstance(encrypted, bytes):
            return base64.urlsafe_b64encode(encrypted).decode('utf-8')
        return str(encrypted)
    
    @classmethod
    def decrypt_field(cls, encrypted_value):
        """
        Расшифровывает значение поля модели.
        Принимает base64 строку из БД.
        """
        if encrypted_value is None or encrypted_value == '':
            return None
        
        if not CRYPTOGRAPHY_AVAILABLE:
            # Если cryptography не установлен, возвращаем значение как есть
            return encrypted_value
        
        try:
            # Декодируем из base64
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_value.encode('utf-8'))
            return cls.decrypt(encrypted_bytes)
        except Exception:
            # Если не удалось расшифровать, возвращаем исходное значение
            # (для обратной совместимости)
            return encrypted_value


# Декораторы для автоматического шифрования/расшифровки полей моделей
def encrypted_field(func):
    """
    Декоратор для свойств моделей, которые должны автоматически шифроваться/расшифровываться.
    """
    def wrapper(self):
        encrypted_value = func(self)
        if encrypted_value:
            return DataEncryption.decrypt_field(encrypted_value)
        return encrypted_value
    return wrapper

