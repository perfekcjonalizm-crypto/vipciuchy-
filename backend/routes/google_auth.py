"""
routes/google_auth.py — logowanie przez Google OAuth 2.0
"""
import os
import secrets
from flask import Blueprint, request, jsonify, session, redirect
from authlib.integrations.requests_client import OAuth2Session
from db import get_db
from werkzeug.security import generate_password_hash

google_auth_bp = Blueprint("google_auth", __name__, url_prefix="/api/auth/google")

GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "https://vipciuchy-production.up.railway.app/api/auth/google/callback"
)

AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL         = "https://oauth2.googleapis.com/token"
USERINFO_URL      = "https://www.googleapis.com/oauth2/v3/userinfo"

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://vipciuchy.pl")


@google_auth_bp.get("/login")
def google_login():
    oauth = OAuth2Session(
        GOOGLE_CLIENT_ID,
        redirect_uri=GOOGLE_REDIRECT_URI,
        scope=["openid", "email", "profile"],
    )
    uri, state = oauth.create_authorization_url(AUTHORIZATION_URL)
    session["oauth_state"] = state
    return redirect(uri)


@google_auth_bp.get("/callback")
def google_callback():
    code  = request.args.get("code")
    state = request.args.get("state")

    if not code:
        return redirect(f"{FRONTEND_URL}?error=google_auth_failed")

    oauth = OAuth2Session(
        GOOGLE_CLIENT_ID,
        redirect_uri=GOOGLE_REDIRECT_URI,
        state=state,
    )
    try:
        token = oauth.fetch_token(
            TOKEN_URL,
            code=code,
            client_secret=GOOGLE_CLIENT_SECRET,
        )
        resp     = oauth.get(USERINFO_URL)
        userinfo = resp.json()
    except Exception:
        return redirect(f"{FRONTEND_URL}?error=google_auth_failed")

    google_email = (userinfo.get("email") or "").lower().strip()
    google_name  = (userinfo.get("name")  or "").strip()
    google_sub   = userinfo.get("sub", "")

    if not google_email:
        return redirect(f"{FRONTEND_URL}?error=google_no_email")

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email=?", (google_email,)
        ).fetchone()

        if not user:
            # Utwórz nowe konto
            username = google_email.split("@")[0][:30]
            # Upewnij się że username jest unikalny
            base = username
            i = 1
            while conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
                username = f"{base}{i}"
                i += 1

            avatar = (google_name[0] if google_name else username[0]).upper()
            pw_hash = generate_password_hash(secrets.token_hex(32), method="pbkdf2:sha256")
            conn.execute(
                "INSERT INTO users (username, email, password_hash, avatar, email_verified, phone_verified, is_active) VALUES (?,?,?,?,1,1,1)",
                (username, google_email, pw_hash, avatar)
            )
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE email=?", (google_email,)).fetchone()

        # Sprawdź czy konto nie jest zablokowane
        if user["is_banned"] if "is_banned" in user.keys() else False:
            return redirect(f"{FRONTEND_URL}?error=account_banned")

        session.permanent = True
        session["user_id"] = user["id"]
        return redirect(f"{FRONTEND_URL}?google_login=ok")

    finally:
        conn.close()
