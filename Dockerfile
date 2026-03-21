FROM python:3.11-slim

WORKDIR /app

# Zależności systemowe
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Zależności Pythona
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kod aplikacji
COPY backend/ ./backend/
COPY wymien-i-kup.html .

# Katalog na uploady i bazę
RUN mkdir -p backend/uploads

WORKDIR /app/backend

# Zmienna środowiskowa
ENV FLASK_ENV=production
ENV PORT=8080

EXPOSE 8080

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
