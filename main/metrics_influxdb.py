import os
import time

try:
    import influxdb_client
    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import SYNCHRONOUS
except ModuleNotFoundError:
    influxdb_client = None
    InfluxDBClient = None
    Point = None
    SYNCHRONOUS = None

from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .models import (
    User, UserProfile, Order, Course, Cart, CartItem,
    CourseFavorite, OrderItem
)


token = os.environ.get("INFLUXDB_TOKEN") or "w2VtilYKU2XvyAcIEtBGAS2Lm8yNDDQH6rDP9CwL1mA6_Br82_gXNoVORzvh108qpaPWRvTdbJGktqYhjHUrKg=="
org = os.environ.get("INFLUXDB_ORG", "MPT")

url = os.environ.get("INFLUXDB_URL") or "http://influx-db:8086"
bucket = os.environ.get("INFLUXDB_BUCKET", "Metrics")



if not token:
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("INFLUXDB_TOKEN не установлен! Метрики не будут отправляться в InfluxDB.")


write_client = None
write_api = None

if influxdb_client is not None and InfluxDBClient is not None and SYNCHRONOUS is not None:
    try:
        write_client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)
        write_api = write_client.write_api(write_options=SYNCHRONOUS)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при инициализации InfluxDB клиента: {e}", exc_info=True)


class UserMetrics:
    def __init__(self):
        pass
    
    def update_metrics(self):
       
        if not write_api:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("InfluxDB клиент не инициализирован. Пропуск отправки метрик.")
            return
            
        import logging
        logger = logging.getLogger(__name__)
        
        try:
        
            total_count = User.objects.count()
            point = (
                Point("mptcourse_users_total")
                .tag("status", "все")
                .field("value", float(total_count))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
       
            active_count = User.objects.filter(is_active=True).count()
            point = (
                Point("mptcourse_users_total")
                .tag("status", "активные")
                .field("value", float(active_count))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
     
            blocked_count = User.objects.filter(is_active=False).count()
            point = (
                Point("mptcourse_users_total")
                .tag("status", "заблокированные")
                .field("value", float(blocked_count))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
         
            thirty_days_ago = timezone.now() - timedelta(days=30)
            recent_users = User.objects.filter(
                Q(date_joined__gte=thirty_days_ago) | 
                Q(profile__registered_at__gte=thirty_days_ago)
            ).distinct().count()
            point = (
                Point("mptcourse_active_users_count")
                .field("value", float(recent_users))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
            # Пользователи с профилями
            users_with_profiles_count = UserProfile.objects.count()
            point = (
                Point("mptcourse_users_with_profiles")
                .field("value", float(users_with_profiles_count))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
        except Exception as e:
           
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при обновлении метрик пользователей: {e}", exc_info=True)


class OrderMetrics:

    def __init__(self):
        pass
    
    def update_metrics(self):
      
        if not write_api:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("InfluxDB клиент не инициализирован. Пропуск отправки метрик.")
            return
            
        import logging
        logger = logging.getLogger(__name__)
        
        try:
           
            status_mapping = {
                'processing': 'обработка',
                'paid': 'оплачен',
                'shipped': 'отправлен',
                'delivered': 'доставлен',
                'cancelled': 'отменен'
            }
            for status_en, status_ru in status_mapping.items():
                count = Order.objects.filter(order_status=status_en).count()
                point = (
                    Point("mptcourse_orders_count")
                    .tag("status", status_ru)
                    .field("value", float(count))
                )
                write_api.write(bucket=bucket, org=org, record=point)
            
           
            total_amount_result = Order.objects.aggregate(
                total=Sum('total_amount')
            )
            total_amount = float(total_amount_result['total'] or Decimal('0'))
            point = (
                Point("mptcourse_orders_total_amount")
                .field("value", total_amount)
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
        
            twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
            orders_24h = Order.objects.filter(created_at__gte=twenty_four_hours_ago).count()
            point = (
                Point("mptcourse_orders_last_24h")
                .field("value", float(orders_24h))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
       
            status_mapping_avg = {
                'processing': 'обработка',
                'paid': 'оплачен',
                'shipped': 'отправлен',
                'delivered': 'доставлен'
            }
            for status_en, status_ru in status_mapping_avg.items():
                status_avg_result = Order.objects.filter(order_status=status_en).aggregate(avg=Avg('total_amount'))
                if status_avg_result['avg'] is not None:
                    status_avg_amount = float(status_avg_result['avg'])
                    point = (
                        Point("mptcourse_average_order_amount")
                        .tag("status", status_ru)
                        .field("value", status_avg_amount)
                    )
                    write_api.write(bucket=bucket, org=org, record=point)
            
     
            delivered_amount_result = Order.objects.filter(
                order_status='delivered'
            ).aggregate(total=Sum('total_amount'))
            delivered_amount = float(delivered_amount_result['total'] or Decimal('0'))
            point = (
                Point("mptcourse_delivered_orders_amount")
                .field("value", delivered_amount)
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при обновлении метрик заказов: {e}", exc_info=True)


class CatalogMetrics:
    def __init__(self):
        pass
    
    def update_metrics(self):
        """Обновляет все метрики каталога и отправляет в InfluxDB"""
        if not write_api:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("InfluxDB клиент не инициализирован. Пропуск отправки метрик.")
            return
            
        import logging
        logger = logging.getLogger(__name__)
        
        try:
        
            total_products = Course.objects.count()
            point = (
                Point("mptcourse_products_total")
                .field("value", float(total_products))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
            available_products = Course.objects.filter(is_available=True).count()
            point = (
                Point("mptcourse_products_available")
                .field("value", float(available_products))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
         
            cart_items = CartItem.objects.all()
            total_items_in_carts = cart_items.aggregate(
                total=Sum('quantity')
            )['total'] or 0
            point = (
                Point("mptcourse_products_in_carts")
                .field("value", float(total_items_in_carts))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
   
            unique_products = cart_items.values('course').distinct().count()
            point = (
                Point("mptcourse_unique_products_in_carts")
                .field("value", float(unique_products))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
       
            total_favorites = CourseFavorite.objects.count()
            point = (
                Point("mptcourse_products_in_favorites")
                .field("value", float(total_favorites))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
  
            unique_favorites = CourseFavorite.objects.values('course').distinct().count()
            point = (
                Point("mptcourse_unique_products_in_favorites")
                .field("value", float(unique_favorites))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            

            carts_value = Decimal('0')
            for cart in Cart.objects.all():
                carts_value += cart.total_price()
            point = (
                Point("mptcourse_carts_total_value")
                .field("value", float(carts_value))
            )
            write_api.write(bucket=bucket, org=org, record=point)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при обновлении метрик каталога: {e}", exc_info=True)



user_metrics = UserMetrics()
order_metrics = OrderMetrics()
catalog_metrics = CatalogMetrics()


def update_all_metrics():
    """Обновляет все метрики приложения и отправляет в InfluxDB"""
    try:
        user_metrics.update_metrics()
        order_metrics.update_metrics()
        catalog_metrics.update_metrics()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Критическая ошибка при отправке метрик: {e}", exc_info=True)
        raise


def check_influxdb_connection():
    """Проверяет подключение к InfluxDB и возвращает информацию о bucket"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        import urllib.request
        import socket
        from urllib.parse import urlparse
        
        parsed_url = urlparse(url)
        host = parsed_url.hostname
        port = parsed_url.port or 8086
        
  
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result != 0:
            return {
                'connected': False,
                'error': f'Не удается подключиться к {url} (порт {port} недоступен)',
                'url': url,
                'host': host,
                'port': port,
                'suggestions': [
                    'Проверьте, что InfluxDB запущен',
                    'Для Docker используйте: INFLUXDB_URL=http://host.docker.internal:8086',
                    'Для Linux Docker используйте IP хоста: INFLUXDB_URL=http://172.17.0.1:8086',
                    'Или добавьте InfluxDB в docker-compose.yml'
                ]
            }
    except Exception as e:
        logger.warning(f"Ошибка при проверке доступности URL: {e}")
    
    if not write_client:
        return {
            'connected': False,
            'error': 'InfluxDB клиент не инициализирован',
            'url': url,
            'suggestions': [
                'Проверьте логи приложения для деталей ошибки инициализации',
                'Убедитесь, что INFLUXDB_TOKEN установлен'
            ]
        }
    
    try:
        from influxdb_client import BucketsApi
        buckets_api = write_client.buckets_api()
        buckets = buckets_api.find_buckets()
        
        bucket_names = [b.name for b in buckets.buckets]
        bucket_exists = bucket in bucket_names
        
        return {
            'connected': True,
            'url': url,
            'org': org,
            'bucket': bucket,
            'bucket_exists': bucket_exists,
            'available_buckets': bucket_names
        }
    except Exception as e:
        logger.error(f"Ошибка при проверке подключения к InfluxDB: {e}", exc_info=True)
        error_msg = str(e)
        
      
        suggestions = []
        if "Connection refused" in error_msg or "Failed to establish" in error_msg:
            suggestions = [
                'InfluxDB недоступен по указанному URL',
                'Для Docker на Windows/Mac используйте: INFLUXDB_URL=http://host.docker.internal:8086',
                'Для Docker на Linux используйте IP хоста: INFLUXDB_URL=http://172.17.0.1:8086',
                'Или добавьте InfluxDB как сервис в docker-compose.yml'
            ]
        elif "Unauthorized" in error_msg or "401" in error_msg:
            suggestions = [
                'Неверный токен или нет прав доступа',
                'Проверьте INFLUXDB_TOKEN',
                'Убедитесь, что токен имеет права на запись в bucket'
            ]
        
        return {
            'connected': False,
            'error': error_msg,
            'url': url,
            'org': org,
            'suggestions': suggestions
        }


def read_metrics_from_influxdb(measurement_name=None, limit=100):
   
    if not write_client:
        return {
            'success': False,
            'error': 'InfluxDB клиент не инициализирован'
        }
    
    try:
        from influxdb_client import QueryApi
        
        query_api = write_client.query_api()
        
      
        if measurement_name:
            query = f'''from(bucket: "{bucket}")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "{measurement_name}")
  |> limit(n: {limit})'''
        else:
         
            query = f'''from(bucket: "{bucket}")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] =~ /^mptcourse_/)
  |> limit(n: {limit})'''
        
        result = query_api.query(org=org, query=query)
        
        metrics_data = []
        measurements_found = set()
        
        excluded_tags = {'result', 'table', '_result', '_table', '_start', '_stop', 'host'}
        
        for table in result:
            for record in table.records:
               
                tags = {}
                try:
                 
                    if hasattr(record, 'row') and record.row:
                       
                        for i, col in enumerate(table.columns):
                            if col.label not in excluded_tags and not col.label.startswith('_'):
                                if col.label not in ['_measurement', '_field', '_time', '_value']:
                                    if i < len(record.row):
                                        tags[col.label] = record.row[i]
                    elif hasattr(record, 'values'):
                        # Fallback на values, но фильтруем служебные теги
                        for key, value in record.values.items():
                            if key not in excluded_tags and not key.startswith('_'):
                                if key not in ['_measurement', '_field', '_time', '_value', '_start', '_stop']:
                                    tags[key] = value
                except Exception as e:
                    # Если не удалось получить теги через row, используем values
                    if hasattr(record, 'values'):
                        for key, value in record.values.items():
                            if key not in excluded_tags and not key.startswith('_'):
                                if key not in ['_measurement', '_field', '_time', '_value', '_start', '_stop']:
                                    tags[key] = value
                
                measurement = record.get_measurement()
                measurements_found.add(measurement)
                
                metrics_data.append({
                    'measurement': measurement,
                    'time': record.get_time().isoformat() if record.get_time() else None,
                    'field': record.get_field(),
                    'value': record.get_value(),
                    'tags': tags
                })
        
        return {
            'success': True,
            'bucket': bucket,
            'org': org,
            'count': len(metrics_data),
            'measurements_found': list(measurements_found),
            'metrics': metrics_data[:limit] 
        }
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при чтении метрик из InfluxDB: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'query_used': query if 'query' in locals() else None
        }


def delete_old_english_status_metrics():
    """
    Удаляет старые метрики с английскими значениями в теге status.
    Используйте эту функцию для очистки старых данных после перехода на русские теги.
    """
    if not write_client:
        return {
            'success': False,
            'error': 'InfluxDB клиент не инициализирован'
        }
    
    try:
        from influxdb_client import DeleteApi
        from datetime import datetime, timedelta
        
        delete_api = write_client.delete_api()
        
        
        start_time = datetime.now() - timedelta(days=7)
        
     
        english_statuses = ['processing', 'paid', 'shipped', 'delivered', 'cancelled', 'active', 'blocked', 'all']
        
        deleted_count = 0
        for status in english_statuses:
            try:
              
                predicate = f'_measurement=~ /^mptcourse_/ AND status="{status}"'
                delete_api.delete(
                    start=start_time,
                    stop=datetime.now(),
                    predicate=predicate,
                    bucket=bucket,
                    org=org
                )
                deleted_count += 1
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Не удалось удалить записи со статусом {status}: {e}")
        
        return {
            'success': True,
            'message': f'Удалены старые записи с английскими статусами',
            'deleted_statuses': english_statuses,
            'deleted_count': deleted_count
        }
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при удалении старых метрик: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


def write_metrics_to_file(output_file='/tmp/metrics.out'):
    """
    Записывает метрики в файл в формате InfluxDB line protocol для Telegraf.
    Генерирует метрики напрямую из БД, а не читает из InfluxDB.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:

        update_all_metrics()
        
      
        lines = []
        current_timestamp_ns = int(timezone.now().timestamp() * 1e9)
        
       
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        blocked_users = User.objects.filter(is_active=False).count()
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_users = User.objects.filter(
            Q(date_joined__gte=thirty_days_ago) | 
            Q(profile__registered_at__gte=thirty_days_ago)
        ).distinct().count()
        users_with_profiles = UserProfile.objects.count()
        
        lines.append(f'mptcourse_users_total,status=все value={float(total_users)} {current_timestamp_ns}')
        lines.append(f'mptcourse_users_total,status=активные value={float(active_users)} {current_timestamp_ns}')
        lines.append(f'mptcourse_users_total,status=заблокированные value={float(blocked_users)} {current_timestamp_ns}')
        lines.append(f'mptcourse_active_users_count value={float(recent_users)} {current_timestamp_ns}')
        lines.append(f'mptcourse_users_with_profiles value={float(users_with_profiles)} {current_timestamp_ns}')
        
    
        status_mapping = {
            'processing': 'обработка',
            'paid': 'оплачен',
            'shipped': 'отправлен',
            'delivered': 'доставлен',
            'cancelled': 'отменен'
        }
        for status_en, status_ru in status_mapping.items():
            count = Order.objects.filter(order_status=status_en).count()
            lines.append(f'mptcourse_orders_count,status={status_ru} value={float(count)} {current_timestamp_ns}')
        
        total_amount_result = Order.objects.aggregate(total=Sum('total_amount'))
        total_amount = float(total_amount_result['total'] or Decimal('0'))
        lines.append(f'mptcourse_orders_total_amount value={total_amount} {current_timestamp_ns}')
        
        twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
        orders_24h = Order.objects.filter(created_at__gte=twenty_four_hours_ago).count()
        lines.append(f'mptcourse_orders_last_24h value={float(orders_24h)} {current_timestamp_ns}')
        
        for status_en, status_ru in status_mapping.items():
            if status_en != 'cancelled':
                status_avg_result = Order.objects.filter(order_status=status_en).aggregate(avg=Avg('total_amount'))
                if status_avg_result['avg'] is not None:
                    status_avg_amount = float(status_avg_result['avg'])
                    lines.append(f'mptcourse_average_order_amount,status={status_ru} value={status_avg_amount} {current_timestamp_ns}')
        
        delivered_amount_result = Order.objects.filter(order_status='delivered').aggregate(total=Sum('total_amount'))
        delivered_amount = float(delivered_amount_result['total'] or Decimal('0'))
        lines.append(f'mptcourse_delivered_orders_amount value={delivered_amount} {current_timestamp_ns}')

        total_products = Course.objects.count()
        available_products = Course.objects.filter(is_available=True).count()
        lines.append(f'mptcourse_products_total value={float(total_products)} {current_timestamp_ns}')
        lines.append(f'mptcourse_products_available value={float(available_products)} {current_timestamp_ns}')
        
        cart_items = CartItem.objects.all()
        total_items_in_carts = cart_items.aggregate(total=Sum('quantity'))['total'] or 0
        unique_products = cart_items.values('course').distinct().count()
        lines.append(f'mptcourse_products_in_carts value={float(total_items_in_carts)} {current_timestamp_ns}')
        lines.append(f'mptcourse_unique_products_in_carts value={float(unique_products)} {current_timestamp_ns}')
        
        total_favorites = CourseFavorite.objects.count()
        unique_favorites = CourseFavorite.objects.values('course').distinct().count()
        lines.append(f'mptcourse_products_in_favorites value={float(total_favorites)} {current_timestamp_ns}')
        lines.append(f'mptcourse_unique_products_in_favorites value={float(unique_favorites)} {current_timestamp_ns}')
        
        carts_value = Decimal('0')
        for cart in Cart.objects.all():
            carts_value += cart.total_price()
        lines.append(f'mptcourse_carts_total_value value={float(carts_value)} {current_timestamp_ns}')
        

        metrics_count = len(lines)
        test_metric_line = f'telegraf_test,source=file value={metrics_count} {current_timestamp_ns}'
        lines.insert(0, test_metric_line)
        
   
        try:
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write('\n'.join(lines))
                f.write('\n')
            
            logger.info(f'Записано {len(lines)} метрик в {output_file}')
            return True
        except Exception as e:
            logger.error(f'Ошибка записи в файл: {e}')
            return False
            
    except Exception as e:
        logger.error(f'Критическая ошибка: {e}', exc_info=True)
        return False


def close_influxdb_client():
  
    try:
        if write_api:
            write_api.close()
        if write_client:
            write_client.close()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при закрытии соединения с InfluxDB: {e}")

