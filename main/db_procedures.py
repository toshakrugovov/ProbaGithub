"""
Модуль для работы с хранимыми процедурами PostgreSQL.
Предоставляет удобные функции для вызова хранимых процедур из Django кода.
"""
from django.db import connection
from decimal import Decimal
import json
from typing import Dict, Any, Optional


def calculate_order_total(order_id: int) -> Decimal:
    """
    Вызывает хранимую процедуру calculate_order_total для расчета итоговой суммы заказа.
    
    Args:
        order_id: ID заказа
        
    Returns:
        Decimal: Итоговая сумма заказа
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT calculate_order_total(%s)", [order_id])
        result = cursor.fetchone()
        return Decimal(str(result[0])) if result and result[0] else Decimal('0.00')


def apply_promo_to_order(order_id: int, promo_code: str, user_id: int) -> Dict[str, Any]:
    """
    Вызывает хранимую процедуру apply_promo_to_order для применения промокода к заказу.
    
    Args:
        order_id: ID заказа
        promo_code: Код промокода
        user_id: ID пользователя
        
    Returns:
        dict: Результат операции с ключами 'success', 'error' или 'discount', 'discount_amount'
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT apply_promo_to_order(%s, %s, %s)",
            [order_id, promo_code, user_id]
        )
        result = cursor.fetchone()
        if result and result[0]:
            return json.loads(result[0])
        return {'success': False, 'error': 'Неизвестная ошибка'}


def update_user_balance(
    user_id: int,
    amount: Decimal,
    transaction_type: str,
    description: Optional[str] = None,
    order_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Вызывает хранимую процедуру update_user_balance для обновления баланса пользователя.
    
    Args:
        user_id: ID пользователя
        amount: Сумма транзакции
        transaction_type: Тип транзакции ('deposit', 'withdrawal', 'order_payment', 'order_refund')
        description: Описание транзакции (опционально)
        order_id: ID заказа (опционально)
        
    Returns:
        dict: Результат операции с ключами 'success', 'error' или 'balance_before', 'balance_after', 'transaction_id'
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT update_user_balance(%s, %s, %s, %s, %s)",
            [user_id, str(amount), transaction_type, description, order_id]
        )
        result = cursor.fetchone()
        if result and result[0]:
            return json.loads(result[0])
        return {'success': False, 'error': 'Неизвестная ошибка'}


def get_order_summary(order_id: Optional[int] = None) -> list:
    """
    Получает данные из представления v_order_summary.
    
    Args:
        order_id: ID заказа (опционально, если None - возвращает все заказы)
        
    Returns:
        list: Список словарей с данными о заказах
    """
    with connection.cursor() as cursor:
        if order_id:
            cursor.execute("SELECT * FROM v_order_summary WHERE order_id = %s", [order_id])
        else:
            cursor.execute("SELECT * FROM v_order_summary ORDER BY order_date DESC")
        
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_product_sales_stats(product_id: Optional[int] = None) -> list:
    """
    Получает данные из представления v_product_sales_stats.
    
    Args:
        product_id: ID товара (опционально, если None - возвращает все товары)
        
    Returns:
        list: Список словарей со статистикой продаж товаров
    """
    with connection.cursor() as cursor:
        if product_id:
            cursor.execute("SELECT * FROM v_product_sales_stats WHERE product_id = %s", [product_id])
        else:
            cursor.execute("SELECT * FROM v_product_sales_stats ORDER BY total_revenue DESC")
        
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_user_balance_summary(user_id: Optional[int] = None) -> list:
    """
    Получает данные из представления v_user_balance_summary.
    
    Args:
        user_id: ID пользователя (опционально, если None - возвращает всех пользователей)
        
    Returns:
        list: Список словарей со сводкой по балансам пользователей
    """
    with connection.cursor() as cursor:
        if user_id:
            cursor.execute("SELECT * FROM v_user_balance_summary WHERE user_id = %s", [user_id])
        else:
            cursor.execute("SELECT * FROM v_user_balance_summary ORDER BY current_balance DESC")
        
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

