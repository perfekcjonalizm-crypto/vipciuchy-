"""
notifier.py — wysyłka e-mail (SMTP) i SMS (Twilio)
W trybie DEV kody trafiają do logu i są zwracane w odpowiedzi API.
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

IS_PROD  = os.environ.get("FLASK_ENV") == "production"
DEV_MODE = not IS_PROD  # jeśli True — kody w logu zamiast wysyłki

# ── SMTP ──────────────────────────────────────────────────────────
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)

# ── Twilio SMS ────────────────────────────────────────────────────
TWILIO_SID  = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN= os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.environ.get("TWILIO_FROM_NUMBER", "")


def send_email_code(to_email: str, code: str) -> bool:
    """Wysyła kod weryfikacyjny na e-mail. Zwraca True jeśli sukces."""
    subject = "Kod weryfikacyjny — rzeczy.pl"
    body = (
        f"Witaj!\n\n"
        f"Twój kod weryfikacyjny: {code}\n\n"
        f"Kod ważny przez 30 minut.\n"
        f"Jeśli to nie Ty — zignoruj tę wiadomość.\n\n"
        f"rzeczy.pl"
    )

    if DEV_MODE or not SMTP_HOST:
        log.warning(f"[DEV] E-MAIL do {to_email} | KOD: {code}")
        print(f"\n{'='*40}\n[DEV] KOD EMAIL dla {to_email}: {code}\n{'='*40}\n")
        return True  # w dev traktujemy jako sukces

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"]    = SMTP_FROM
        msg["To"]      = to_email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [to_email], msg.as_string())
        return True
    except Exception as e:
        log.error(f"Błąd wysyłki e-mail: {e}")
        return False


def send_sms_code(to_phone: str, code: str) -> bool:
    """Wysyła kod SMS przez Twilio. Zwraca True jeśli sukces."""
    if DEV_MODE or not TWILIO_SID:
        log.warning(f"[DEV] SMS do {to_phone} | KOD: {code}")
        print(f"\n{'='*40}\n[DEV] KOD SMS dla {to_phone}: {code}\n{'='*40}\n")
        return True

    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(
            body=f"rzeczy.pl — Twój kod: {code} (ważny 30 min)",
            from_=TWILIO_FROM,
            to=to_phone
        )
        return True
    except Exception as e:
        log.error(f"Błąd wysyłki SMS: {e}")
        return False


def send_order_notification_buyer(buyer_email: str, buyer_name: str, product_name: str, amount: float, order_id: int) -> bool:
    """Email do kupującego po złożeniu zamówienia."""
    subject = f"✅ Zamówienie #{order_id} potwierdzone — rzeczy.pl"
    body = (
        f"Cześć {buyer_name}!\n\n"
        f"Twoje zamówienie zostało przyjęte 🎉\n\n"
        f"📦 Produkt: {product_name}\n"
        f"💰 Kwota: {amount:.2f} zł\n"
        f"🔢 Nr zamówienia: #{order_id}\n\n"
        f"Sprzedawczyni skontaktuje się z Tobą w sprawie wysyłki.\n"
        f"Możesz napisać do niej przez czat na rzeczy.pl\n\n"
        f"Dziękujemy za zakupy! 💜\n"
        f"Zespół rzeczy.pl"
    )
    if DEV_MODE or not SMTP_HOST:
        print(f"\n{'='*40}\n[DEV] EMAIL KUPUJĄCY {buyer_email}:\n{subject}\n{body}\n{'='*40}\n")
        return True
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = buyer_email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls(); s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [buyer_email], msg.as_string())
        return True
    except Exception as e:
        log.error(f"Błąd emaila kupującego: {e}"); return False


def send_order_notification_seller(seller_email: str, seller_name: str, product_name: str, seller_amount: float, order_id: int) -> bool:
    """Email do sprzedawczyni po sprzedaży."""
    subject = f"🛍️ Sprzedałaś produkt! Zamówienie #{order_id} — rzeczy.pl"
    body = (
        f"Gratulacje {seller_name}! 🎉\n\n"
        f"Ktoś właśnie kupił Twój produkt!\n\n"
        f"📦 Produkt: {product_name}\n"
        f"💰 Twój zarobek (po prowizji 5%): {seller_amount:.2f} zł\n"
        f"🔢 Nr zamówienia: #{order_id}\n\n"
        f"Skontaktuj się z kupującą przez czat i uzgodnij wysyłkę.\n\n"
        f"Miłej sprzedaży! 💜\n"
        f"Zespół rzeczy.pl"
    )
    if DEV_MODE or not SMTP_HOST:
        print(f"\n{'='*40}\n[DEV] EMAIL SPRZEDAWCA {seller_email}:\n{subject}\n{body}\n{'='*40}\n")
        return True
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = seller_email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls(); s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [seller_email], msg.as_string())
        return True
    except Exception as e:
        log.error(f"Błąd emaila sprzedawczyni: {e}"); return False


def send_shipping_notification(to_email: str, username: str, product_name: str, tracking_number: str, order_id: int) -> bool:
    """Email powiadomienie dla kupującego o wysłaniu paczki."""
    subject = f"📦 Twoje zamówienie #{order_id} zostało wysłane!"
    tracking_info = f"\nNumer śledzenia: {tracking_number}" if tracking_number else ""
    body = (
        f"Cześć {username}!\n\n"
        f"Sprzedawca wysłał Twoje zamówienie #{order_id}.\n"
        f"Produkt: {product_name}{tracking_info}\n\n"
        f"Po otrzymaniu paczki zatwierdź odbiór w serwisie, "
        f"aby środki zostały wypłacone sprzedawcy.\n\n"
        f"Pozdrawiamy,\nZespół Rzeczy z Drugiej Ręki"
    )
    if DEV_MODE or not SMTP_HOST:
        print(f"\n{'='*40}\n[DEV] EMAIL WYSYŁKA {to_email}:\n{subject}\n{body}\n{'='*40}\n")
        return True
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls(); s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [to_email], msg.as_string())
        return True
    except Exception as e:
        log.error(f"Błąd emaila wysyłki: {e}"); return False


def send_generic_notification(to_email: str, to_name: str, event_label: str, product_name: str, note: str = "") -> bool:
    """Generyczne powiadomienie o zmianie statusu zamówienia."""
    subject = f"📬 {event_label} — rzeczy.pl"
    note_line = f"\nNotatka: {note}" if note else ""
    body = (
        f"Cześć {to_name}!\n\n"
        f"Status Twojego zamówienia dotyczącego \"{product_name}\" zmienił się:\n"
        f"➡️  {event_label}{note_line}\n\n"
        f"Zaloguj się na rzeczy.pl, aby zobaczyć szczegóły.\n\n"
        f"Zespół rzeczy.pl"
    )
    if DEV_MODE or not SMTP_HOST:
        print(f"\n{'='*40}\n[DEV] EMAIL STATUS {to_email}: {event_label}\n{'='*40}\n")
        return True
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls(); s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [to_email], msg.as_string())
        return True
    except Exception as e:
        log.error(f"Błąd emaila statusu: {e}"); return False


def send_message_notification(to_email: str, to_name: str, from_name: str, product_name: str) -> bool:
    """Email powiadomienie o nowej wiadomości."""
    subject = f"💬 Nowa wiadomość od {from_name} — rzeczy.pl"
    body = (
        f"Cześć {to_name}!\n\n"
        f"{from_name} napisał(a) do Ciebie w sprawie produktu \"{product_name}\".\n\n"
        f"Zaloguj się na rzeczy.pl, aby odpowiedzieć.\n\n"
        f"Zespół rzeczy.pl"
    )
    if DEV_MODE or not SMTP_HOST:
        print(f"\n{'='*40}\n[DEV] EMAIL WIADOMOŚĆ {to_email}: od {from_name}\n{'='*40}\n")
        return True
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.starttls(); s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [to_email], msg.as_string())
        return True
    except Exception as e:
        log.error(f"Błąd emaila wiadomości: {e}"); return False
