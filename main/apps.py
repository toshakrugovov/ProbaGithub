from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'
    
    # Инициализация обязательных записей происходит автоматически
    # через метод get_account() модели OrganizationAccount
    # и при восстановлении из бэкапа через initialize_required_records()


