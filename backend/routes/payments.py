"""
routes/payments.py — integracja Stripe: PaymentIntent, webhook, wypłaty
"""
import os
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from db import get_db
from routes.csrf import csrf_required

payments_bp = Blueprint("payments", __name__, url_prefix="/api/payments")
log = logging.getLogger(__name__)

STRIPE_SECRET_KEY     = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
PLATFORM_FEE_PCT      = 0.05
AUTO_RELEASE_DAYS     = 14   # dni do auto-release po potwierdzeniu wysyłki


def _stripe():
    """Zwraca moduł stripe z ustawionym kluczem lub None w trybie dev."""
    if not STRIPE_SECRET_KEY:
        return None
    try:
        import stripe as _s
        _s.api_key = STRIPE_SECRET_KEY
        return _s
    except ImportError:
        return None


# ─────────────────────────────────────────────────────────────────
# 1. Utwórz PaymentIntent
# ─────────────────────────────────────────────────────────────────
@payments_bp.post("/create-intent")
@csrf_required
def create_intent():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data       = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    method     = (data.get("payment_method") or "card").strip()  # card | blik

    if not product_id:
        return jsonify({"error": "Brakuje product_id."}), 400

    conn = get_db()
    try:
        prod = conn.execute(
            "SELECT * FROM products WHERE id=? AND is_sold=0 AND is_hidden=0", (product_id,)
        ).fetchone()
        if not prod:
            return jsonify({"error": "Produkt nie istnieje lub już sprzedany."}), 404
        if prod["seller_id"] == uid:
            return jsonify({"error": "Nie możesz kupić własnego produktu."}), 400

        amount_pln = prod["price"]
        amount_gr  = int(round(amount_pln * 100))  # Stripe używa groszy
        stripe     = _stripe()

        if not stripe:
            # Tryb deweloperski — bez prawdziwego Stripe
            return jsonify({
                "client_secret":   "pi_dev_secret_" + str(product_id),
                "publishable_key": "",
                "amount":          amount_pln,
                "dev_mode":        True,
            })

        payment_methods = ["blik"] if method == "blik" else ["card"]
        intent = stripe.PaymentIntent.create(
            amount=amount_gr,
            currency="pln",
            payment_method_types=payment_methods,
            capture_method="automatic",
            metadata={
                "product_id": str(product_id),
                "buyer_id":   str(uid),
                "seller_id":  str(prod["seller_id"]),
            },
            description=f"Zakup: {prod['name']} (ID {product_id})",
        )
        return jsonify({
            "client_secret":   intent.client_secret,
            "publishable_key": STRIPE_PUBLISHABLE_KEY,
            "amount":          amount_pln,
            "dev_mode":        False,
        })
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────
# 2. Stripe Webhook
# ─────────────────────────────────────────────────────────────────
@payments_bp.post("/webhook")
def stripe_webhook():
    payload = request.get_data()
    sig     = request.headers.get("Stripe-Signature", "")
    stripe  = _stripe()

    if not stripe or not STRIPE_WEBHOOK_SECRET:
        return jsonify({"ok": True})

    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        log.warning(f"Stripe webhook error: {e}")
        return jsonify({"error": "Invalid signature"}), 400

    if event["type"] == "payment_intent.succeeded":
        _handle_payment_success(event["data"]["object"])
    elif event["type"] == "payment_intent.payment_failed":
        log.info(f"Payment failed: {event['data']['object']['id']}")

    return jsonify({"ok": True})


def _handle_payment_success(intent):
    """Tworzy zamówienie po udanej płatności Stripe."""
    try:
        product_id = int(intent["metadata"].get("product_id", 0))
        buyer_id   = int(intent["metadata"].get("buyer_id", 0))
        seller_id  = int(intent["metadata"].get("seller_id", 0))
    except (TypeError, ValueError):
        return

    if not product_id or not buyer_id:
        return

    conn = get_db()
    try:
        # Idempotency — sprawdź czy zamówienie już istnieje
        if conn.execute(
            "SELECT id FROM orders WHERE stripe_payment_intent_id=?", (intent["id"],)
        ).fetchone():
            return

        prod = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not prod:
            return

        amount        = prod["price"]
        platform_fee  = round(amount * PLATFORM_FEE_PCT, 2)
        seller_amount = round(amount - platform_fee, 2)
        auto_release  = (datetime.now() + timedelta(days=AUTO_RELEASE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

        cur = conn.execute(
            """INSERT INTO orders
               (product_id, buyer_id, seller_id, amount, platform_fee, seller_amount,
                payment_method, status, escrow_status, stripe_payment_intent_id, auto_release_at)
               VALUES (?,?,?,?,?,?,'card','paid','paid_held',?,?)""",
            (product_id, buyer_id, seller_id, amount, platform_fee, seller_amount,
             intent["id"], auto_release)
        )
        conn.execute("UPDATE products SET is_sold=1, status='sold' WHERE id=?", (product_id,))
        conn.commit()
        order_id = cur.lastrowid
        _send_order_emails(conn, buyer_id, seller_id, prod, amount, seller_amount, order_id)
    except Exception as e:
        log.error(f"_handle_payment_success: {e}")
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────
# 3. Tryb dev — utwórz zamówienie bez Stripe
# ─────────────────────────────────────────────────────────────────
@payments_bp.post("/confirm-dev")
@csrf_required
def confirm_dev():
    """Dev mode: symuluje udaną płatność i tworzy zamówienie."""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data           = request.get_json(silent=True) or {}
    product_id     = data.get("product_id")
    payment_method = (data.get("payment_method") or "blik").strip()
    shipping_carrier   = (data.get("shipping_carrier")   or "").strip()
    shipping_service   = (data.get("shipping_service")   or "").strip()
    shipping_point_id  = (data.get("shipping_point_id")  or "").strip()
    shipping_amount    = float(data.get("shipping_amount") or 0)
    import json as _json
    shipping_recipient = _json.dumps(data.get("shipping_recipient") or {})

    if not product_id:
        return jsonify({"error": "Brakuje product_id."}), 400

    conn = get_db()
    try:
        prod = conn.execute(
            "SELECT * FROM products WHERE id=? AND is_sold=0", (product_id,)
        ).fetchone()
        if not prod:
            return jsonify({"error": "Produkt nie istnieje lub już sprzedany."}), 404
        if prod["seller_id"] == uid:
            return jsonify({"error": "Nie możesz kupić własnego produktu."}), 400

        amount        = prod["price"]
        platform_fee  = round(amount * PLATFORM_FEE_PCT, 2)
        seller_amount = round(amount - platform_fee, 2)
        auto_release  = (datetime.now() + timedelta(days=AUTO_RELEASE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

        cur = conn.execute(
            """INSERT INTO orders
               (product_id, buyer_id, seller_id, amount, platform_fee, seller_amount,
                payment_method, status, escrow_status, auto_release_at,
                shipping_carrier, shipping_service, shipping_point_id, shipping_amount, shipping_recipient)
               VALUES (?,?,?,?,?,?,?,'paid','paid_held',?,?,?,?,?,?)""",
            (product_id, uid, prod["seller_id"], amount, platform_fee, seller_amount,
             payment_method, auto_release,
             shipping_carrier, shipping_service, shipping_point_id, shipping_amount, shipping_recipient)
        )
        order_id = cur.lastrowid
        conn.execute("UPDATE products SET is_sold=1, status='sold' WHERE id=?", (product_id,))
        conn.commit()
        _send_order_emails(conn, uid, prod["seller_id"], prod, amount, seller_amount, order_id)
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        from routes.orders import _order_dict
        return jsonify({"order": _order_dict(order)}), 201
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────
# 4. Stripe Connect — onboarding sprzedawcy
# ─────────────────────────────────────────────────────────────────
@payments_bp.get("/connect")
def connect_onboarding():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    stripe = _stripe()
    if not stripe:
        return jsonify({"error": "Stripe nie skonfigurowany.", "dev_mode": True}), 503

    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return jsonify({"error": "Nie znaleziono użytkownika."}), 404

        stripe_account_id = user["stripe_account_id"] if "stripe_account_id" in user.keys() else ""

        if not stripe_account_id:
            account = stripe.Account.create(
                type="express",
                country="PL",
                email=user["email"],
                capabilities={"transfers": {"requested": True}},
            )
            stripe_account_id = account["id"]
            conn.execute(
                "UPDATE users SET stripe_account_id=? WHERE id=?",
                (stripe_account_id, uid)
            )
            conn.commit()

        base_url = os.environ.get("BASE_URL", "http://localhost:8080")
        link = stripe.AccountLink.create(
            account=stripe_account_id,
            refresh_url=f"{base_url}/?stripe_connect=refresh",
            return_url=f"{base_url}/?stripe_connect=success",
            type="account_onboarding",
        )
        return jsonify({"url": link["url"]})
    finally:
        conn.close()


@payments_bp.get("/connect-status")
def connect_status():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        stripe_account_id = user["stripe_account_id"] if "stripe_account_id" in cols and user["stripe_account_id"] else ""

        if not stripe_account_id:
            return jsonify({"connected": False})

        stripe = _stripe()
        if not stripe:
            return jsonify({"connected": True, "dev_mode": True})

        account = stripe.Account.retrieve(stripe_account_id)
        return jsonify({
            "connected":    account.get("charges_enabled", False),
            "details_done": account.get("details_submitted", False),
            "account_id":   stripe_account_id,
        })
    finally:
        conn.close()


def _send_order_emails(conn, buyer_id, seller_id, prod, amount, seller_amount, order_id):
    try:
        buyer_row  = conn.execute("SELECT username, email FROM users WHERE id=?", (buyer_id,)).fetchone()
        seller_row = conn.execute("SELECT username, email FROM users WHERE id=?", (seller_id,)).fetchone()
        if buyer_row and seller_row:
            from notifier import send_order_notification_buyer, send_order_notification_seller
            send_order_notification_buyer(
                buyer_row["email"], buyer_row["username"], prod["name"], amount, order_id
            )
            send_order_notification_seller(
                seller_row["email"], seller_row["username"], prod["name"], seller_amount, order_id
            )
    except Exception:
        pass
