import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import HTTPException
from .config import SECRET_KEY
from .models import User

ACCESS_TOKEN_SECONDS = 15 * 60
REFRESH_TOKEN_SECONDS = 7 * 24 * 60 * 60

def password_hash(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    return base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_s, digest_s = stored.split("$")
        expected = base64.urlsafe_b64decode(digest_s)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.urlsafe_b64decode(salt_s), 240_000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

def make_token(user: User) -> str:
    # Retained for callers that need a short-lived, stateless test/service token.
    return jwt.encode({"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(hours=12)}, SECRET_KEY, algorithm="HS256")

def make_managed_token(user: User, token_type: str, lifetime_seconds: int, session_id: str) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=lifetime_seconds)
    jti = str(uuid.uuid4())
    token = jwt.encode({"sub": str(user.id), "jti": jti, "sid": session_id, "type": token_type,
                        "iat": now, "exp": expires}, SECRET_KEY, algorithm="HS256")
    return token, jti, expires.replace(tzinfo=None)

def decode_token(token: str, expected_type: Optional[str] = None) -> dict:
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = int(data["sub"])
        if expected_type and data.get("jti") and data.get("type") != expected_type:
            raise jwt.InvalidTokenError("Wrong token type")
        return {"user_id": user_id, "jti": data.get("jti"), "sid": data.get("sid"), "type": data.get("type")}
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
