"""
routes/reports.py — system zgłaszania ofert i użytkowników
"""
from flask import Blueprint, request, jsonify, session
from db import get_db
from routes.csrf import csrf_required

reports_bp = Blueprint("reports", __name__, url_prefix="/api/reports")

VALID_REASONS = [
    "Fałszywa oferta",
    "Spam / powielona oferta",
    "Nieodpowiednie treści",
    "Oszustwo / próba wyłudzenia",
    "Naruszenie regulaminu",
    "Inne",
]


@reports_bp.post("")
@csrf_required
def submit_report():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Wymagane logowanie."}), 401

    data        = request.get_json(silent=True) or {}
    target_type = (data.get("target_type") or "").strip()
    target_id   = data.get("target_id")
    reason      = (data.get("reason") or "").strip()[:500]

    if target_type not in ("product", "user"):
        return jsonify({"error": "Nieprawidłowy typ zgłoszenia."}), 400
    if not target_id or not reason:
        return jsonify({"error": "Brakuje wymaganych pól."}), 400
    try:
        target_id = int(target_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Nieprawidłowe target_id."}), 400

    conn = get_db()
    try:
        # Sprawdź czy cel istnieje
        if target_type == "product":
            if not conn.execute("SELECT 1 FROM products WHERE id=?", (target_id,)).fetchone():
                return jsonify({"error": "Nie znaleziono produktu."}), 404
        else:
            if not conn.execute("SELECT 1 FROM users WHERE id=?", (target_id,)).fetchone():
                return jsonify({"error": "Nie znaleziono użytkownika."}), 404

        # Ogranicz: max 1 zgłoszenie danej oferty/usera od tego samego użytkownika
        existing = conn.execute(
            "SELECT 1 FROM reports WHERE reporter_id=? AND target_type=? AND target_id=? AND status='pending'",
            (uid, target_type, target_id)
        ).fetchone()
        if existing:
            return jsonify({"error": "Już zgłosiłeś ten element. Czeka na rozpatrzenie."}), 409

        conn.execute(
            "INSERT INTO reports (reporter_id, target_type, target_id, reason) VALUES (?,?,?,?)",
            (uid, target_type, target_id, reason)
        )
        conn.commit()
        return jsonify({"ok": True}), 201
    finally:
        conn.close()
