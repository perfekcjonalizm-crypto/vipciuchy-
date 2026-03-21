"""
routes/upload.py — upload zdjęć produktu
"""
import os
import uuid
from flask import Blueprint, request, jsonify, session, send_from_directory
from routes.csrf import csrf_required

upload_bp = Blueprint("upload", __name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}
MAX_SIZE = 5 * 1024 * 1024  # 5 MB

# Upewnij się że katalog istnieje
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


@upload_bp.post("/api/upload")
@csrf_required
def upload_file():
    if not session.get("user_id"):
        return jsonify({"error": "Wymagane logowanie."}), 401

    if "file" not in request.files:
        return jsonify({"error": "Brak pliku."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Nie wybrano pliku."}), 400
    if not _allowed(file.filename):
        return jsonify({"error": "Dozwolone formaty: JPG, PNG, WEBP, GIF."}), 400

    # Sprawdź rozmiar
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_SIZE:
        return jsonify({"error": "Plik za duży (max 5 MB)."}), 413

    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    file.save(path)

    url = f"/api/uploads/{filename}"
    return jsonify({"url": url, "filename": filename}), 201


@upload_bp.get("/api/uploads/<filename>")
def serve_upload(filename):
    # Zabezpieczenie przed path traversal
    safe = os.path.basename(filename)
    return send_from_directory(UPLOAD_DIR, safe)
