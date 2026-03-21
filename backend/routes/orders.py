"""
routes/orders.py — składanie i przeglądanie zamówień + escrow flow
"""
import json
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from db import get_db
from routes.csrf import csrf_required

orders_bp = Blueprint("orders", __name__, url_prefix="/api/orders")

PLATFORM_FEE_PCT  = 0.0
AUTO_RELEASE_DAYS = 14

# ─── State machine ────────────────────────────────────────────────
# Kto może wykonać przejście: 'seller' | 'buyer' | 'system'
# Format: (from_status, to_status) → allowed_roles
_TRANSITIONS = {
    ("pending",   "paid"):       {"system"},          # po potwierdzeniu płatności
    ("pending",   "cancelled"):  {"buyer", "seller", "admin"},
    ("paid",      "shipped"):    {"seller"},           # sprzedawca wysyła
    ("paid",      "cancelled"):  {"buyer", "seller", "admin"},
    ("shipped",   "delivered"):  {"buyer", "system"},  # kupujący potwierdza lub auto
    ("shipped",   "cancelled"):  {"admin"},            # tylko admin może anulować po wysyłce
    ("delivered", "cancelled"):  set(),                # niedozwolone
}

VALID_STATUSES = {"pending", "paid", "shipped", "delivered", "cancelled"}


def _can_transition(from_s: str, to_s: str, role: str) -> bool:
    allowed = _TRANSITIONS.get((from_s, to_s), set())
    return role in allowed


def _record_transition(conn, order_id, actor_id,
                        actor_role: str, from_s: str, to_s: str, note: str = "") -> None:
    conn.execute(
        """INSERT INTO order_status_history
               (order_id, actor_id, actor_role, from_status, to_status, note)
           VALUES (?,?,?,?,?,?)""",
        (order_id, actor_id, actor_role, from_s, to_s, note)
    )


# ─── Helpers ─────────────────────────────────────────────────────
def _order_dict(row):
    keys = row.keys()
    def _get(k, default=None):
        return row[k] if k in keys else default

    return {
        "id":                        row["id"],
        "product_id":                row["product_id"],
        "buyer_id":                  row["buyer_id"],
        "seller_id":                 row["seller_id"],
        "amount":                    row["amount"],
        "platform_fee":              row["platform_fee"],
        "seller_amount":             row["seller_amount"],
        "payment_method":            row["payment_method"],
        "status":                    row["status"],
        "escrow_status":             _get("escrow_status", "paid_held"),
        "tracking_number":           _get("tracking_number", ""),
        "shipped_at":                _get("shipped_at"),
        "delivered_at":              _get("delivered_at"),
        "payout_at":                 _get("payout_at"),
        "auto_release_at":           _get("auto_release_at"),
        "stripe_payment_intent_id":  _get("stripe_payment_intent_id", ""),
        "shipping_carrier":   _get("shipping_carrier", ""),
        "shipping_service":   _get("shipping_service", ""),
        "shipping_point_id":  _get("shipping_point_id", ""),
        "shipping_amount":    _get("shipping_amount", 0),
        "shipping_recipient": _get("shipping_recipient", ""),
        "created_at":                row["created_at"],
    }


def _trigger_payout(conn, order):
    """Wypłata sprzedawcy — Stripe Transfer lub log w dev."""
    import os, logging
    log = logging.getLogger(__name__)

    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if stripe_key:
        try:
            import stripe
            stripe.api_key = stripe_key
            cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
            seller = conn.execute("SELECT * FROM users WHERE id=?", (order["seller_id"],)).fetchone()
            seller_account = seller["stripe_account_id"] if "stripe_account_id" in cols and seller and seller["stripe_account_id"] else ""
            if seller_account:
                amount_gr = int(round(order["seller_amount"] * 100))
                stripe.Transfer.create(
                    amount=amount_gr,
                    currency="pln",
                    destination=seller_account,
                    description=f"Wypłata zamówienie #{order['id']}",
                )
                log.info(f"Stripe Transfer OK: order #{order['id']} → {seller_account}")
        except Exception as e:
            log.error(f"Stripe Transfer failed: {e}")
    else:
        import logging
        logging.getLogger(__name__).info(
            f"[DEV] Payout skipped (no Stripe key): order #{order['id']}, "
            f"seller #{order['seller_id']}, amount={order['seller_amount']} PLN"
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE orders SET escrow_status='payout_sent', payout_at=? WHERE id=?",
        (now, order["id"])
    )
    conn.commit()


# ─── Endpoint: utwórz zamówienie (legacy / fallback) ─────────────
@orders_bp.post("")
@csrf_required
def create_order():
    """Fallback: tworzy zamówienie bez PaymentIntent (dev mode)."""
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
    shipping_recipient = json.dumps(data.get("shipping_recipient") or {})

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

        try:
            buyer_row  = conn.execute("SELECT username, email FROM users WHERE id=?", (uid,)).fetchone()
            seller_row = conn.execute("SELECT username, email FROM users WHERE id=?", (prod["seller_id"],)).fetchone()
            if buyer_row and seller_row:
                from notifier import send_order_notification_buyer, send_order_notification_seller
                send_order_notification_buyer(buyer_row["email"], buyer_row["username"], prod["name"], amount, order_id)
                send_order_notification_seller(seller_row["email"], seller_row["username"], prod["name"], seller_amount, order_id)
        except Exception:
            pass

        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return jsonify({"order": _order_dict(order)}), 201
    finally:
        conn.close()


# ─── Endpoint: potwierdź wysyłkę (sprzedawca) ────────────────────
@orders_bp.post("/<int:oid>/confirm-shipping")
@csrf_required
def confirm_shipping(oid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data           = request.get_json(silent=True) or {}
    tracking_number = (data.get("tracking_number") or "").strip()

    conn = get_db()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id=? AND seller_id=?", (oid, uid)
        ).fetchone()
        if not order:
            return jsonify({"error": "Nie znaleziono zamówienia."}), 404

        escrow = order["escrow_status"] if "escrow_status" in order.keys() else "paid_held"
        if escrow not in ("paid_held",):
            return jsonify({"error": f"Nie można potwierdzić wysyłki w statusie '{escrow}'."}), 400

        now          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        auto_release = (datetime.now() + timedelta(days=AUTO_RELEASE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

        conn.execute(
            """UPDATE orders
               SET escrow_status='shipped', shipped_at=?, tracking_number=?, auto_release_at=?
               WHERE id=?""",
            (now, tracking_number, auto_release, oid)
        )
        conn.commit()

        # Powiadom kupującego
        try:
            buyer  = conn.execute("SELECT email, username FROM users WHERE id=?", (order["buyer_id"],)).fetchone()
            prod   = conn.execute("SELECT name FROM products WHERE id=?", (order["product_id"],)).fetchone()
            if buyer and prod:
                from notifier import send_shipping_notification
                send_shipping_notification(buyer["email"], buyer["username"], prod["name"], tracking_number, oid)
        except Exception:
            pass

        order = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        return jsonify({"order": _order_dict(order)})
    finally:
        conn.close()


# ─── Endpoint: potwierdź odbiór (kupujący) ───────────────────────
@orders_bp.post("/<int:oid>/confirm-delivery")
@csrf_required
def confirm_delivery(oid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id=? AND buyer_id=?", (oid, uid)
        ).fetchone()
        if not order:
            return jsonify({"error": "Nie znaleziono zamówienia."}), 404

        escrow = order["escrow_status"] if "escrow_status" in order.keys() else ""
        if escrow not in ("paid_held", "shipped"):
            return jsonify({"error": f"Nie można potwierdzić odbioru w statusie '{escrow}'."}), 400

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE orders SET escrow_status='delivered', delivered_at=? WHERE id=?",
            (now, oid)
        )
        conn.commit()

        # Wypłata sprzedawcy
        order_updated = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        _trigger_payout(conn, order_updated)

        order_final = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        return jsonify({"order": _order_dict(order_final)})
    finally:
        conn.close()


# ─── Endpoint: otwórz spór (kupujący) ───────────────────────────
@orders_bp.post("/<int:oid>/dispute")
@csrf_required
def open_dispute(oid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data        = request.get_json(silent=True) or {}
    reason      = (data.get("reason") or "").strip()
    description = (data.get("description") or "").strip()

    if not reason:
        return jsonify({"error": "Podaj powód sporu."}), 400
    if len(description) > 2000:
        return jsonify({"error": "Opis zbyt długi (max 2000 znaków)."}), 400

    conn = get_db()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id=? AND buyer_id=?", (oid, uid)
        ).fetchone()
        if not order:
            return jsonify({"error": "Nie znaleziono zamówienia."}), 404

        escrow = order["escrow_status"] if "escrow_status" in order.keys() else ""
        if escrow not in ("paid_held", "shipped"):
            return jsonify({"error": "Spór można otworzyć tylko dla zamówień w toku."}), 400

        # Sprawdź czy spór już istnieje
        existing = conn.execute(
            "SELECT id FROM disputes WHERE order_id=? AND status='open'", (oid,)
        ).fetchone()
        if existing:
            return jsonify({"error": "Dla tego zamówienia już istnieje otwarty spór."}), 400

        conn.execute(
            "INSERT INTO disputes (order_id, reporter_id, reason, description) VALUES (?,?,?,?)",
            (oid, uid, reason, description)
        )
        conn.execute(
            "UPDATE orders SET escrow_status='disputed' WHERE id=?", (oid,)
        )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


# ─── Endpoint: anuluj zamówienie (kupujący, przed wysyłką) ───────
@orders_bp.post("/<int:oid>/cancel")
@csrf_required
def cancel_order(oid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id=? AND buyer_id=?", (oid, uid)
        ).fetchone()
        if not order:
            return jsonify({"error": "Nie znaleziono zamówienia."}), 404

        escrow = order["escrow_status"] if "escrow_status" in order.keys() else ""
        if escrow != "paid_held":
            return jsonify({"error": "Można anulować tylko zamówienia przed wysyłką."}), 400

        # Stripe refund (jeśli był prawdziwy PaymentIntent)
        pi_id = order["stripe_payment_intent_id"] if "stripe_payment_intent_id" in order.keys() else ""
        if pi_id and not pi_id.startswith("pi_dev"):
            import os
            stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
            if stripe_key:
                try:
                    import stripe
                    stripe.api_key = stripe_key
                    stripe.Refund.create(payment_intent=pi_id)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Stripe Refund failed: {e}")

        conn.execute(
            "UPDATE orders SET escrow_status='refunded', status='cancelled' WHERE id=?", (oid,)
        )
        conn.execute(
            "UPDATE products SET is_sold=0, status='available' WHERE id=?",
            (order["product_id"],)
        )
        conn.commit()
        order = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        return jsonify({"order": _order_dict(order)})
    finally:
        conn.close()


# ─── Endpoint: szczegóły zamówienia ──────────────────────────────
@orders_bp.get("/my")
def my_orders():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT o.*, p.name as product_name, p.emoji as product_emoji
               FROM orders o
               LEFT JOIN products p ON p.id = o.product_id
               WHERE o.buyer_id=? ORDER BY o.created_at DESC""",
            (uid,)
        ).fetchall()
        result = []
        for r in rows:
            d = _order_dict(r)
            d["product_name"]  = r["product_name"]  if "product_name"  in r.keys() else None
            d["product_emoji"] = r["product_emoji"] if "product_emoji" in r.keys() else "📦"
            result.append(d)
        return jsonify({"orders": result})
    finally:
        conn.close()


@orders_bp.get("/selling")
def selling_orders():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT o.*, p.name as product_name, p.emoji as product_emoji,
                      u.username as buyer_name
               FROM orders o
               LEFT JOIN products p ON p.id = o.product_id
               LEFT JOIN users u ON u.id = o.buyer_id
               WHERE o.seller_id=? ORDER BY o.created_at DESC""",
            (uid,)
        ).fetchall()
        result = []
        for r in rows:
            d = _order_dict(r)
            d["product_name"]  = r["product_name"]  if "product_name"  in r.keys() else None
            d["product_emoji"] = r["product_emoji"] if "product_emoji" in r.keys() else "📦"
            d["buyer_name"]    = r["buyer_name"]    if "buyer_name"    in r.keys() else None
            result.append(d)
        return jsonify({"orders": result})
    finally:
        conn.close()


@orders_bp.get("/<int:oid>")
def get_order(oid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401
    conn = get_db()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id=? AND (buyer_id=? OR seller_id=?)",
            (oid, uid, uid)
        ).fetchone()
        if not order:
            return jsonify({"error": "Nie znaleziono zamówienia."}), 404
        return jsonify({"order": _order_dict(order)})
    finally:
        conn.close()


# ─── Endpoint: zmiana statusu zamówienia ─────────────────────────
@orders_bp.patch("/<int:oid>/status")
@csrf_required
def update_order_status(oid):
    """
    Sprzedawca (lub kupujący w określonych przypadkach) zmienia status zamówienia.

    Body JSON:
      { "status": "shipped", "note": "InPost paczkomat XYZ" }

    Dozwolone przejścia zależne od roli:
      pending  → paid       (system/admin)
      pending  → cancelled  (buyer | seller | admin)
      paid     → shipped    (seller)
      paid     → cancelled  (buyer | seller | admin)
      shipped  → delivered  (buyer | system)
      shipped  → cancelled  (admin)
    """
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data       = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").strip().lower()
    note       = (data.get("note") or "").strip()[:500]

    if new_status not in VALID_STATUSES:
        return jsonify({"error": f"Nieprawidłowy status. Dozwolone: {', '.join(sorted(VALID_STATUSES))}."}), 400

    conn = get_db()
    try:
        order = conn.execute(
            "SELECT * FROM orders WHERE id=? AND (buyer_id=? OR seller_id=?)",
            (oid, uid, uid)
        ).fetchone()
        if not order:
            return jsonify({"error": "Nie znaleziono zamówienia."}), 404

        # Ustal rolę aktora
        if order["seller_id"] == uid and order["buyer_id"] == uid:
            actor_role = "seller"   # edge case — ta sama osoba
        elif order["seller_id"] == uid:
            actor_role = "seller"
        else:
            actor_role = "buyer"

        # Sprawdź czy użytkownik jest adminem
        user_row = conn.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()
        if user_row and user_row["is_admin"]:
            actor_role = "admin"

        cur_status = order["status"]

        # Idempotency: tylko uczestnicy mogą "potwierdzić" obecny status
        # (uczestnik już zweryfikowany przez SELECT wyżej)
        if cur_status == new_status:
            return jsonify({"order": _order_dict(order)})

        if not _can_transition(cur_status, new_status, actor_role):
            allowed_for_role = [
                f"{f}→{t}" for (f, t), roles in _TRANSITIONS.items()
                if actor_role in roles and f == cur_status
            ]
            hint = f"Dozwolone przejścia z '{cur_status}': {allowed_for_role or 'brak'}"
            return jsonify({"error": f"Niedozwolone przejście '{cur_status}'→'{new_status}' dla roli '{actor_role}'. {hint}"}), 422

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Dodatkowe akcje zależne od nowego statusu
        extra_updates: dict[str, object] = {}

        if new_status == "shipped" and not order["shipped_at"]:
            extra_updates["shipped_at"] = now
            # Zresetuj auto-release od momentu wysyłki
            auto_release = (datetime.now() + timedelta(days=AUTO_RELEASE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
            extra_updates["auto_release_at"] = auto_release
            extra_updates["escrow_status"] = "shipped"

        elif new_status == "delivered" and not order["delivered_at"]:
            extra_updates["delivered_at"] = now
            extra_updates["escrow_status"] = "delivered"

        elif new_status == "cancelled":
            extra_updates["escrow_status"] = "refunded"
            # Przywróć dostępność produktu jeśli zamówienie nie było jeszcze w toku
            if cur_status in ("pending", "paid"):
                conn.execute(
                    "UPDATE products SET is_sold=0, status='available' WHERE id=?",
                    (order["product_id"],)
                )

        elif new_status == "paid":
            extra_updates["escrow_status"] = "paid_held"

        # Zbuduj SET clause
        set_parts = ["status=?"]
        params: list[object] = [new_status]
        for col, val in extra_updates.items():
            set_parts.append(f"{col}=?")
            params.append(val)
        params.append(oid)

        conn.execute(
            f"UPDATE orders SET {', '.join(set_parts)} WHERE id=?",
            params
        )

        _record_transition(conn, oid, uid, actor_role, cur_status, new_status, note)

        # Wypłata przy delivered
        if new_status == "delivered":
            order_updated = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
            _trigger_payout(conn, order_updated)

        conn.commit()

        # Powiadomienia
        try:
            _notify_status_change(conn, order, new_status, note)
        except Exception:
            pass

        order_final = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        return jsonify({"order": _order_dict(order_final)})
    finally:
        conn.close()


def _notify_status_change(conn, order, new_status: str, note: str) -> None:
    """Wysyła powiadomienie email do drugiej strony o zmianie statusu."""
    labels = {
        "paid":      "Płatność potwierdzona",
        "shipped":   "Zamówienie wysłane",
        "delivered": "Zamówienie dostarczone",
        "cancelled": "Zamówienie anulowane",
    }
    label = labels.get(new_status)
    if not label:
        return

    prod = conn.execute("SELECT name FROM products WHERE id=?", (order["product_id"],)).fetchone()
    prod_name = prod["name"] if prod else f"#{order['product_id']}"

    # Powiadom kupującego przy shipped i delivered
    if new_status in ("shipped", "delivered"):
        buyer = conn.execute("SELECT email, username FROM users WHERE id=?", (order["buyer_id"],)).fetchone()
        if buyer:
            from notifier import send_generic_notification
            send_generic_notification(
                buyer["email"], buyer["username"],
                label, prod_name, note
            )
    # Powiadom sprzedawcę przy cancelled
    elif new_status == "cancelled":
        seller = conn.execute("SELECT email, username FROM users WHERE id=?", (order["seller_id"],)).fetchone()
        if seller:
            from notifier import send_generic_notification
            send_generic_notification(
                seller["email"], seller["username"],
                label, prod_name, note
            )


# ─── Endpoint: historia statusów zamówienia ──────────────────────
@orders_bp.get("/<int:oid>/status-history")
def order_status_history(oid):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        order = conn.execute(
            "SELECT id FROM orders WHERE id=? AND (buyer_id=? OR seller_id=?)",
            (oid, uid, uid)
        ).fetchone()
        if not order:
            return jsonify({"error": "Nie znaleziono zamówienia."}), 404

        rows = conn.execute(
            """SELECT h.*, u.username as actor_username
               FROM order_status_history h
               LEFT JOIN users u ON u.id = h.actor_id
               WHERE h.order_id=?
               ORDER BY h.created_at ASC""",
            (oid,)
        ).fetchall()

        history = [
            {
                "id":             r["id"],
                "actor_username": r["actor_username"],
                "actor_role":     r["actor_role"],
                "from_status":    r["from_status"],
                "to_status":      r["to_status"],
                "note":           r["note"],
                "created_at":     r["created_at"],
            }
            for r in rows
        ]
        return jsonify({"history": history})
    finally:
        conn.close()
