"""
csrf.py — prosty CSRF token oparty na sesji
"""
import secrets
from flask import session, request, jsonify
from functools import wraps


def generate_csrf():
    """Generuje token CSRF i zapisuje w sesji."""
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(32)
    return session["_csrf"]


def csrf_required(f):
    """Dekorator — wymaga poprawnego tokenu CSRF dla metod modyfikujących."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        # Pomiń dla GET/HEAD/OPTIONS
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return f(*args, **kwargs)
        # Niezalogowany → 401 (przed sprawdzeniem CSRF)
        if not session.get("user_id"):
            return jsonify({"error": "Wymagane logowanie."}), 401
        # Sprawdź token z nagłówka lub JSON
        token = request.headers.get("X-CSRF-Token") or \
                (request.get_json(silent=True) or {}).get("_csrf")
        if not token or token != session.get("_csrf"):
            return jsonify({"error": "Błąd bezpieczeństwa (CSRF). Odśwież stronę."}), 403
        return f(*args, **kwargs)
    return wrapper
