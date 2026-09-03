"""Local authentication and Google OpenID Connect provider helpers."""
from __future__ import annotations

import hmac
import secrets
from urllib.parse import urlencode

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from fastdps.config import settings


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def google_enabled() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri)


def google_authorize_url(session: dict) -> str:
    if not google_enabled():
        raise RuntimeError("Google sign-in is not configured")
    state = secrets.token_urlsafe(32)
    session["google_oauth_state"] = state
    return f"{GOOGLE_AUTH_URL}?{urlencode({'client_id': settings.google_client_id, 'redirect_uri': settings.google_redirect_uri, 'response_type': 'code', 'scope': 'openid email profile', 'state': state, 'prompt': 'select_account'})}"


def google_exchange(code: str, state: str, session: dict) -> dict:
    expected = session.pop("google_oauth_state", "")
    if not expected or not state or not hmac.compare_digest(expected, state):
        raise ValueError("Google sign-in state was invalid")
    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri, "grant_type": "authorization_code",
        },
        timeout=20,
    )
    response.raise_for_status()
    claims = id_token.verify_oauth2_token(response.json()["id_token"], google_requests.Request(), settings.google_client_id)
    email = str(claims.get("email", "")).lower()
    if not email or not claims.get("email_verified"):
        raise PermissionError("Google did not return a verified email address")
    domain = email.rsplit("@", 1)[-1]
    if settings.google_allowed_emails and email not in settings.google_allowed_emails:
        raise PermissionError("This email address is not authorised")
    if settings.google_allowed_domains and domain not in settings.google_allowed_domains:
        raise PermissionError("This email domain is not authorised")
    return {"email": email, "name": claims.get("name") or email.split("@", 1)[0]}
