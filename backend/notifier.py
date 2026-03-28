"""
notifier.py — wysyłka e-mail przez Resend HTTP API
Railway blokuje SMTP (port 587) — używamy Resend (port 443, HTTP).
W trybie DEV kody trafiają do logu.
"""
import os
import logging
import requests as _requests

log = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM    = os.environ.get("RESEND_FROM", "VipCiuchy <onboarding@resend.dev>")
DEV_MODE       = not bool(RESEND_API_KEY)


def _send_resend(to_email: str, subject: str, body: str) -> bool:
    """Wysyła email przez Resend API (HTTP). Zwraca True jeśli sukces."""
    try:
        resp = _requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type":  "application/json",
            },
            json={
                "from":    RESEND_FROM,
                "to":      [to_email],
                "subject": subject,
                "text":    body,
            },
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            log.error(f"Resend error {resp.status_code}: {resp.text}")
            return False
        return True
    except Exception as e:
        log.error(f"Błąd wysyłki e-mail (Resend): {e}")
        return False


def send_email_code(to_email: str, code: str) -> bool:
    """Wysyła kod weryfikacyjny na e-mail."""
    if DEV_MODE:
        print(f"\n{'='*40}\n[DEV] KOD EMAIL dla {to_email}: {code}\n{'='*40}\n")
        return True
    return _send_resend(
        to_email,
        "Kod weryfikacyjny — VipCiuchy",
        f"Witaj!\n\nTwój kod weryfikacyjny VipCiuchy: {code}\n\n"
        f"Kod ważny przez 30 minut.\n"
        f"Jeśli to nie Ty — zignoruj tę wiadomość.\n\n"
        f"Zespół VipCiuchy\nvipciuchy.pl",
    )


def send_sms_code(to_phone: str, code: str) -> bool:
    """Wysyła kod SMS przez Twilio. Zwraca True jeśli sukces."""
def send_sms_code(to_phone: str, code: str) -> bool:
    """SMS usunięty — weryfikacja tylko przez email."""
    return True


def send_order_notification_buyer(buyer_email: str, buyer_name: str, product_name: str, amount: float, order_id: int) -> bool:
    if DEV_MODE:
        print(f"[DEV] EMAIL KUPUJĄCY {buyer_email}: zamówienie #{order_id}"); return True
    return _send_resend(buyer_email, f"Zamówienie #{order_id} potwierdzone — VipCiuchy",
        f"Cześć {buyer_name}!\n\nTwoje zamówienie zostało przyjęte.\n\n"
        f"Produkt: {product_name}\nKwota: {amount:.2f} zł\nNr zamówienia: #{order_id}\n\n"
        f"Zespół VipCiuchy\nvipciuchy.pl")


def send_order_notification_seller(seller_email: str, seller_name: str, product_name: str, seller_amount: float, order_id: int) -> bool:
    if DEV_MODE:
        print(f"[DEV] EMAIL SPRZEDAWCA {seller_email}: zamówienie #{order_id}"); return True
    return _send_resend(seller_email, f"Sprzedałeś produkt! Zamówienie #{order_id} — VipCiuchy",
        f"Gratulacje {seller_name}!\n\nKtoś kupił Twój produkt.\n\n"
        f"Produkt: {product_name}\nTwój zarobek (po prowizji 5%): {seller_amount:.2f} zł\n\n"
        f"Zespół VipCiuchy\nvipciuchy.pl")


def send_shipping_notification(to_email: str, username: str, product_name: str, tracking_number: str, order_id: int) -> bool:
    if DEV_MODE:
        print(f"[DEV] EMAIL WYSYŁKA {to_email}: #{order_id}"); return True
    tracking = f"\nNumer śledzenia: {tracking_number}" if tracking_number else ""
    return _send_resend(to_email, f"Zamówienie #{order_id} wysłane — VipCiuchy",
        f"Cześć {username}!\n\nZamówienie #{order_id} ({product_name}) zostało wysłane.{tracking}\n\n"
        f"Po otrzymaniu paczki zatwierdź odbiór w serwisie.\n\nZespół VipCiuchy\nvipciuchy.pl")


def send_generic_notification(to_email: str, to_name: str, event_label: str, product_name: str, note: str = "") -> bool:
    if DEV_MODE:
        print(f"[DEV] EMAIL STATUS {to_email}: {event_label}"); return True
    note_line = f"\nNotatka: {note}" if note else ""
    return _send_resend(to_email, f"{event_label} — VipCiuchy",
        f"Cześć {to_name}!\n\nStatus zamówienia ({product_name}): {event_label}{note_line}\n\n"
        f"Zaloguj się na vipciuchy.pl\n\nZespół VipCiuchy")


def send_message_notification(to_email: str, to_name: str, from_name: str, product_name: str) -> bool:
    if DEV_MODE:
        print(f"[DEV] EMAIL WIADOMOŚĆ {to_email}: od {from_name}"); return True
    return _send_resend(to_email, f"Nowa wiadomość od {from_name} — VipCiuchy",
        f"Cześć {to_name}!\n\n{from_name} napisał(a) do Ciebie w sprawie \"{product_name}\".\n\n"
        f"Zaloguj się na vipciuchy.pl aby odpowiedzieć.\n\nZespół VipCiuchy")
