"""
routes/contact.py — formularz kontaktowy
"""
import os
import logging
from flask import Blueprint, request, jsonify
from routes.csrf import csrf_required

contact_bp = Blueprint("contact", __name__, url_prefix="/api/contact")

log = logging.getLogger(__name__)

IS_DEV = os.environ.get("FLASK_ENV") != "production"


@contact_bp.post("")
@csrf_required
def send_contact():
    data = request.get_json(silent=True) or {}
    name    = (data.get("name")    or "").strip()
    email   = (data.get("email")   or "").strip()
    message = (data.get("message") or "").strip()

    if not name or not email or not message:
        return jsonify({"error": "Wypełnij wszystkie pola."}), 400
    if len(name) > 100:
        return jsonify({"error": "Imię zbyt długie (max 100 znaków)."}), 400
    if len(message) < 10:
        return jsonify({"error": "Wiadomość musi mieć co najmniej 10 znaków."}), 400
    if len(message) > 5000:
        return jsonify({"error": "Wiadomość zbyt długa (max 5000 znaków)."}), 400
    if "@" not in email or len(email) > 254:
        return jsonify({"error": "Niepoprawny adres e-mail."}), 400

    if IS_DEV:
        print(f"\n{'='*50}")
        print(f"[KONTAKT] Od: {name} <{email}>")
        print(f"[KONTAKT] Wiadomość: {message}")
        print(f"{'='*50}\n")
        return jsonify({"ok": True})

    # Produkcja — wyślij przez SMTP
    try:
        import smtplib
        from email.mime.text import MIMEText

        SMTP_HOST = os.environ.get("SMTP_HOST", "")
        SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
        SMTP_USER = os.environ.get("SMTP_USER", "")
        SMTP_PASS = os.environ.get("SMTP_PASS", "")
        SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

        if not SMTP_HOST:
            log.warning("SMTP nie skonfigurowany — wiadomość kontaktowa utracona")
            return jsonify({"ok": True})

        body = f"Wiadomość z formularza kontaktowego rzeczy.pl\n\nOd: {name} <{email}>\n\n{message}"
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"Kontakt od {name} — rzeczy.pl"
        msg["From"]    = SMTP_FROM
        msg["To"]      = SMTP_FROM  # wysyłamy do siebie (adres admina)
        msg["Reply-To"] = email

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [SMTP_FROM], msg.as_string())

        return jsonify({"ok": True})
    except Exception as e:
        log.error(f"Błąd wysyłki wiadomości kontaktowej: {e}")
        return jsonify({"ok": True})  # Nie ujawniaj błędu użytkownikowi
