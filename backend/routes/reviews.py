"""
routes/reviews.py — system ocen sprzedawców
"""
from flask import Blueprint, request, jsonify, session
from db import get_db
from routes.csrf import csrf_required

reviews_bp = Blueprint("reviews", __name__, url_prefix="/api/reviews")


@reviews_bp.post("")
@csrf_required
def create_review():
    """Dodaj ocenę sprzedawcy po zrealizowanym zamówieniu."""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data        = request.get_json(silent=True) or {}
    order_id    = data.get("order_id")
    rating      = data.get("rating")
    comment     = (data.get("comment") or "").strip()[:500]

    if not order_id or not rating:
        return jsonify({"error": "Brakuje order_id lub rating."}), 400
    try:
        order_id = int(order_id)
        rating   = int(rating)
        if not (1 <= rating <= 5):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "rating musi być od 1 do 5."}), 400

    conn = get_db()
    try:
        # Sprawdź czy zamówienie należy do tego kupującego
        order = conn.execute(
            "SELECT * FROM orders WHERE id=? AND buyer_id=? AND status='paid'",
            (order_id, uid)
        ).fetchone()
        if not order:
            return jsonify({"error": "Nie znaleziono zamówienia lub nie możesz ocenić tej transakcji."}), 404

        reviewed_id = order["seller_id"]
        if not reviewed_id:
            return jsonify({"error": "Brak sprzedawcy."}), 400

        # Sprawdź czy już ocenił
        existing = conn.execute(
            "SELECT 1 FROM reviews WHERE reviewer_id=? AND order_id=?",
            (uid, order_id)
        ).fetchone()
        if existing:
            return jsonify({"error": "Już oceniłeś/aś tę transakcję."}), 409

        conn.execute(
            "INSERT INTO reviews (reviewer_id, reviewed_id, order_id, rating, comment) VALUES (?,?,?,?,?)",
            (uid, reviewed_id, order_id, rating, comment)
        )
        conn.commit()
        return jsonify({"ok": True}), 201
    finally:
        conn.close()


@reviews_bp.get("/user/<int:uid>")
def user_reviews(uid):
    """Pobierz oceny sprzedawcy."""
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT r.*, u.username as reviewer_name, u.avatar as reviewer_avatar
               FROM reviews r LEFT JOIN users u ON u.id=r.reviewer_id
               WHERE r.reviewed_id=? ORDER BY r.created_at DESC LIMIT 20""",
            (uid,)
        ).fetchall()
        avg = conn.execute(
            "SELECT AVG(rating), COUNT(*) FROM reviews WHERE reviewed_id=?",
            (uid,)
        ).fetchone()
        return jsonify({
            "reviews": [dict(r) for r in rows],
            "avg_rating": round(avg[0], 1) if avg[0] else None,
            "count": avg[1],
        })
    finally:
        conn.close()
