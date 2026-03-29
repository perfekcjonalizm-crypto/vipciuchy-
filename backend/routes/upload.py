"""
routes/upload.py — upload zdjęć przez Cloudinary
"""
import os
import cloudinary
import cloudinary.uploader
from flask import Blueprint, request, jsonify, session

upload_bp = Blueprint("upload", __name__)

cloudinary.config(
    cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
    api_key    = os.environ.get("CLOUDINARY_API_KEY", ""),
    api_secret = os.environ.get("CLOUDINARY_API_SECRET", ""),
    secure     = True,
)

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}
MAX_SIZE    = 5 * 1024 * 1024  # 5 MB


def _allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


@upload_bp.post("/api/upload")
def upload_file():
    if not session.get("user_id"):
        return jsonify({"error": "Wymagane logowanie."}), 401

    if "file" not in request.files:
        return jsonify({"error": "Brak pliku."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Nie wybrano pliku."}), 400
    if not _allowed(file.filename):
        return jsonify({"error": "Dozwolone formaty: JPG, PNG, WEBP."}), 400

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_SIZE:
        return jsonify({"error": "Plik za duży (max 5 MB)."}), 413

    result = cloudinary.uploader.upload(
        file,
        folder        = "vipciuchy/avatars",
        transformation= [{"width": 400, "height": 400, "crop": "fill", "gravity": "face"}],
    )

    url = result.get("secure_url", "")
    return jsonify({"url": url, "filename": result.get("public_id", "")}), 201
