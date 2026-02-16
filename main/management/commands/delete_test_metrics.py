"""
Django management command для удаления тестовых метрик test_metric из InfluxDB.
"""
from django.core.management.base import BaseCommand
from main.metrics_influxdb import write_client, bucket, org
from influxdb_client import DeleteApi
from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Удаляет тестовые метрики test_metric из InfluxDB'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=1,
            help='Количество дней назад для удаления (по умолчанию: 1)',
        )

    def handle(self, *args, **options):
        days = options['days']
        
        if not write_client:
            self.stdout.write(
                self.style.ERROR('InfluxDB клиент не инициализирован')
            )
            return
        
        try:
            delete_api = write_client.delete_api()
            start_time = datetime.now() - timedelta(days=days)
            stop_time = datetime.now()
            
            # Удаляем метрики test_metric
            delete_api.delete(
                start=start_time,
                stop=stop_time,
                predicate='_measurement="test_metric"',
                bucket=bucket,
                org=org
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ Удалены метрики test_metric за последние {days} дней'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ Ошибка при удалении метрик: {e}')
            )

