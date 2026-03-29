"""
routes/google_auth.py — logowanie przez Google OAuth 2.0
"""
import os
import secrets
import logging
import requests as _requests
from flask import Blueprint, request, jsonify, session, redirect
from db import get_db
from werkzeug.security import generate_password_hash
from urllib.parse import urlencode

google_auth_bp = Blueprint("google_auth", __name__, url_prefix="/api/auth/google")

FRONTEND_URL = "https://vipciuchy.pl"


def _cfg():
    """Odczytaj zmienne środowiskowe w czasie żądania (nie przy starcie modułu)."""
    return (
        os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
        os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
        os.environ.get("GOOGLE_REDIRECT_URI", "https://api.vipciuchy.pl/api/auth/google/callback").strip(),
    )


@google_auth_bp.get("/login")
def google_login():
    client_id, client_secret, redirect_uri = _cfg()
    logging.info(f"[google] login — client_id={client_id[:20]}... redirect_uri={redirect_uri}")
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    params = {
        "client_id":     client_id,
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
        "access_type":   "online",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return redirect(url)


@google_auth_bp.get("/callback")
def google_callback():
    client_id, client_secret, redirect_uri = _cfg()
    code  = request.args.get("code")
    state = request.args.get("state")
    g_error = request.args.get("error", "")
    g_desc  = request.args.get("error_description", "")

    logging.error(f"[google] callback — code={'yes' if code else 'no'} error={g_error!r} desc={g_desc!r}")

    if not code:
        return redirect(f"{FRONTEND_URL}?error=google_auth_failed&g={g_error}")

    # Wymień code na token
    token_resp = _requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code":          code,
            "client_id":     client_id,
            "client_secret": client_secret,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
        },
        timeout=15,
    )
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    logging.error(f"[google] token response keys={list(token_data.keys())} error={token_data.get('error')}")

    if not access_token:
        return redirect(f"{FRONTEND_URL}?error=google_auth_failed&g=no_token")

    # Pobierz dane użytkownika
    userinfo_resp = _requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    userinfo = userinfo_resp.json()

    google_email = (userinfo.get("email") or "").lower().strip()
    google_name  = (userinfo.get("name")  or "").strip()

    if not google_email:
        return redirect(f"{FRONTEND_URL}?error=google_no_email")

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email=?", (google_email,)
        ).fetchone()

        if not user:
            username = google_email.split("@")[0][:30]
            base = username
            i = 1
            while conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
                username = f"{base}{i}"
                i += 1
            avatar  = (google_name[0] if google_name else username[0]).upper()
            pw_hash = generate_password_hash(secrets.token_hex(32), method="pbkdf2:sha256")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, avatar, email_verified, phone_verified, is_active) VALUES (?,?,?,?,1,1,1)",
                (username, google_email, pw_hash, avatar)
            )
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE email=?", (google_email,)).fetchone()

        if user["is_banned"] if "is_banned" in user.keys() else False:
            return redirect(f"{FRONTEND_URL}?error=account_banned")

        session.permanent = True
        session["user_id"] = user["id"]
        return redirect(f"{FRONTEND_URL}?google_login=ok")

    finally:
        conn.close()
