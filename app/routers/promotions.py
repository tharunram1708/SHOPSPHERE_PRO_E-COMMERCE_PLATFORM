from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import current_user, log, require_roles
from ..models import Promotion, User
from ..schemas import PromotionIn, PromotionOut
from ..models import now
router = APIRouter()


@router.post("/promotions", status_code=201, response_model=PromotionOut)
def create_promotion(data: PromotionIn, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "ops"))):
    code = data.code.strip().upper()
    if data.kind not in ("percent", "fixed"): raise HTTPException(422, "kind must be percent or fixed")
    if data.kind == "percent" and data.value > 100: raise HTTPException(422, "Percentage cannot exceed 100")
    if data.starts_at and data.ends_at and data.ends_at <= data.starts_at: raise HTTPException(422, "ends_at must be after starts_at")
    if db.scalar(select(Promotion).where(Promotion.code == code)): raise HTTPException(409, "Promotion code already exists")
    promo = Promotion(**{**data.model_dump(), "code": code}); db.add(promo); db.flush(); log(db, actor, "promotion.created", "promotion", promo.id); db.commit(); db.refresh(promo)
    return {"id": promo.id, "code": promo.code, "kind": promo.kind, "value": promo.value, "active": promo.active}

@router.get("/promotions/{code}/validate")
def validate_promotion(code: str, subtotal: float = Query(gt=0), db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.scalar(select(Promotion).where(Promotion.code == code.upper()))
    if not p or not p.active: raise HTTPException(404, "Promotion is unavailable")
    moment = now()
    if p.starts_at and p.starts_at > moment or p.ends_at and p.ends_at <= moment: raise HTTPException(409, "Promotion is outside its validity window")
    if p.max_uses is not None and p.uses >= p.max_uses: raise HTTPException(409, "Promotion usage limit reached")
    if subtotal < p.minimum_order: raise HTTPException(409, "Minimum order amount not met")
    discount = min(subtotal, subtotal * p.value / 100 if p.kind == "percent" else p.value)
    return {"code": p.code, "discount": round(discount, 2), "total": round(subtotal - discount, 2)}

