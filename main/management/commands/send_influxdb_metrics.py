"""
Команда для непрерывной отправки метрик напрямую в InfluxDB.
Отправляет метрики без использования Telegraf, чтобы избежать добавления тега host.
"""
import time
from django.core.management.base import BaseCommand
from main.metrics_influxdb import update_all_metrics


class Command(BaseCommand):
    help = 'Непрерывно отправляет метрики напрямую в InfluxDB (без Telegraf)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=10,
            help='Интервал отправки в секундах (по умолчанию: 10)',
        )

    def handle(self, *args, **options):
        interval = options['interval']
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Запуск отправки метрик в InfluxDB каждые {interval} секунд...'
            )
        )
        self.stdout.write('Метрики отправляются напрямую в InfluxDB (без Telegraf)')
        self.stdout.write('Нажмите Ctrl+C для остановки')
        
        try:
            while True:
                try:
                    update_all_metrics()
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Метрики отправлены в InfluxDB')
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'✗ Ошибка при отправке метрик: {e}')
                    )
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('\nОстановка отправки метрик...'))






