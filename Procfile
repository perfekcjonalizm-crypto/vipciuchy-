web: gunicorn --chdir backend app:app --workers 4 --threads 2 --worker-class gthread --bind 0.0.0.0:${PORT:-8080} --timeout 30 --keep-alive 5 --log-level info
