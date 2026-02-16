# Gunicorn конфигурация для продакшена

bind = "unix:/home/mptcourse/mptcourse/mptcourse/mptcourse.sock"
workers = 3
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Логирование
accesslog = "/home/mptcourse/mptcourse/logs/access.log"
errorlog = "/home/mptcourse/mptcourse/logs/error.log"
loglevel = "info"

# Безопасность
user = "mptcourse"
group = "www-data"
umask = 0o007

# Перезапуск при изменении кода (только для разработки)
reload = False

