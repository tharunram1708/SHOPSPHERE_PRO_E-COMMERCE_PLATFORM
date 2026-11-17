from datetime import datetime
from typing import Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import get_db
from .models import AuditLog, AuthToken, User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)

ROLE_PERMISSIONS = {
    "customer": [],
    "ops": ["products:write", "stock:adjust", "promotions:write", "orders:manage", "reports:read"],
    "support": ["tickets:manage"],
    "admin": ["*"],
}

def effective_permissions(user: User) -> list[str]:
    role_permissions = ROLE_PERMISSIONS.get(user.role, [])
    if "*" in role_permissions:
        return ["*"]
    return sorted(set(role_permissions) | set(user.permissions))

def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_token(creds.credentials, expected_type="access")
    if claims["jti"]:
        token = db.scalar(select(AuthToken).where(AuthToken.jti == claims["jti"]))
        if not token or token.token_type != "access" or token.revoked_at is not None or token.expires_at <= datetime.utcnow():
            raise HTTPException(401, "Invalid or revoked access token", headers={"WWW-Authenticate": "Bearer"})
    user = db.get(User, claims["user_id"])
    if not user or user.status != "active":
        raise HTTPException(401, "Invalid user")
    return user

def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Insufficient permissions")
        return user
    return dependency

def require_permissions(*permissions: str):
    def dependency(user: User = Depends(current_user)) -> User:
        granted = effective_permissions(user)
        if "*" not in granted and not set(permissions).issubset(granted):
            raise HTTPException(403, "Insufficient permissions")
        return user
    return dependency

def log(db: Session, actor: Optional[User], action: str, entity: str, entity_id: Optional[int], details: str = "") -> None:
    db.add(AuditLog(actor_id=actor.id if actor else None, action=action, entity_type=entity, entity_id=entity_id, details=details))
