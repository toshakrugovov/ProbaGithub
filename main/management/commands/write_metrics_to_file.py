"""
Django management command для записи метрик в файл /tmp/metrics.out
в формате InfluxDB line protocol для Telegraf.
"""
from django.core.management.base import BaseCommand
from main.metrics_influxdb import write_metrics_to_file


class Command(BaseCommand):
    help = 'Записывает метрики в файл для Telegraf в формате InfluxDB line protocol'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-file',
            type=str,
            default='/tmp/metrics.out',
            help='Путь к файлу для записи метрик (по умолчанию: /tmp/metrics.out)',
        )

    def handle(self, *args, **options):
        output_file = options['output_file']
        
        if write_metrics_to_file(output_file):
            self.stdout.write(
                self.style.SUCCESS(f'✓ Метрики записаны в {output_file}')
            )
        else:
            self.stdout.write(
                self.style.ERROR(f'✗ Ошибка при записи метрик в {output_file}')
            )

