from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import current_user
from ..models import User
from ..schemas import RegisterIn, LoginIn, UserOut, TokenOut
from ..security import make_token, password_hash, verify_password
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
    db.add(user); db.commit(); db.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}

@router.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return {"access_token": make_token(user), "token_type": "bearer", "expires_in": 43200, "role": user.role}

@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}

