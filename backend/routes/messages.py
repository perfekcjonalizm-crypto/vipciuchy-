"""
routes/messages.py — prywatny czat między użytkownikami

Model:     rozmowa = para użytkowników (min_id, max_id) — niezależna od produktu
Oferty:    wiadomość z msg_type='product_link' dołącza podgląd oferty
Odczyt:    is_read=0/1 per wiadomość; PATCH /thread/<id>/read oznacza wszystkie
Powiadomienia: email do odbiorcy przy każdej nowej wiadomości (raz na 5 min per para)

Endpoints:
  GET    /api/messages/conversations           — lista rozmów bieżącego użytkownika
  GET    /api/messages/unread-count            — liczba nieprzeczytanych wiadomości
  GET    /api/messages/thread/<other_id>       — wiadomości z konkretną osobą
  POST   /api/messages                         — wyślij wiadomość
  PATCH  /api/messages/thread/<other_id>/read  — oznacz rozmowę jako przeczytaną
"""
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from db import get_db
from routes.csrf import csrf_required

messages_bp = Blueprint("messages", __name__, url_prefix="/api/messages")

MAX_MSG_LEN      = 2000
PAGE_SIZE        = 50
# Minimalny odstęp między mailami dla tej samej pary użytkowników (w minutach)
NOTIF_COOLDOWN   = 5


# ─── Helpers ──────────────────────────────────────────────────────

def _msg_dict(row):
    keys = row.keys()
    d = {
        "id":           row["id"],
        "from_user_id": row["from_user_id"],
        "to_user_id":   row["to_user_id"],
        "content":      row["content"],
        "msg_type":     row["msg_type"] if "msg_type" in keys else "text",
        "is_read":      bool(row["is_read"]) if "is_read" in keys else False,
        "created_at":   row["created_at"],
        "from_username": row["from_username"] if "from_username" in keys else None,
        "from_avatar":   row["from_avatar"]   if "from_avatar"   in keys else None,
    }
    # Podgląd oferty dołączonej do wiadomości
    if "product_id" in keys and row["product_id"]:
        d["product"] = {
            "id":    row["product_id"],
            "name":  row["product_name"]  if "product_name"  in keys else None,
            "price": row["product_price"] if "product_price" in keys else None,
            "emoji": row["product_emoji"] if "product_emoji" in keys else "📦",
            "is_sold": bool(row["product_is_sold"]) if "product_is_sold" in keys else None,
        }
    else:
        d["product"] = None
    return d


def _thread_key(uid_a, uid_b):
    """Deterministyczny klucz rozmowy: (min, max) niezależny od kierunku."""
    return (min(uid_a, uid_b), max(uid_a, uid_b))


def _should_notify(conn, from_uid, to_uid) -> bool:
    """True jeśli od ostatniego maila minęło NOTIF_COOLDOWN minut."""
    cutoff = (datetime.now() - timedelta(minutes=NOTIF_COOLDOWN)).strftime("%Y-%m-%d %H:%M:%S")
    row = conn.execute(
        """SELECT MAX(created_at) as last_notified
           FROM messages
           WHERE from_user_id=? AND to_user_id=? AND created_at > ?""",
        (from_uid, to_uid, cutoff)
    ).fetchone()
    # Jeśli w oknie cooldown nie było żadnej wcześniejszej wiadomości → wyślij
    return row["last_notified"] is None


# ─── Endpoint: lista rozmów ───────────────────────────────────────

@messages_bp.get("/conversations")
def get_conversations():
    """
    Zwraca listę rozmów bieżącego użytkownika, posortowanych po dacie
    ostatniej wiadomości. Każda rozmowa zawiera:
      - dane drugiego użytkownika
      - ostatnią wiadomość
      - liczbę nieprzeczytanych
    """
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        # Krok 1: ostatnia wiadomość per para użytkowników (bez window functions)
        rows = conn.execute(
            """
            SELECT
                CASE WHEN m.from_user_id = :uid
                     THEN m.to_user_id
                     ELSE m.from_user_id
                END                              AS other_id,
                MAX(m.created_at)               AS last_at
            FROM messages m
            WHERE m.from_user_id = :uid OR m.to_user_id = :uid
            GROUP BY other_id
            ORDER BY last_at DESC
            LIMIT 100
            """,
            {"uid": uid}
        ).fetchall()

        if not rows:
            return jsonify({"conversations": []})

        # Krok 2: dla każdej pary pobierz szczegóły ostatniej wiadomości + licznik
        result = []
        for row in rows:
            other_id = row["other_id"]
            last_at  = row["last_at"]

            last_msg = conn.execute(
                """SELECT content, msg_type FROM messages
                   WHERE ((from_user_id=:uid AND to_user_id=:oid)
                       OR (from_user_id=:oid AND to_user_id=:uid))
                   ORDER BY created_at DESC LIMIT 1""",
                {"uid": uid, "oid": other_id}
            ).fetchone()

            other_user = conn.execute(
                "SELECT username, avatar, avatar_url FROM users WHERE id=?",
                (other_id,)
            ).fetchone()

            unread = conn.execute(
                "SELECT COUNT(*) AS cnt FROM messages WHERE from_user_id=? AND to_user_id=? AND is_read=0",
                (other_id, uid)
            ).fetchone()

            result.append({
                "other_user": {
                    "id":       other_id,
                    "username": other_user["username"] if other_user else None,
                    "avatar":   (other_user["avatar_url"] or other_user["avatar"] or "") if other_user else "",
                },
                "last_message":  last_msg["content"]  if last_msg else "",
                "last_msg_type": last_msg["msg_type"]  if last_msg else "text",
                "last_at":       last_at,
                "unread_count":  unread["cnt"] if unread else 0,
            })

        return jsonify({"conversations": result})
    finally:
        conn.close()


# ─── Endpoint: liczba nieprzeczytanych ───────────────────────────

@messages_bp.get("/unread-count")
def unread_count():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE to_user_id=? AND is_read=0",
            (uid,)
        ).fetchone()
        return jsonify({"unread": row["cnt"]})
    finally:
        conn.close()


# ─── Endpoint: wiadomości z konkretną osobą ───────────────────────

@messages_bp.get("/thread/<int:other_id>")
def get_thread(other_id):
    """
    Zwraca historię rozmowy z użytkownikiem <other_id>.
    Opcjonalny parametr ?before=<id> do paginacji (wiadomości starsze niż <id>).
    """
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401
    if uid == other_id:
        return jsonify({"error": "Nie możesz pisać sam do siebie."}), 400

    before_id = request.args.get("before", type=int)

    conn = get_db()
    try:
        # Sprawdź czy drugi użytkownik istnieje
        other = conn.execute("SELECT id, username FROM users WHERE id=?", (other_id,)).fetchone()
        if not other:
            return jsonify({"error": "Użytkownik nie istnieje."}), 404

        where_extra = "AND m.id < :before_id" if before_id else ""

        rows = conn.execute(
            f"""
            SELECT
                m.*,
                u.username   AS from_username,
                u.avatar_url AS from_avatar,
                p.name       AS product_name,
                p.price      AS product_price,
                p.emoji      AS product_emoji,
                p.is_sold    AS product_is_sold
            FROM messages m
            LEFT JOIN users    u ON u.id = m.from_user_id
            LEFT JOIN products p ON p.id = m.product_id
            WHERE (
                (m.from_user_id = :uid AND m.to_user_id = :other)
             OR (m.from_user_id = :other AND m.to_user_id = :uid)
            )
            {where_extra}
            ORDER BY m.created_at DESC
            LIMIT :limit
            """,
            {"uid": uid, "other": other_id, "before_id": before_id, "limit": PAGE_SIZE}
        ).fetchall()

        # Odwróć — najstarsze na górze
        messages = [_msg_dict(r) for r in reversed(rows)]
        return jsonify({
            "messages":    messages,
            "other_user":  {"id": other["id"], "username": other["username"]},
            "has_more":    len(rows) == PAGE_SIZE,
        })
    finally:
        conn.close()


# ─── Endpoint: wyślij wiadomość ──────────────────────────────────

@messages_bp.post("")
@csrf_required
def send_message():
    """
    Wysyła wiadomość prywatną.

    Body JSON:
      {
        "to_user_id": 5,
        "content":    "Hej, czy ta kurtka jest dostępna?",
        "product_id": 12,           // opcjonalne — dołącz podgląd oferty
        "msg_type":   "text"        // "text" | "product_link"
      }

    Gdy product_id jest podany, msg_type automatycznie ustawiane na "product_link".
    """
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data       = request.get_json(silent=True) or {}
    to_user_id = data.get("to_user_id")
    content    = (data.get("content") or "").strip()
    product_id = data.get("product_id") or None
    msg_type   = (data.get("msg_type") or "text").strip().lower()

    # Walidacja
    if not to_user_id:
        return jsonify({"error": "Brakuje to_user_id."}), 400
    if not content:
        return jsonify({"error": "Wiadomość nie może być pusta."}), 400
    if len(content) > MAX_MSG_LEN:
        return jsonify({"error": f"Wiadomość zbyt długa (max {MAX_MSG_LEN} znaków)."}), 400
    if uid == to_user_id:
        return jsonify({"error": "Nie możesz pisać sam do siebie."}), 400
    if msg_type not in ("text", "product_link"):
        msg_type = "text"

    # Jeśli podano product_id → zawsze product_link
    if product_id:
        msg_type = "product_link"

    conn = get_db()
    try:
        # Sprawdź odbiorcę
        recipient = conn.execute(
            "SELECT id, username, email, is_banned FROM users WHERE id=?", (to_user_id,)
        ).fetchone()
        if not recipient:
            return jsonify({"error": "Odbiorca nie istnieje."}), 404
        if recipient["is_banned"]:
            return jsonify({"error": "Nie możesz napisać do tego użytkownika."}), 403

        # Sprawdź produkt jeśli podano
        if product_id:
            prod_check = conn.execute("SELECT id FROM products WHERE id=?", (product_id,)).fetchone()
            if not prod_check:
                return jsonify({"error": "Podana oferta nie istnieje."}), 400

        notify = _should_notify(conn, uid, to_user_id)

        cur = conn.execute(
            "INSERT INTO messages (from_user_id, to_user_id, product_id, content, msg_type) VALUES (?,?,?,?,?)",
            (uid, to_user_id, product_id, content, msg_type)
        )
        conn.commit()
        msg_id = cur.lastrowid

        row = conn.execute(
            """SELECT m.*, u.username AS from_username, u.avatar_url AS from_avatar,
                      p.name AS product_name, p.price AS product_price,
                      p.emoji AS product_emoji, p.is_sold AS product_is_sold
               FROM messages m
               LEFT JOIN users u ON u.id = m.from_user_id
               LEFT JOIN products p ON p.id = m.product_id
               WHERE m.id=?""",
            (msg_id,)
        ).fetchone()

        # Powiadomienie email — raz na NOTIF_COOLDOWN minut per rozmowa
        if notify:
            try:
                sender = conn.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
                prod_name = None
                if product_id:
                    p = conn.execute("SELECT name FROM products WHERE id=?", (product_id,)).fetchone()
                    prod_name = p["name"] if p else None
                from notifier import send_message_notification
                send_message_notification(
                    recipient["email"], recipient["username"],
                    sender["username"] if sender else "Ktoś",
                    prod_name or "wiadomość prywatna"
                )
            except Exception:
                pass

        return jsonify({"message": _msg_dict(row)}), 201
    finally:
        conn.close()


# ─── Endpoint: oznacz rozmowę jako przeczytaną ───────────────────

@messages_bp.patch("/thread/<int:other_id>/read")
@csrf_required
def mark_thread_read(other_id):
    """
    Oznacza wszystkie wiadomości od <other_id> do bieżącego użytkownika
    jako przeczytane. Wywołaj przy otwarciu rozmowy.
    """
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        conn.execute(
            "UPDATE messages SET is_read=1 WHERE from_user_id=? AND to_user_id=? AND is_read=0",
            (other_id, uid)
        )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


# ─── Endpoint: backward compat — wiadomości per produkt ──────────
# Pozostawione żeby stary frontend nie pękł; kieruje do nowego modelu.

@messages_bp.get("/<int:product_id>")
def get_messages_by_product(product_id):
    """
    Backward-compat: zwraca wiadomości dotyczące produktu <product_id>
    wymienione między bieżącym użytkownikiem a sprzedawcą/kupującym.
    """
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT m.*, u.username AS from_username, u.avatar_url AS from_avatar,
                      p.name AS product_name, p.price AS product_price,
                      p.emoji AS product_emoji, p.is_sold AS product_is_sold
               FROM messages m
               LEFT JOIN users    u ON u.id = m.from_user_id
               LEFT JOIN products p ON p.id = m.product_id
               WHERE m.product_id=?
                 AND (m.from_user_id=? OR m.to_user_id=?)
               ORDER BY m.created_at ASC""",
            (product_id, uid, uid)
        ).fetchall()
        return jsonify({"messages": [_msg_dict(r) for r in rows]})
    finally:
        conn.close()
