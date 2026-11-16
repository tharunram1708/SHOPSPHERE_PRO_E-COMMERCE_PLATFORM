"""Compatibility entry point. Run with: uvicorn app.main:app --reload"""
from app.main import app
from app.database import Base, SessionLocal
from app.models import User
from app.security import make_token, password_hash
