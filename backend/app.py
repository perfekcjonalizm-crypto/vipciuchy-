"""
app.py — aplikacja Flask (lokalnie + produkcja)
Lokalnie:    python3 app.py
Produkcja:   gunicorn -c gunicorn.conf.py app:app
"""
import os
import sys
import logging
from flask import Flask, jsonify, send_file, request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

# ── Wczytaj .env ─────────────────────────────────────────────────
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Konfiguracja ─────────────────────────────────────────────────
ENV        = os.environ.get("FLASK_ENV", "development").strip()
SECRET_KEY = os.environ.get("SECRET_KEY")
PORT       = int(os.environ.get("PORT", 8080))
IS_PROD    = ENV == "production"

if not SECRET_KEY:
    if IS_PROD:
        raise RuntimeError("SECRET_KEY nie jest ustawiony! Uzupełnij plik .env")
    SECRET_KEY = "dev-only-insecure-key-change-me"

ALLOWED_ORIGINS = [o.strip() for o in os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:8080,http://localhost:5500,http://127.0.0.1:8080,"
    "https://vipciuchy.pl,https://www.vipciuchy.pl,"
    "https://vipciuchy-production.up.railway.app"
).split(",") if o.strip()]

# ── Importy blueprintów ──────────────────────────────────────────
from db import init_db
from routes.auth      import auth_bp
from routes.products  import products_bp
from routes.orders    import orders_bp
from routes.messages  import messages_bp
from routes.upload    import upload_bp
from routes.favorites import favorites_bp
from routes.contact   import contact_bp
from routes.admin     import admin_bp
from routes.reports   import reports_bp
from routes.reviews   import reviews_bp
from routes.payments  import payments_bp
from routes.shipping      import shipping_bp
from routes.google_auth   import google_auth_bp

# ── Aplikacja ─────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key        = SECRET_KEY
app.config["ENV"]     = ENV
app.config["DEBUG"]   = not IS_PROD

# Bezpieczne ciasteczka sesji
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"]   = IS_PROD
app.config["SESSION_COOKIE_DOMAIN"]   = ".vipciuchy.pl" if IS_PROD else None
app.config["SESSION_COOKIE_NAME"]     = "session"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30  # 30 dni
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max body

# ── CORS — ręczne nagłówki ────────────────────────────────────────
def _cors_origin() -> str:
    """
    Zwraca origin do użycia w nagłówkach CORS.
    Railway/Fastly CDN może zdjąć nagłówek Origin — fallback na Referer,
    a gdy go też brak, w trybie produkcyjnym używamy domyślnej domeny.
    """
    origin = request.headers.get("Origin", "").strip()
    if not origin:
        try:
            from urllib.parse import urlparse
            ref = request.headers.get("Referer", "")
            if ref:
                p = urlparse(ref)
                origin = f"{p.scheme}://{p.netloc}"
        except Exception:
            pass
    if not origin and IS_PROD and ALLOWED_ORIGINS:
        origin = ALLOWED_ORIGINS[0]   # CDN zjadł Origin — bezpiecznie zakładamy główną domenę
    return origin


def _set_cors(headers, origin: str) -> None:
    headers["Access-Control-Allow-Origin"]      = origin
    headers["Access-Control-Allow-Credentials"] = "true"
    headers["Access-Control-Allow-Headers"]     = "Content-Type, X-CSRF-Token"
    headers["Access-Control-Allow-Methods"]     = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    headers["Vary"]                             = "Origin"


@app.after_request
def apply_cors(response):
    origin = _cors_origin()
    if origin in ALLOWED_ORIGINS:
        _set_cors(response.headers, origin)
    return response


@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        from flask import Response
        origin = _cors_origin()
        resp = Response("", 204)
        if origin in ALLOWED_ORIGINS:
            _set_cors(resp.headers, origin)
        return resp

# ── Rate limiting ─────────────────────────────────────────────────
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per minute"],
    storage_uri="memory://",
)

# Ostrzejsze limity na auth i kontakt
limiter.limit("10 per minute")(auth_bp)
limiter.limit("5 per minute")(contact_bp)

# ── Blueprinty ────────────────────────────────────────────────────
app.register_blueprint(auth_bp)
app.register_blueprint(products_bp)
app.register_blueprint(orders_bp)
app.register_blueprint(messages_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(favorites_bp)
app.register_blueprint(contact_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(reviews_bp)
app.register_blueprint(payments_bp)
app.register_blueprint(shipping_bp)
app.register_blueprint(google_auth_bp)

# Surowszy rate limit na logowanie
limiter.limit("10 per 15 minutes")(app.view_functions["auth.login"])

# ── Frontend HTML ─────────────────────────────────────────────────
HTML_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wymien-i-kup.html")

@app.get("/")
def frontend():
    resp = send_file(HTML_PATH)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

# ── Security headers ──────────────────────────────────────────────
@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"]        = "DENY"
    resp.headers["X-XSS-Protection"]       = "1; mode=block"
    resp.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://js.stripe.com https://plausible.io; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob: https://images.unsplash.com; "
        "connect-src 'self' https://api.stripe.com https://plausible.io; "
        "frame-src https://js.stripe.com https://hooks.stripe.com; "
        "frame-ancestors 'none';"
    )
    if IS_PROD:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp

# ── CSRF token ────────────────────────────────────────────────────
from routes.csrf import generate_csrf

@app.get("/api/csrf")
def csrf_token():
    return jsonify({"csrf": generate_csrf()})

# ── Healthcheck ───────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "env": ENV, "app": "Rzeczy z Drugiej Ręki"})

# ── Obsługa błędów ────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Nie znaleziono zasobu."}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Niedozwolona metoda HTTP."}), 405

@app.errorhandler(429)
def rate_limit(e):
    return jsonify({"error": "Zbyt wiele żądań. Poczekaj chwilę."}), 429

@app.errorhandler(500)
def server_error(e):
    app.logger.error(f"500 error: {e}")
    return jsonify({"error": "Wewnętrzny błąd serwera."}), 500

# ── Logging (produkcja) ───────────────────────────────────────────
if IS_PROD:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(os.path.dirname(__file__), "app.log")),
            logging.StreamHandler(),
        ]
    )

# ── Start ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    try:
        from seed import seed
        seed()
    except Exception as ex:
        print(f"[warn] Seed: {ex}")

    print(f"\n{'='*52}")
    print(f"  Rzeczy z Drugiej Ręki — {'PRODUKCJA' if IS_PROD else 'DEVELOPMENT'}")
    print(f"  http://localhost:{PORT}/")
    print(f"{'='*52}\n")

    app.run(host="0.0.0.0", port=PORT, debug=not IS_PROD, use_reloader=not IS_PROD)
