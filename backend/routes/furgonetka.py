"""
routes/furgonetka.py — integracja z Furgonetka.pl (webhook / REST)

Furgonetka pobiera zamówienia gotowe do wysyłki:
  GET  /api/furgonetka/orders                    → lista zamówień
  POST /api/furgonetka/orders/{id}/tracking_number → aktualizacja numeru śledzenia

Dokumentacja: https://furgonetka.pl/integracja/dokumentacja/
"""
import os
import json
import logging
from flask import Blueprint, request, jsonify
from db import get_db

furgonetka_bp = Blueprint("furgonetka", __name__, url_prefix="/api/furgonetka")
log = logging.getLogger(__name__)

def _get_token():
    """Czyta token dynamicznie — Railway może ładować env po starcie."""
    # Szuka też z ewentualną spacją (błąd wprowadzania w Railway)
    for key in ["FURGONETKA_WEBHOOK_TOKEN", "FURGONETKA_WEBHOOK_TOKEN "]:
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return ""


# ── Debug endpoints (usuń po weryfikacji) ────────────────────────
@furgonetka_bp.get("/health")
def health():
    token = _get_token()
    return jsonify({
        "token_set": bool(token),
        "token_len": len(token),
        "env_keys":  [k for k in os.environ if "FURG" in k.upper()],
    })


@furgonetka_bp.route("/debug-orders", methods=["GET", "POST"])
def debug_orders():
    """Zwraca wszystkie nagłówki i parametry."""
    info = {
        "method":  request.method,
        "headers": dict(request.headers),
        "args":    dict(request.args),
        "json":    request.get_json(silent=True),
        "auth_ok": _auth(),
    }
    log.warning(f"[furgonetka debug] {info}")
    return jsonify({"orders": [], "page": 1, "per_page": 50, "total": 0, "total_pages": 1})


@furgonetka_bp.route("/", defaults={"subpath": ""}, methods=["GET", "POST", "PUT", "PATCH"])
@furgonetka_bp.route("/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH"])
def catch_all(subpath):
    """
    Catch-all — loguje KAŻDE żądanie Furgonetki, żebyśmy widzieli
    dokładnie jaki URL i nagłówki wysyła podczas testu połączenia.
    Zwraca prawidłowy format orders (200 OK) bez sprawdzania autoryzacji.
    USUŃ po ustaleniu formatu autoryzacji.
    """
    info = {
        "path":    request.path,
        "method":  request.method,
        "headers": dict(request.headers),
        "args":    dict(request.args),
        "json":    request.get_json(silent=True),
    }
    log.warning(f"[furgonetka catch-all] {info}")
    # Odpowiedz poprawnym formatem niezależnie od URL/auth
    return jsonify({"orders": [], "page": 1, "per_page": 50, "total": 0, "total_pages": 1})


def _auth():
    """Weryfikuje token Furgonetki — obsługuje wszystkie możliwe formaty."""
    token = _get_token()
    if not token:
        return False

    # 1. Authorization: Bearer {token}
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        if auth[7:].strip() == token:
            return True
    # 2. Authorization: Token {token}
    if auth.startswith("Token "):
        if auth[6:].strip() == token:
            return True
    # 3. Cały nagłówek to sam token
    if auth.strip() == token:
        return True
    # 4. Nagłówek X-Token lub X-Api-Key
    for header in ["X-Token", "X-Api-Key", "X-Auth-Token", "Api-Key"]:
        if request.headers.get(header, "").strip() == token:
            return True
    # 5. Query param ?token= lub ?api_key=
    for param in ["token", "api_key", "apikey"]:
        if request.args.get(param, "").strip() == token:
            return True
    # 6. JSON body
    body = request.get_json(silent=True) or {}
    if body.get("token", "").strip() == token:
        return True

    return False


# ── GET /api/furgonetka/orders ────────────────────────────────────
@furgonetka_bp.get("/orders")
def get_orders():
    """
    Furgonetka pobiera zamówienia gotowe do wysyłki.
    Zwraca zamówienia ze statusem 'paid' lub 'processing' bez numeru śledzenia.
    """
    # Zawsze loguj — potrzebne do debugowania autoryzacji
    log.warning(f"[furgonetka /orders] method={request.method} "
                f"headers={dict(request.headers)} args={dict(request.args)}")
    if not _auth():
        return jsonify({"message": "Unauthorized"}), 401

    page     = max(1, int(request.args.get("page", 1)))
    per_page = min(100, int(request.args.get("per_page", 50)))
    offset   = (page - 1) * per_page

    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT o.id, o.amount, o.shipping_carrier, o.shipping_service,
                      o.shipping_point_id, o.shipping_amount, o.shipping_recipient,
                      o.created_at, o.status, o.tracking_number,
                      p.name  AS product_name,
                      p.brand AS product_brand,
                      u_b.username AS buyer_name,
                      u_b.email    AS buyer_email,
                      u_b.phone    AS buyer_phone,
                      u_s.username AS seller_name,
                      u_s.email    AS seller_email,
                      u_s.phone    AS seller_phone,
                      u_s.address  AS seller_address,
                      u_s.city     AS seller_city,
                      u_s.postal_code AS seller_postal
               FROM orders o
               LEFT JOIN products p ON p.id = o.product_id
               LEFT JOIN users u_b  ON u_b.id = o.buyer_id
               LEFT JOIN users u_s  ON u_s.id = o.seller_id
               WHERE o.status IN ('paid','processing')
                 AND (o.tracking_number IS NULL OR o.tracking_number = '')
               ORDER BY o.created_at DESC
               LIMIT ? OFFSET ?""",
            (per_page, offset)
        ).fetchall()

        total = conn.execute(
            """SELECT COUNT(*) FROM orders
               WHERE status IN ('paid','processing')
                 AND (tracking_number IS NULL OR tracking_number = '')"""
        ).fetchone()[0]

        orders = []
        for r in rows:
            try:
                recipient = json.loads(r["shipping_recipient"] or "{}")
            except Exception:
                recipient = {}

            carrier_map = {
                "inpost_paczkomat": "inpost_locker",
                "inpost_kurier":    "inpost_courier",
                "dpd":              "dpd",
                "poczta":           "poczta_polska",
                "orlen":            "orlen_paczka",
            }

            orders.append({
                "id":            str(r["id"]),
                "status":        r["status"] or "paid",
                "created_at":    r["created_at"],
                "source":        "VipCiuchy",
                "delivery_method": carrier_map.get(r["shipping_carrier"] or "", "inpost_locker"),
                "delivery_point_id": r["shipping_point_id"] or "",
                "products": [
                    {
                        "name":     f"{r['product_brand']} — {r['product_name']}",
                        "quantity": 1,
                        "price":    float(r["amount"] or 0),
                    }
                ],
                "buyer": {
                    "name":    recipient.get("name") or r["buyer_name"] or "",
                    "email":   recipient.get("email") or r["buyer_email"] or "",
                    "phone":   recipient.get("phone") or r["buyer_phone"] or "",
                    "address": {
                        "street":      recipient.get("address") or "",
                        "city":        recipient.get("city") or "",
                        "post_code":   recipient.get("postal") or "",
                        "country_code": "PL",
                    },
                },
                "sender": {
                    "name":    r["seller_name"] or "",
                    "email":   r["seller_email"] or "",
                    "phone":   r["seller_phone"] or "",
                    "address": {
                        "street":      r["seller_address"] or "",
                        "city":        r["seller_city"] or "",
                        "post_code":   r["seller_postal"] or "",
                        "country_code": "PL",
                    },
                },
                "cod":              False,
                "cod_amount":       0,
                "insurance_amount": float(r["amount"] or 0),
            })

        return jsonify({
            "orders":     orders,
            "page":       page,
            "per_page":   per_page,
            "total":      total,
            "total_pages": max(1, -(-total // per_page)),
        })
    finally:
        conn.close()


# ── POST /api/furgonetka/orders/{id}/tracking_number ─────────────
@furgonetka_bp.post("/orders/<int:order_id>/tracking_number")
def set_tracking(order_id: int):
    """
    Furgonetka odsyła numer śledzenia po stworzeniu przesyłki.
    """
    if not _auth():
        return jsonify({"message": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    tracking = (data.get("tracking_number") or "").strip()
    carrier  = (data.get("carrier") or "").strip()
    label_url = (data.get("label_url") or "").strip()

    if not tracking:
        return jsonify({"message": "Brakuje tracking_number."}), 400

    conn = get_db()
    try:
        order = conn.execute("SELECT id, status FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            return jsonify({"message": "Zamówienie nie istnieje."}), 404

        conn.execute(
            "UPDATE orders SET tracking_number=?, status='shipped' WHERE id=?",
            (tracking, order_id)
        )

        # Zapisz/zaktualizuj przesyłkę w tabeli shipments
        existing = conn.execute("SELECT id FROM shipments WHERE order_id=?", (order_id,)).fetchone()
        if existing:
            conn.execute(
                """UPDATE shipments
                   SET tracking_number=?, tracking_status='dispatched',
                       carrier=COALESCE(NULLIF(?,''), carrier),
                       label_url=COALESCE(NULLIF(?,''), label_url)
                   WHERE order_id=?""",
                (tracking, carrier, label_url, order_id)
            )
        else:
            conn.execute(
                """INSERT INTO shipments
                   (order_id, carrier, tracking_number, tracking_status, label_url)
                   VALUES (?,?,?,'dispatched',?)""",
                (order_id, carrier, tracking, label_url)
            )

        conn.commit()
        log.info(f"[furgonetka] Order {order_id} tracking={tracking} carrier={carrier}")
        return jsonify({"message": "OK"}), 200
    finally:
        conn.close()
