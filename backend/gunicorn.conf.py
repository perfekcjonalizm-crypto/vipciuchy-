"""
gunicorn.conf.py — konfiguracja serwera produkcyjnego
Uruchomienie: gunicorn -c gunicorn.conf.py app:app
"""
import os
import multiprocessing

# Adres i port
bind    = f"0.0.0.0:{os.environ.get('PORT', '8080')}"

# Liczba workerów: 2 × CPU + 1 (standardowa formuła)
workers = multiprocessing.cpu_count() * 2 + 1

# Typ workera (sync jest bezpieczny dla SQLite, gevent dla PostgreSQL)
worker_class = "sync"

# Timeout żądania (sekundy)
timeout = 30

# Keepalive
keepalive = 5

# Logi
accesslog = "-"        # stdout
errorlog  = "-"        # stderr
loglevel  = "info"

# Bezpieczeństwo
limit_request_line   = 4096
limit_request_fields = 100

# Restart workera po N żądaniach (przeciwdziała memory leak)
max_requests          = 1000
max_requests_jitter   = 100

# Plik PID
pidfile = "/tmp/gunicorn_rzeczy.pid"
