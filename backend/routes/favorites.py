"""
routes/favorites.py — ulubione produkty użytkownika
"""
from flask import Blueprint, request, jsonify, session
from db import get_db
from routes.csrf import csrf_required

favorites_bp = Blueprint("favorites", __name__, url_prefix="/api/favorites")


def _prod_dict(row):
    import json
    return {
        "id":          row["id"],
        "name":        row["name"],
        "brand":       row["brand"],
        "price":       row["price"],
        "size":        row["size"],
        "condition":   row["condition"],
        "emoji":       row["emoji"],
        "description": row["description"],
        "seller_id":   row["seller_id"],
        "seller":      row["username"]  if "username"  in row.keys() else None,
        "avatar":      row["avatar"]    if "avatar"    in row.keys() else None,
        "images":      json.loads(row["images"] if "images" in row.keys() and row["images"] else "[]"),
        "is_sold":     bool(row["is_sold"]),
        "created_at":  row["created_at"],
    }


@favorites_bp.get("")
def get_favorites():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT p.*, u.username, u.avatar FROM favorites f
               JOIN products p ON p.id = f.product_id
               LEFT JOIN users u ON u.id = p.seller_id
               WHERE f.user_id = ? AND p.is_sold = 0""",
            (uid,)
        ).fetchall()
        return jsonify({"products": [_prod_dict(r) for r in rows]})
    finally:
        conn.close()


@favorites_bp.post("")
@csrf_required
def add_favorite():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    if not product_id:
        return jsonify({"error": "Brakuje product_id."}), 400

    conn = get_db()
    try:
        # Sprawdź czy produkt istnieje
        prod = conn.execute("SELECT id FROM products WHERE id=?", (product_id,)).fetchone()
        if not prod:
            return jsonify({"error": "Produkt nie istnieje."}), 404

        # Sprawdź czy już jest w ulubionych
        exists = conn.execute(
            "SELECT 1 FROM favorites WHERE user_id=? AND product_id=?", (uid, product_id)
        ).fetchone()
        if exists:
            return jsonify({"ok": True, "already": True})

        conn.execute(
            "INSERT INTO favorites (user_id, product_id) VALUES (?,?)",
            (uid, product_id)
        )
        conn.commit()
        return jsonify({"ok": True}), 201
    finally:
        conn.close()


@favorites_bp.delete("/<int:product_id>")
@csrf_required
def remove_favorite(product_id):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM favorites WHERE user_id=? AND product_id=?",
            (uid, product_id)
        )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()
