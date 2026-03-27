"""
gunicorn.conf.py — konfiguracja serwera produkcyjnego
Uruchomienie: gunicorn -c gunicorn.conf.py app:app
"""
import os
import multiprocessing

# Adres i port
bind    = f"0.0.0.0:{os.environ.get('PORT', '8080')}"

# Liczba workerów: 2 × CPU + 1 (standardowa formuła)
workers = 2

# Typ workera
worker_class = "sync"

# Timeout żądania (sekundy)
timeout = 120

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


def on_starting(server):
    """
    Uruchamiany RAZ w procesie master, zanim workery zostaną sforkowane.
    Inicjalizuje bazę danych — eliminuje wyścig między workerami.
    """
    import sys
    import os
    sys.path.insert(0, os.path.dirname(__file__))
    from db import init_db
    init_db()
