

from django.http import HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from .metrics import get_all_metrics_prometheus_format
try:
    from django_prometheus.exports import ExportToDjangoView
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from prometheus_client.core import REGISTRY
except ImportError:
    ExportToDjangoView = None
    generate_latest = None
    CONTENT_TYPE_LATEST = 'text/plain; version=0.0.4; charset=utf-8'
    REGISTRY = None


@never_cache
@require_http_methods(["GET"])
def metrics_export(request):
    
    try:
        custom_metrics = get_all_metrics_prometheus_format()
        django_metrics = ""
        if generate_latest and REGISTRY:
            try:
                django_metrics = generate_latest(REGISTRY).decode('utf-8')
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Не удалось получить стандартные метрики: {e}")
        
        if django_metrics:
            all_metrics = custom_metrics + "\n# Django Prometheus стандартные метрики\n" + django_metrics
        else:
            all_metrics = custom_metrics
        

        return HttpResponse(
            all_metrics,
            content_type=CONTENT_TYPE_LATEST
        )
    except Exception as e:

        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при экспорте метрик: {e}")
        

        return HttpResponse(
            "# Ошибка при генерации метрик\n",
            content_type=CONTENT_TYPE_LATEST,
            status=500
        )
