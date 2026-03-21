#!/bin/bash
# start.sh — uruchamia backend lokalnie
# Użycie: ./start.sh [port]

set -e

PORT=${1:-8080}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo "================================================"
echo "  Rzeczy z Drugiej Ręki — lokalny backend"
echo "================================================"
echo ""

# Sprawdź Python
if ! command -v python3 &>/dev/null; then
    echo "BŁĄD: Python 3 nie jest zainstalowany."
    exit 1
fi

# Sprawdź Flask
if ! python3 -c "import flask" 2>/dev/null; then
    echo "Instaluję Flask i zależności..."
    python3 -m pip install flask flask-cors werkzeug python-dotenv flask-limiter
fi

echo "Uruchamiam backend na porcie $PORT..."
echo "Zatrzymaj: Ctrl+C"
echo ""

# Uruchom Flask w tle, poczekaj aż będzie gotowy, otwórz przeglądarkę
cd "$BACKEND_DIR"
PORT=$PORT python3 app.py &
FLASK_PID=$!

# Czekaj aż serwer będzie gotowy (max 10s)
echo "Czekam na serwer..."
for i in $(seq 1 20); do
    if curl -s "http://localhost:$PORT/api/health" >/dev/null 2>&1; then
        echo "Serwer gotowy!"
        break
    fi
    sleep 0.5
done

echo ""
echo "  Otwieranie: http://localhost:$PORT/"
echo ""
open "http://localhost:$PORT/"

# Wróć na pierwszy plan
wait $FLASK_PID
