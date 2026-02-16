"""
View для отправки метрик в InfluxDB.
При обращении к endpoint обновляет все метрики и отправляет их в InfluxDB.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from django.utils import timezone
from .metrics_influxdb import update_all_metrics, check_influxdb_connection, read_metrics_from_influxdb, delete_old_english_status_metrics


@never_cache
@require_http_methods(["GET", "POST"])
def metrics_influxdb_export(request):
    """
    Обновляет все метрики и отправляет их в InfluxDB.
    
    Returns:
        JsonResponse: JSON ответ со статусом отправки метрик
    """
    try:
       
        connection_info = check_influxdb_connection()
        if not connection_info.get('connected'):
            return JsonResponse({
                'status': 'error',
                'message': f'Не удалось подключиться к InfluxDB: {connection_info.get("error", "Unknown error")}',
                'connection_info': connection_info,
                'timestamp': str(timezone.now())
            }, status=500)
        
        if not connection_info.get('bucket_exists'):
            return JsonResponse({
                'status': 'warning',
                'message': f'Bucket "{connection_info.get("bucket")}" не найден в InfluxDB',
                'connection_info': connection_info,
                'timestamp': str(timezone.now())
            }, status=200)
    
        update_all_metrics()
        
        # Проверяем, что метрики записались
        metrics_check = read_metrics_from_influxdb(limit=10)
        
        from .metrics_influxdb import bucket, org, url
        return JsonResponse({
            'status': 'success',
            'message': 'Метрики успешно отправлены в InfluxDB',
            'config': {
                'url': url,
                'bucket': bucket,
                'org': org
            },
            'connection_info': connection_info,
            'written_metrics_count': metrics_check.get('count', 0) if metrics_check.get('success') else 0,
            'timestamp': str(timezone.now())
        }, status=200)
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Ошибка при отправке метрик: {str(e)}',
            'timestamp': str(timezone.now())
        }, status=500)


@never_cache
@require_http_methods(["GET"])
def metrics_influxdb_check(request):
    """
    Проверяет, какие метрики записаны в InfluxDB.
    Полезно для диагностики проблем с записью.
    
    Query параметры:
        measurement: Имя measurement для фильтрации (опционально)
        limit: Максимальное количество записей (по умолчанию 100)
    """
    try:
        measurement = request.GET.get('measurement', None)
        limit = int(request.GET.get('limit', 100))
        
        # Проверяем подключение
        connection_info = check_influxdb_connection()
        
        # Читаем метрики
        metrics_data = read_metrics_from_influxdb(measurement_name=measurement, limit=limit)
        
        return JsonResponse({
            'status': 'success',
            'connection_info': connection_info,
            'metrics_data': metrics_data,
            'timestamp': str(timezone.now())
        }, status=200)
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Ошибка при проверке метрик: {str(e)}',
            'timestamp': str(timezone.now())
        }, status=500)


@never_cache
@require_http_methods(["POST"])
def metrics_influxdb_cleanup(request):
    """
    Удаляет старые метрики с английскими значениями в теге status.
    Используйте для очистки старых данных после перехода на русские теги.
    """
    try:
        result = delete_old_english_status_metrics()
        
        return JsonResponse({
            'status': 'success' if result.get('success') else 'error',
            'result': result,
            'timestamp': str(timezone.now())
        }, status=200 if result.get('success') else 500)
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'Ошибка при очистке метрик: {str(e)}',
            'timestamp': str(timezone.now())
        }, status=500)


@never_cache
@require_http_methods(["GET"])
def metrics_influxdb_telegraf_view(request):
    """
    Показывает метрики, отправленные через Telegraf (с тегом host от Telegraf).
    Полезно для проверки, что Telegraf правильно отправляет метрики.
    Примечание: тег host исключается из результатов, так как это инфраструктурный тег,
    который не должен влиять на бизнес-метрики (статусы заказов и т.д.).
    
    Query параметры:
        measurement: Имя measurement для фильтрации (опционально)
        limit: Максимальное количество записей (по умолчанию 100)
    """
    try:
        from .metrics_influxdb import write_client, bucket, org
        from influxdb_client import QueryApi
        
        measurement = request.GET.get('measurement', None)
        limit = int(request.GET.get('limit', 100))
        
        if not write_client:
            return JsonResponse({
                'status': 'error',
                'message': 'InfluxDB клиент не инициализирован'
            }, status=500)
        
        query_api = write_client.query_api()
        
        # Запрос для метрик, отправленных через Telegraf (с тегом host)
        if measurement:
            query = f'''from(bucket: "{bucket}")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "{measurement}")
  |> filter(fn: (r) => exists r["host"])
  |> limit(n: {limit})'''
        else:
            # Получаем все метрики с префиксом mptcourse, отправленные через Telegraf
            query = f'''from(bucket: "{bucket}")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] =~ /^mptcourse_/)
  |> filter(fn: (r) => exists r["host"])
  |> limit(n: {limit})'''
        
        result = query_api.query(org=org, query=query)
        
        metrics_data = []
        measurements_found = set()
        
        # Исключаем служебные теги, включая host (Docker container ID от Telegraf)
        # host не должен влиять на бизнес-метрики со статусами
        excluded_tags = {'result', 'table', '_result', '_table', '_start', '_stop', 'host'}
        excluded_fields = {'_measurement', '_field', '_time', '_value', '_start', '_stop'}
        
        for table in result:
            for record in table.records:
                tags = {}
                if hasattr(record, 'values'):
                    for key, value in record.values.items():
                        # Исключаем служебные поля и теги
                        if key not in excluded_fields and not key.startswith('_') and key not in excluded_tags:
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
        
        return JsonResponse({
            'status': 'success',
            'count': len(metrics_data),
            'measurements_found': list(measurements_found),
            'metrics': metrics_data[:limit],
            'query_used': query,
            'timestamp': str(timezone.now())
        }, status=200)
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при чтении метрик Telegraf: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': f'Ошибка при чтении метрик: {str(e)}',
            'timestamp': str(timezone.now())
        }, status=500)
