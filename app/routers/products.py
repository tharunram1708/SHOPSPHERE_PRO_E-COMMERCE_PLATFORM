from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import log, require_roles
from ..models import Product, User
from ..schemas import ProductIn, ProductPatch, ProductOut, StockIn
router = APIRouter()


@router.get("/products", response_model=list[ProductOut])
def products(search: Optional[str] = None, low_stock: bool = False, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    stmt = select(Product).where(Product.active.is_(True))
    if search: stmt = stmt.where((Product.name.ilike(f"%{search}%")) | Product.sku.ilike(f"%{search}%"))
    if low_stock: stmt = stmt.where(Product.stock <= 5)
    rows = db.scalars(stmt.order_by(Product.id).offset(skip).limit(limit)).all()
    return [{"id": p.id, "sku": p.sku, "name": p.name, "description": p.description, "price": p.price, "stock": p.stock} for p in rows]

@router.post("/products", status_code=201, response_model=ProductOut)
def add_product(data: ProductIn, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "ops"))):
    if db.scalar(select(Product).where(Product.sku == data.sku)):
        raise HTTPException(409, "SKU already exists")
    p = Product(**data.model_dump()); db.add(p); db.flush(); log(db, actor, "product.created", "product", p.id); db.commit(); db.refresh(p)
    return {"id": p.id, **data.model_dump()}

@router.patch("/products/{product_id}", response_model=ProductOut)
def edit_product(product_id: int, data: ProductPatch, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "ops"))):
    p = db.get(Product, product_id)
    if not p: raise HTTPException(404, "Product not found")
    for key, value in data.model_dump(exclude_unset=True).items(): setattr(p, key, value)
    log(db, actor, "product.updated", "product", p.id); db.commit(); db.refresh(p)
    return {"id": p.id, "sku": p.sku, "name": p.name, "description": p.description, "price": p.price, "stock": p.stock, "active": p.active}

@router.post("/products/{product_id}/stock-adjustments")
def adjust_stock(product_id: int, data: StockIn, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "ops"))):
    p = db.get(Product, product_id)
    if not p: raise HTTPException(404, "Product not found")
    if p.stock + data.adjustment < 0: raise HTTPException(409, "Stock cannot become negative")
    p.stock += data.adjustment
    log(db, actor, "stock.adjusted", "product", p.id, f"{data.adjustment}: {data.reason}"); db.commit()
    return {"product_id": p.id, "stock": p.stock}

