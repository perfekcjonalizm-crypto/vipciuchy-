"""
routes/admin.py — panel administracyjny (wymaga is_admin=1)
"""
from flask import Blueprint, request, jsonify, session
from db import get_db
from routes.csrf import csrf_required

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _admin_required(f):
    """Dekorator sprawdzający uprawnienia admina."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            return jsonify({"error": "Wymagane logowanie."}), 401
        conn = get_db()
        try:
            user = conn.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()
            if not user or not user["is_admin"]:
                return jsonify({"error": "Brak uprawnień administratora."}), 403
        finally:
            conn.close()
        return f(*args, **kwargs)
    return decorated


# ── UŻYTKOWNICY ───────────────────────────────────────────────────

@admin_bp.get("/users")
@_admin_required
def list_users():
    q = request.args.get("q", "").strip()
    try:
        page     = max(1, int(request.args.get("page", 1)))
        per_page = min(50, max(1, int(request.args.get("per_page", 20))))
    except (TypeError, ValueError):
        return jsonify({"error": "Nieprawidłowe parametry."}), 400
    offset = (page - 1) * per_page

    sql  = "SELECT id, username, email, avatar, is_admin, is_banned, is_active, failed_logins, locked_until, created_at FROM users"
    args = []
    if q:
        sql  += " WHERE username LIKE ? OR email LIKE ?"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    args += [per_page, offset]

    conn = get_db()
    try:
        rows  = conn.execute(sql, args).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM users" + (" WHERE username LIKE ? OR email LIKE ?" if q else ""),
            [f"%{q}%", f"%{q}%"] if q else []
        ).fetchone()[0]
        return jsonify({
            "users": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "pages": (total + per_page - 1) // per_page,
        })
    finally:
        conn.close()


@admin_bp.post("/users/<int:uid>/ban")
@csrf_required
@_admin_required
def ban_user(uid):
    conn = get_db()
    try:
        user = conn.execute("SELECT id, is_banned, is_admin FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return jsonify({"error": "Nie znaleziono użytkownika."}), 404
        if user["is_admin"]:
            return jsonify({"error": "Nie można zbanować admina."}), 403
        new_banned = 0 if user["is_banned"] else 1
        conn.execute("UPDATE users SET is_banned=? WHERE id=?", (new_banned, uid))
        conn.commit()
        return jsonify({"ok": True, "is_banned": bool(new_banned)})
    finally:
        conn.close()


@admin_bp.post("/users/<int:uid>/admin")
@csrf_required
@_admin_required
def toggle_admin(uid):
    """Nadaj/odbierz uprawnienia admina."""
    conn = get_db()
    try:
        user = conn.execute("SELECT id, is_admin FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return jsonify({"error": "Nie znaleziono użytkownika."}), 404
        new_val = 0 if user["is_admin"] else 1
        conn.execute("UPDATE users SET is_admin=? WHERE id=?", (new_val, uid))
        conn.commit()
        return jsonify({"ok": True, "is_admin": bool(new_val)})
    finally:
        conn.close()


# ── PRODUKTY ──────────────────────────────────────────────────────

@admin_bp.get("/products")
@_admin_required
def list_products():
    flagged_only = request.args.get("flagged") == "1"
    q = request.args.get("q", "").strip()
    try:
        page     = max(1, int(request.args.get("page", 1)))
        per_page = min(50, max(1, int(request.args.get("per_page", 20))))
    except (TypeError, ValueError):
        return jsonify({"error": "Nieprawidłowe parametry."}), 400
    offset = (page - 1) * per_page

    conds = []
    args  = []
    if flagged_only:
        conds.append("p.is_flagged=1")
    if q:
        conds.append("(p.name LIKE ? OR p.brand LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]

    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sql = f"""SELECT p.id, p.name, p.brand, p.price, p.emoji, p.is_sold, p.is_flagged,
                     p.flag_reason, p.created_at, u.username as seller
              FROM products p LEFT JOIN users u ON u.id=p.seller_id
              {where} ORDER BY p.created_at DESC LIMIT ? OFFSET ?"""
    args += [per_page, offset]

    count_sql = f"SELECT COUNT(*) FROM products p {where}"

    conn = get_db()
    try:
        rows  = conn.execute(sql, args).fetchall()
        total = conn.execute(count_sql, args[:-2]).fetchone()[0]
        return jsonify({
            "products": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "pages": (total + per_page - 1) // per_page,
        })
    finally:
        conn.close()


@admin_bp.delete("/products/<int:pid>")
@csrf_required
@_admin_required
def delete_product(pid):
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM products WHERE id=?", (pid,)).fetchone():
            return jsonify({"error": "Nie znaleziono produktu."}), 404
        conn.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@admin_bp.post("/products/<int:pid>/flag")
@csrf_required
@_admin_required
def flag_product(pid):
    data   = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()[:200]
    conn = get_db()
    try:
        prod = conn.execute("SELECT id, is_flagged FROM products WHERE id=?", (pid,)).fetchone()
        if not prod:
            return jsonify({"error": "Nie znaleziono produktu."}), 404
        new_flag = 0 if prod["is_flagged"] else 1
        conn.execute("UPDATE products SET is_flagged=?, flag_reason=? WHERE id=?",
                     (new_flag, reason if new_flag else "", pid))
        conn.commit()
        return jsonify({"ok": True, "is_flagged": bool(new_flag)})
    finally:
        conn.close()


# ── ZGŁOSZENIA ────────────────────────────────────────────────────

@admin_bp.get("/reports")
@_admin_required
def list_reports():
    status_filter = request.args.get("status", "pending")
    try:
        page     = max(1, int(request.args.get("page", 1)))
        per_page = min(50, max(1, int(request.args.get("per_page", 20))))
    except (TypeError, ValueError):
        return jsonify({"error": "Nieprawidłowe parametry."}), 400
    offset = (page - 1) * per_page

    sql = """SELECT r.*, u.username as reporter_name
             FROM reports r LEFT JOIN users u ON u.id=r.reporter_id
             WHERE r.status=? ORDER BY r.created_at DESC LIMIT ? OFFSET ?"""
    count_sql = "SELECT COUNT(*) FROM reports WHERE status=?"

    conn = get_db()
    try:
        rows  = conn.execute(sql, [status_filter, per_page, offset]).fetchall()
        total = conn.execute(count_sql, [status_filter]).fetchone()[0]
        return jsonify({
            "reports": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "pages": (total + per_page - 1) // per_page,
        })
    finally:
        conn.close()


@admin_bp.post("/reports/<int:rid>/resolve")
@csrf_required
@_admin_required
def resolve_report(rid):
    data   = request.get_json(silent=True) or {}
    action = data.get("action", "reviewed")
    if action not in ("reviewed", "dismissed"):
        return jsonify({"error": "Nieprawidłowa akcja."}), 400
    conn = get_db()
    try:
        if not conn.execute("SELECT 1 FROM reports WHERE id=?", (rid,)).fetchone():
            return jsonify({"error": "Nie znaleziono zgłoszenia."}), 404
        conn.execute("UPDATE reports SET status=? WHERE id=?", (action, rid))
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


# ── STATYSTYKI ────────────────────────────────────────────────────

@admin_bp.get("/stats")
@_admin_required
def stats():
    conn = get_db()
    try:
        return jsonify({
            "users":         conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "users_banned":  conn.execute("SELECT COUNT(*) FROM users WHERE is_banned=1").fetchone()[0],
            "products":      conn.execute("SELECT COUNT(*) FROM products WHERE is_sold=0").fetchone()[0],
            "products_sold": conn.execute("SELECT COUNT(*) FROM products WHERE is_sold=1").fetchone()[0],
            "products_flagged": conn.execute("SELECT COUNT(*) FROM products WHERE is_flagged=1").fetchone()[0],
            "orders":        conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "reports_pending": conn.execute("SELECT COUNT(*) FROM reports WHERE status='pending'").fetchone()[0],
        })
    finally:
        conn.close()
