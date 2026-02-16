"""
Команда для непрерывной записи метрик в файл.
Запускается как отдельный процесс для автоматической записи метрик каждые N секунд.
"""
import time
from django.core.management.base import BaseCommand
from main.metrics_influxdb import write_metrics_to_file


class Command(BaseCommand):
    help = 'Непрерывно записывает метрики в файл для Telegraf'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=10,
            help='Интервал записи в секундах (по умолчанию: 10)',
        )
        parser.add_argument(
            '--output-file',
            type=str,
            default='/tmp/metrics.out',
            help='Путь к файлу для записи метрик',
        )

    def handle(self, *args, **options):
        interval = options['interval']
        output_file = options['output_file']
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Запуск записи метрик в {output_file} каждые {interval} секунд...'
            )
        )
        self.stdout.write('Нажмите Ctrl+C для остановки')
        
        try:
            while True:
                if write_metrics_to_file(output_file):
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Метрики обновлены в {output_file}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'⚠ Ошибка при записи метрик')
                    )
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('\nОстановка записи метрик...'))

