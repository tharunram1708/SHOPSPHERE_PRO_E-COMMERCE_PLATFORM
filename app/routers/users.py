import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import effective_permissions, log, require_roles
from ..models import AuthToken, AuditLog, User
from ..schemas import UserActivityOut, UserCreateIn, UserOut, UserUpdateIn
from ..security import password_hash

router = APIRouter()
VALID_PERMISSIONS = {
    "products:write", "stock:adjust", "promotions:write", "orders:manage",
    "tickets:manage", "reports:read", "audit:read",
}

def user_response(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role,
            "status": user.status, "permissions": effective_permissions(user), "created_at": user.created_at}

@router.get("/users", response_model=list[UserOut])
def list_users(q: str | None = None, role: str | None = None, status: str | None = None,
               skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
               db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    stmt = select(User).order_by(User.id)
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(User.email.ilike(needle) | User.name.ilike(needle))
    if role:
        stmt = stmt.where(User.role == role)
    if status:
        stmt = stmt.where(User.status == status)
    return [user_response(user) for user in db.scalars(stmt.offset(skip).limit(limit)).all()]

@router.post("/users", status_code=201, response_model=UserOut)
def create_user(data: UserCreateIn, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    email = str(data.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    unknown = sorted(set(data.permissions) - VALID_PERMISSIONS)
    if unknown:
        raise HTTPException(422, f"Unknown permissions: {', '.join(unknown)}")
    if data.role in ("ops", "support", "admin") and len(data.password) < 12:
        raise HTTPException(422, "Employee passwords must contain at least 12 characters")
    user = User(email=email, name=data.name, password_hash=password_hash(data.password), role=data.role,
                permissions_json=json.dumps(sorted(set(data.permissions))))
    db.add(user)
    db.flush()
    log(db, actor, "user.created", "user", user.id, data.role)
    db.commit()
    db.refresh(user)
    return user_response(user)

@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user_response(user)

@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdateIn, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if changes.get("status", "active") != "active" and user.id == actor.id:
        raise HTTPException(409, "You cannot deactivate your own account")
    if "email" in changes and changes["email"] is not None:
        email = str(changes["email"]).lower()
        duplicate = db.scalar(select(User).where(User.email == email, User.id != user.id))
        if duplicate:
            raise HTTPException(409, "Email already registered")
        changes["email"] = email
    if "permissions" in changes:
        permissions = changes["permissions"] or []
        unknown = sorted(set(permissions) - VALID_PERMISSIONS)
        if unknown:
            raise HTTPException(422, f"Unknown permissions: {', '.join(unknown)}")
        changes["permissions_json"] = json.dumps(sorted(set(permissions)))
        del changes["permissions"]
    for key, value in changes.items():
        setattr(user, key, value)
    if user.status != "active":
        db.execute(update(AuthToken).where(AuthToken.user_id == user.id, AuthToken.revoked_at.is_(None))
                   .values(revoked_at=datetime.utcnow()))
    log(db, actor, "user.updated", "user", user.id, ",".join(sorted(changes)))
    db.commit()
    db.refresh(user)
    return user_response(user)

@router.post("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(user_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    return set_user_status(user_id, "inactive", db, actor)

@router.post("/users/{user_id}/activate", response_model=UserOut)
def activate_user(user_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    return set_user_status(user_id, "active", db, actor)

def set_user_status(user_id: int, status: str, db: Session, actor: User):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == actor.id and status != "active":
        raise HTTPException(409, "You cannot deactivate your own account")
    user.status = status
    if status != "active":
        db.execute(update(AuthToken).where(AuthToken.user_id == user.id, AuthToken.revoked_at.is_(None))
                   .values(revoked_at=datetime.utcnow()))
    log(db, actor, f"user.{status}", "user", user.id)
    db.commit()
    db.refresh(user)
    return user_response(user)

@router.get("/users/{user_id}/activity", response_model=list[UserActivityOut])
def user_activity(user_id: int, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                  db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    if not db.get(User, user_id):
        raise HTTPException(404, "User not found")
    rows = db.scalars(select(AuditLog).where(or_(AuditLog.actor_id == user_id,
                                                  (AuditLog.entity_type == "user") & (AuditLog.entity_id == user_id)))
                      .order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)).all()
    return [{"id": row.id, "actor_id": row.actor_id, "action": row.action,
             "entity_type": row.entity_type, "entity_id": row.entity_id,
             "details": row.details or "", "created_at": row.created_at} for row in rows]
