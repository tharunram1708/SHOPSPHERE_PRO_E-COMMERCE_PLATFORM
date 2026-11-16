"""ShopSphere Pro API application entry point."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import select
from .database import SessionLocal
from .dependencies import current_user
from .models import User
from .security import password_hash
from .database import Base
from .routers import auth, orders, products, promotions, reports, tickets

@asynccontextmanager
async def lifespan(_: FastAPI):
    email = os.getenv("SHOPSPHERE_ADMIN_EMAIL")
    password = os.getenv("SHOPSPHERE_ADMIN_PASSWORD")
    if email and password:
        db = SessionLocal()
        try:
            if not db.scalar(select(User).where(User.email == email.lower())):
                db.add(User(email=email.lower(), name="ShopSphere Admin", password_hash=password_hash(password), role="admin"))
                db.commit()
        finally:
            db.close()
    yield

app = FastAPI(title="ShopSphere Pro API", version="2.0.0", description="Operational, commercial, customer service and reporting APIs", lifespan=lifespan)
for route_group in (auth.router, products.router, promotions.router, orders.router, tickets.router, reports.router):
    app.include_router(route_group)
