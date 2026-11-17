from datetime import datetime
from typing import Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import bearer, current_user, effective_permissions, log, require_roles
from ..models import AuthToken, User
from ..schemas import EmployeeCreateIn, RegisterIn, LoginIn, LogoutIn, RefreshIn, UserOut, TokenOut
from ..security import ACCESS_TOKEN_SECONDS, REFRESH_TOKEN_SECONDS, decode_token, make_managed_token, password_hash, verify_password
router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "service": "shopsphere-pro"}

@router.post("/auth/register", status_code=201, response_model=UserOut)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = str(data.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = User(email=email, name=data.name, password_hash=password_hash(data.password), role="customer")
    db.add(user); db.flush(); log(db, None, "user.registered", "user", user.id); db.commit(); db.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role,
            "status": user.status, "permissions": effective_permissions(user), "created_at": user.created_at}

@router.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if not user or user.status != "active" or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    log(db, user, "user.login", "user", user.id)
    return issue_tokens(db, user)

@router.post("/auth/customer/login", response_model=TokenOut)
def customer_login(data: LoginIn, db: Session = Depends(get_db)):
    return login_for_role(data, db, ("customer",))

@router.post("/auth/employee/login", response_model=TokenOut)
def employee_login(data: LoginIn, db: Session = Depends(get_db)):
    return login_for_role(data, db, ("ops", "support", "admin"))

def login_for_role(data: LoginIn, db: Session, roles: tuple[str, ...]):
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if not user or user.status != "active" or not verify_password(data.password, user.password_hash) or user.role not in roles:
        raise HTTPException(401, "Incorrect email or password")
    log(db, user, "user.login", "user", user.id)
    return issue_tokens(db, user)

def issue_tokens(db: Session, user: User, session_id: Optional[str] = None):
    session_id = session_id or str(uuid.uuid4())
    access, access_jti, access_exp = make_managed_token(user, "access", ACCESS_TOKEN_SECONDS, session_id)
    refresh, refresh_jti, refresh_exp = make_managed_token(user, "refresh", REFRESH_TOKEN_SECONDS, session_id)
    db.add_all([
        AuthToken(jti=access_jti, session_id=session_id, user_id=user.id, token_type="access", expires_at=access_exp),
        AuthToken(jti=refresh_jti, session_id=session_id, user_id=user.id, token_type="refresh", expires_at=refresh_exp),
    ])
    db.commit()
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_SECONDS, "refresh_expires_in": REFRESH_TOKEN_SECONDS, "role": user.role}

@router.post("/auth/refresh", response_model=TokenOut)
def refresh(data: RefreshIn, db: Session = Depends(get_db)):
    claims = decode_token(data.refresh_token, expected_type="refresh")
    if not claims["jti"]:
        raise HTTPException(401, "Invalid refresh token")
    stored = db.scalar(select(AuthToken).where(AuthToken.jti == claims["jti"]))
    if not stored or stored.token_type != "refresh" or stored.revoked_at is not None or stored.expires_at <= datetime.utcnow():
        raise HTTPException(401, "Invalid or revoked refresh token")
    user = db.get(User, claims["user_id"])
    if not user or user.status != "active" or user.id != stored.user_id:
        raise HTTPException(401, "Invalid refresh token")
    now = datetime.utcnow()
    rotated = db.execute(update(AuthToken).where(
        AuthToken.id == stored.id,
        AuthToken.revoked_at.is_(None),
        AuthToken.expires_at > now,
    ).values(revoked_at=now))
    if rotated.rowcount != 1:
        db.rollback()
        raise HTTPException(401, "Refresh token has already been used")
    db.commit()
    log(db, user, "user.token_refreshed", "user", user.id)
    result = issue_tokens(db, user, stored.session_id)
    return result

@router.post("/auth/logout", status_code=204)
def logout(data: Optional[LogoutIn] = None, credentials: HTTPAuthorizationCredentials = Depends(bearer),
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    access_claims = decode_token(credentials.credentials, expected_type="access")
    access = db.scalar(select(AuthToken).where(AuthToken.jti == access_claims["jti"])) if access_claims["jti"] else None
    if access and access.user_id == user.id and access.revoked_at is None:
        db.execute(update(AuthToken).where(
            AuthToken.session_id == access.session_id,
            AuthToken.user_id == user.id,
            AuthToken.revoked_at.is_(None),
        ).values(revoked_at=now))
    if data and data.refresh_token:
        refresh_claims = decode_token(data.refresh_token, expected_type="refresh")
        if refresh_claims["jti"]:
            refresh = db.scalar(select(AuthToken).where(AuthToken.jti == refresh_claims["jti"]))
            if refresh and access and refresh.user_id == user.id and refresh.session_id == access.session_id and refresh.token_type == "refresh" and refresh.revoked_at is None:
                refresh.revoked_at = now
    log(db, user, "user.logout", "user", user.id)
    db.commit()

@router.post("/auth/employees", status_code=201, response_model=UserOut)
def create_employee(data: EmployeeCreateIn, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    email = str(data.email).lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    employee = User(email=email, name=data.name, password_hash=password_hash(data.password), role=data.role)
    db.add(employee)
    db.flush()
    log(db, actor, "user.created", "user", employee.id, data.role)
    db.commit()
    db.refresh(employee)
    return {"id": employee.id, "email": employee.email, "name": employee.name, "role": employee.role,
            "status": employee.status, "permissions": effective_permissions(employee), "created_at": employee.created_at}

@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role,
            "status": user.status, "permissions": effective_permissions(user), "created_at": user.created_at}

