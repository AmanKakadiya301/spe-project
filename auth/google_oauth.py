"""
auth/google_oauth.py
CREATE at auth/google_oauth.py
Google OAuth 2.0 Blueprint.

Setup:
  1. console.cloud.google.com → APIs → Credentials → OAuth 2.0 Client
  2. Authorised redirect URI: http://localhost:5000/auth/google/callback
  3. Add to .env: GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=...

Register in main.py:
    from auth.google_oauth import google_auth
    app.register_blueprint(google_auth)
"""
import os
import json
import base64
import logging
from datetime import datetime

import requests
from flask import Blueprint, redirect, request, url_for, jsonify
from flask_login import login_user, current_user

logger = logging.getLogger(__name__)

google_auth = Blueprint("google_auth", __name__, url_prefix="/auth")

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
DISCOVERY_URL        = "https://accounts.google.com/.well-known/openid-configuration"
_discovery: dict     = {}


def _cfg():
    if not _discovery:
        r = requests.get(DISCOVERY_URL, timeout=5)
        r.raise_for_status()
        _discovery.update(r.json())
    return _discovery


@google_auth.route("/google")
def google_login():
    if not GOOGLE_CLIENT_ID:
        return jsonify({"error": "Google OAuth not configured"}), 503
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    import urllib.parse
    cfg      = _cfg()
    redirect_uri = url_for("google_auth.google_callback", _external=True)
    params   = {
        "client_id": GOOGLE_CLIENT_ID, "redirect_uri": redirect_uri,
        "response_type": "code", "scope": "openid email profile",
        "access_type": "offline", "prompt": "select_account",
    }
    return redirect(cfg["authorization_endpoint"] + "?" + urllib.parse.urlencode(params))


@google_auth.route("/google/callback")
def google_callback():
    from models import db, User, AuditLog

    code  = request.args.get("code")
    error = request.args.get("error")
    if error or not code:
        return redirect(url_for("login_page") + "?error=google_cancelled")

    cfg          = _cfg()
    redirect_uri = url_for("google_auth.google_callback", _external=True)

    try:
        tok = requests.post(cfg["token_endpoint"], data={
            "code": code, "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code",
        }, timeout=10)
        tok.raise_for_status()
        tokens = tok.json()
    except Exception as exc:
        logger.error(f"Google token exchange failed: {exc}")
        return redirect(url_for("login_page") + "?error=google_failed")

    # Decode id_token payload (base64 JWT middle segment)
    id_token = tokens.get("id_token", "")
    try:
        payload_b64 = id_token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        userinfo = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        r2 = requests.get(cfg["userinfo_endpoint"],
                          headers={"Authorization": f"Bearer {tokens.get('access_token')}"}, timeout=5)
        userinfo = r2.json()

    google_id  = userinfo.get("sub")
    email      = userinfo.get("email", "")
    name       = userinfo.get("name", email.split("@")[0] if email else "user")
    avatar_url = userinfo.get("picture", "")

    if not google_id:
        return redirect(url_for("login_page") + "?error=google_no_id")

    user = User.query.filter_by(google_id=google_id).first()
    if not user and email:
        user = User.query.filter_by(email=email).first()
    if not user:
        user = User(username=name, email=email, google_id=google_id,
                    avatar_url=avatar_url, role="user")
        db.session.add(user)
        logger.info(f"New user via Google: {email}")
    else:
        user.google_id = google_id
        user.avatar_url = avatar_url
        if not user.email:
            user.email = email

    user.last_login = datetime.utcnow()
    AuditLog.log("google_login", user=user, ip=request.remote_addr, meta={"email": email})
    db.session.commit()
    login_user(user)
    return redirect(url_for("index"))


@google_auth.route("/status")
def oauth_status():
    return jsonify({"google_oauth_enabled": bool(GOOGLE_CLIENT_ID)})
