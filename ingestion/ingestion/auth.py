import base64
import hashlib
import hmac
import os
import time

# Session cookies are HMAC-signed with SESSION_SECRET, kept deliberately
# separate from API_KEY (which authenticates REST callers). This means a
# leaked API_KEY does not let an attacker forge session cookies, and rotating
# one secret does not invalidate the other. Note: there is still no
# revocation list — a leaked cookie is valid for COOKIE_MAX_AGE.

COOKIE_NAME = "mindstore_session"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 days


def _get_secret() -> bytes:
    return os.environ["SESSION_SECRET"].encode()


def create_cookie_value(username: str) -> str:
    expiry = int(time.time()) + COOKIE_MAX_AGE
    payload = f"{username}:{expiry}"
    sig = hmac.new(_get_secret(), payload.encode(), hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(payload.encode()).decode()
    return f"{encoded}.{sig}"


def verify_cookie(cookie_value: str) -> str | None:
    """Returns username if valid, None otherwise."""
    try:
        encoded, sig = cookie_value.rsplit(".", 1)
        payload = base64.urlsafe_b64decode(encoded).decode()
        expected_sig = hmac.new(_get_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        username, expiry_str = payload.rsplit(":", 1)
        if int(expiry_str) < time.time():
            return None
        return username
    except Exception:
        return None
