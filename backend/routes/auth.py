"""
routes/auth.py — rejestracja, logowanie, wylogowanie, /me, weryfikacja
"""
import datetime
import hmac
import os
import secrets
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db
from routes.csrf import csrf_required

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Tryb DEV gdy brak klucza Resend — kody widoczne w odpowiedzi API
IS_DEV = not bool(os.environ.get("RESEND_API_KEY"))


def _user_dict(row):
    return {
        "id":             row["id"],
        "username":       row["username"],
        "email":          row["email"],
        "avatar":         row["avatar"],
        "created_at":     row["created_at"],
        "email_verified": row["email_verified"] if "email_verified" in row.keys() else 1,
        "phone_verified": row["phone_verified"] if "phone_verified" in row.keys() else 1,
        "is_admin":       bool(row["is_admin"])  if "is_admin"  in row.keys() else False,
        "is_banned":      bool(row["is_banned"]) if "is_banned" in row.keys() else False,
        "bio":        row["bio"]         if "bio"         in row.keys() else '',
        "city":       row["city"]        if "city"        in row.keys() else '',
        "address":    row["address"]     if "address"     in row.keys() else '',
        "postal_code":row["postal_code"] if "postal_code" in row.keys() else '',
        "avatar_url": row["avatar_url"]  if "avatar_url"  in row.keys() else '',
    }


def _gen_code():
    return str(secrets.randbelow(900000) + 100000)


def _save_code(conn, user_id, code_type, code):
    expires = (datetime.datetime.now() + datetime.timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM verification_tokens WHERE user_id=? AND type=?", (user_id, code_type))
    conn.execute(
        "INSERT INTO verification_tokens (user_id, type, code, expires_at) VALUES (?,?,?,?)",
        (user_id, code_type, code, expires)
    )


@auth_bp.post("/register")
def register():
    data     = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    email    = (data.get("email")    or "").strip().lower()
    password = (data.get("password") or "")
    phone    = (data.get("phone")    or "").strip()
    gdpr_consent = data.get("gdpr_consent", False)

    if not username or not email or not password or not phone:
        return jsonify({"error": "Wypełnij wszystkie pola."}), 400
    if len(username) < 3:
        return jsonify({"error": "Nazwa użytkownika min. 3 znaki."}), 400
    if len(password) < 6:
        return jsonify({"error": "Hasło min. 6 znaków."}), 400
    if "@" not in email:
        return jsonify({"error": "Niepoprawny e-mail."}), 400
    if len(phone) < 9:
        return jsonify({"error": "Niepoprawny numer telefonu."}), 400
    if not gdpr_consent:
        return jsonify({"error": "Wymagana akceptacja Regulaminu i Polityki Prywatności."}), 400

    conn = get_db()
    try:
        pw_hash = generate_password_hash(password, method='pbkdf2:sha256')
        avatar  = username[0].upper()
        conn.execute(
            "INSERT INTO users (username, email, password_hash, avatar, phone, email_verified, phone_verified, is_active) VALUES (?,?,?,?,?,0,0,0)",
            (username, email, pw_hash, avatar, phone)
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        uid  = user["id"]

        # Generuj kod email (SMS usunięty — weryfikacja tylko przez email)
        email_code = _gen_code()
        _save_code(conn, uid, "email", email_code)
        conn.commit()

        from notifier import send_email_code
        send_email_code(email, email_code)

        response = {"pending_verification": True, "user_id": uid}
        if IS_DEV:
            response["_dev_email_code"] = email_code

        return jsonify(response), 201

    except Exception as e:
        if "UNIQUE" in str(e):
            return jsonify({"error": "Taka nazwa użytkownika lub e-mail już istnieje."}), 409
        return jsonify({"error": "Błąd serwera."}), 500
    finally:
        conn.close()


@auth_bp.post("/verify")
def verify():
    """Weryfikacja e-mail po rejestracji (SMS usunięty)."""
    data       = request.get_json(silent=True) or {}
    user_id    = data.get("user_id")
    email_code = (data.get("email_code") or "").strip()

    if not user_id or not email_code:
        return jsonify({"error": "Podaj kod weryfikacyjny."}), 400

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM verification_tokens WHERE user_id=? AND type='email' AND used=0 AND expires_at > ?",
            (user_id, now)
        ).fetchone()
        if not row:
            return jsonify({"error": "Kod wygasł lub jest nieprawidłowy."}), 400
        if not hmac.compare_digest(row["code"], email_code):
            return jsonify({"error": "Błędny kod weryfikacyjny."}), 400

        # Aktywuj konto
        conn.execute("UPDATE verification_tokens SET used=1 WHERE user_id=? AND type='email'", (user_id,))
        conn.execute(
            "UPDATE users SET email_verified=1, phone_verified=1, is_active=1 WHERE id=?",
            (user_id,)
        )
        conn.commit()

        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        session["user_id"] = user["id"]
        from routes.csrf import generate_csrf
        return jsonify({"user": _user_dict(user), "csrf": generate_csrf()})
    finally:
        conn.close()


@auth_bp.post("/resend")
def resend():
    """Ponowne wysłanie kodów weryfikacyjnych."""
    data    = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "Brak user_id."}), 400

    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id=? AND is_active=0", (user_id,)).fetchone()
        if not user:
            return jsonify({"error": "Konto nie wymaga weryfikacji."}), 400

        email_code = _gen_code()
        phone_code = _gen_code()
        _save_code(conn, user_id, "email", email_code)
        _save_code(conn, user_id, "phone", phone_code)
        conn.commit()

        from notifier import send_email_code, send_sms_code
        send_email_code(user["email"], email_code)
        send_sms_code(user["phone"], phone_code)

        response = {"ok": True}
        if IS_DEV:
            response["_dev_email_code"] = email_code
            response["_dev_phone_code"] = phone_code
        return jsonify(response)
    finally:
        conn.close()


@auth_bp.post("/login")
def login():
    data     = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "")
    ip       = request.remote_addr or "unknown"

    if not username or not password:
        return jsonify({"error": "Podaj login i hasło."}), 400

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE username=? OR email=?",
            (username, username.lower())
        ).fetchone()

        # Loguj próbę
        conn.execute(
            "INSERT INTO login_attempts (ip, username, success) VALUES (?,?,0)",
            (ip, username[:100])
        )

        # Sprawdź blokadę konta
        import datetime as _dt
        if user:
            if user["is_banned"] if "is_banned" in user.keys() else False:
                conn.commit()
                return jsonify({"error": "Konto zostało zablokowane przez administratora."}), 403

            locked = user["locked_until"] if "locked_until" in user.keys() else None
            if locked:
                now_str = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if now_str < locked:
                    mins = int((_dt.datetime.strptime(locked, "%Y-%m-%d %H:%M:%S") - _dt.datetime.now()).total_seconds() / 60) + 1
                    conn.commit()
                    return jsonify({"error": f"Konto tymczasowo zablokowane. Spróbuj za {mins} min."}), 429

        if not user or not check_password_hash(user["password_hash"], password):
            # Zwiększ licznik nieudanych logowań
            if user:
                failed = (user["failed_logins"] or 0) + 1
                if failed >= 5:
                    locked_until = (_dt.datetime.now() + _dt.timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
                    conn.execute(
                        "UPDATE users SET failed_logins=?, locked_until=? WHERE id=?",
                        (failed, locked_until, user["id"])
                    )
                else:
                    conn.execute("UPDATE users SET failed_logins=? WHERE id=?", (failed, user["id"]))
            conn.commit()
            return jsonify({"error": "Błędny login lub hasło."}), 401

        # Sprawdź czy konto jest aktywne (zweryfikowane)
        if "is_active" in user.keys() and not user["is_active"]:
            conn.commit()
            return jsonify({
                "error": "Konto nie zostało jeszcze zweryfikowane. Sprawdź e-mail i SMS.",
                "pending_verification": True,
                "user_id": user["id"]
            }), 403

        # Sukces — resetuj licznik
        conn.execute(
            "UPDATE login_attempts SET success=1 WHERE id=(SELECT MAX(id) FROM login_attempts WHERE username=?)",
            (username[:100],)
        )
        conn.execute("UPDATE users SET failed_logins=0, locked_until=NULL WHERE id=?", (user["id"],))
        conn.commit()

        session["user_id"] = user["id"]
        from routes.csrf import generate_csrf
        return jsonify({"user": _user_dict(user), "csrf": generate_csrf()})
    finally:
        conn.close()


@auth_bp.post("/logout")
@csrf_required
def logout():
    session.pop("user_id", None)
    return jsonify({"ok": True})


@auth_bp.get("/me")
def me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"user": None})
    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            session.clear()
            return jsonify({"user": None})
        return jsonify({"user": _user_dict(user)})
    finally:
        conn.close()


@auth_bp.get("/data")
def export_data():
    """RODO Art. 20 — prawo do przenoszenia danych."""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        user     = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        products = conn.execute("SELECT * FROM products WHERE seller_id=?", (uid,)).fetchall()
        orders   = conn.execute("SELECT * FROM orders WHERE buyer_id=?", (uid,)).fetchall()
        messages = conn.execute(
            "SELECT * FROM messages WHERE from_user_id=? OR to_user_id=?", (uid, uid)
        ).fetchall()

        return jsonify({
            "exported_at": datetime.datetime.now().isoformat(),
            "user": {
                "id":         user["id"],
                "username":   user["username"],
                "email":      user["email"],
                "avatar":     user["avatar"],
                "created_at": user["created_at"],
            },
            "products": [dict(p) for p in products],
            "orders":   [dict(o) for o in orders],
            "messages": [{"id": m["id"], "product_id": m["product_id"],
                          "content": m["content"], "created_at": m["created_at"]} for m in messages],
        })
    finally:
        conn.close()


@auth_bp.post("/reset-request")
def reset_request():
    """Żądanie resetu hasła — generuje 6-cyfrowy kod i zapisuje go."""
    data  = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email or "@" not in email:
        return jsonify({"error": "Podaj poprawny e-mail."}), 400

    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        # Zawsze zwróć ok — nie ujawniaj czy email istnieje
        if not user:
            return jsonify({"ok": True})

        code = _gen_code()
        _save_code(conn, user["id"], "reset", code)
        conn.commit()

        from notifier import send_email_code
        send_email_code(email, code)

        response = {"ok": True}
        if IS_DEV:
            response["_dev_code"] = code
        return jsonify(response)
    finally:
        conn.close()


@auth_bp.post("/reset")
def reset_password():
    """Ustawia nowe hasło po weryfikacji kodu."""
    data         = request.get_json(silent=True) or {}
    email        = (data.get("email")        or "").strip().lower()
    code         = (data.get("code")         or "").strip()
    new_password = (data.get("new_password") or "")

    if not email or not code or not new_password:
        return jsonify({"error": "Wypełnij wszystkie pola."}), 400
    if len(new_password) < 6:
        return jsonify({"error": "Hasło musi mieć co najmniej 6 znaków."}), 400

    now  = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user:
            return jsonify({"error": "Nieprawidłowy kod lub e-mail."}), 400

        token = conn.execute(
            "SELECT * FROM verification_tokens WHERE user_id=? AND type='reset' AND used=0 AND expires_at > ?",
            (user["id"], now)
        ).fetchone()
        if not token or not hmac.compare_digest(token["code"], code):
            return jsonify({"error": "Nieprawidłowy lub wygasły kod."}), 400

        pw_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash, user["id"]))
        conn.execute("UPDATE verification_tokens SET used=1 WHERE id=?", (token["id"],))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@auth_bp.put("/profile")
@csrf_required
def update_profile():
    """Aktualizacja profilu."""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401
    data        = request.get_json(silent=True) or {}
    avatar      = (data.get("avatar")      or "").strip()[:4]
    phone       = (data.get("phone")       or "").strip()[:20]
    bio         = (data.get("bio")         or "").strip()[:300]
    city        = (data.get("city")        or "").strip()[:100]
    address     = (data.get("address")     or "").strip()[:200]
    postal_code = (data.get("postal_code") or "").strip()[:10]
    avatar_url  = (data.get("avatar_url")  or "").strip()[:500]

    conn = get_db()
    try:
        updates = []
        params  = []
        if avatar:      updates.append("avatar=?");      params.append(avatar)
        if phone:       updates.append("phone=?");       params.append(phone)
        if bio is not None and "bio" in data:
            updates.append("bio=?"); params.append(bio)
        if city is not None and "city" in data:
            updates.append("city=?"); params.append(city)
        if address is not None and "address" in data:
            updates.append("address=?"); params.append(address)
        if postal_code is not None and "postal_code" in data:
            updates.append("postal_code=?"); params.append(postal_code)
        if avatar_url is not None and "avatar_url" in data:
            updates.append("avatar_url=?"); params.append(avatar_url)
        if updates:
            params.append(uid)
            conn.execute("UPDATE users SET " + ", ".join(updates) + " WHERE id=?", params)
            conn.commit()
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return jsonify({"user": _user_dict(user)})
    finally:
        conn.close()


@auth_bp.delete("/account")
def delete_account():
    """RODO Art. 17 — prawo do bycia zapomnianym."""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data     = request.get_json(silent=True) or {}
    password = data.get("password", "")

    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return jsonify({"error": "Użytkownik nie istnieje."}), 404

        if not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "Nieprawidłowe hasło."}), 401

        anon = f"usunieto_{uid}"
        # Usuń produkty, ogłoszenia, wiadomości, ulubione i tokeny
        conn.execute("DELETE FROM products WHERE seller_id=?", (uid,))
        conn.execute("DELETE FROM orders WHERE buyer_id=? OR seller_id=?", (uid, uid))
        conn.execute("DELETE FROM messages WHERE from_user_id=? OR to_user_id=?", (uid, uid))
        conn.execute("DELETE FROM favorites WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM verification_tokens WHERE user_id=?", (uid,))
        # Zanonimizuj konto (RODO)
        conn.execute(
            "UPDATE users SET username=?, email=?, password_hash=?, avatar='' WHERE id=?",
            (anon, f"{anon}@deleted.local", secrets.token_hex(32), uid)
        )
        conn.commit()
        session.clear()
        return jsonify({"ok": True, "message": "Konto zostało usunięte."})
    finally:
        conn.close()
