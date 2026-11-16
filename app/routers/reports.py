from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import require_roles
from ..models import AuditLog, Order, Product, Ticket, User, now
from ..schemas import SalesReportOut, SummaryReportOut
router = APIRouter()


@router.get("/reports/summary", response_model=SummaryReportOut)
def report_summary(db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "ops"))):
    gross = db.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(Order.status != "cancelled"))
    orders = db.scalar(select(func.count(Order.id)).where(Order.status != "cancelled"))
    low_stock = db.scalar(select(func.count(Product.id)).where(Product.active.is_(True), Product.stock <= 5))
    tickets_open = db.scalar(select(func.count(Ticket.id)).where(Ticket.status.in_(["open", "in_progress"])))
    return {"revenue": round(float(gross), 2), "orders": orders, "average_order_value": round(float(gross) / orders, 2) if orders else 0, "low_stock_products": low_stock, "open_tickets": tickets_open}

@router.get("/reports/sales", response_model=SalesReportOut)
def report_sales(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "ops"))):
    since = now().replace(hour=0, minute=0, second=0, microsecond=0)
    since -= timedelta(days=days - 1)
    rows = db.execute(select(func.date(Order.created_at), func.count(Order.id), func.coalesce(func.sum(Order.total), 0)).where(Order.status != "cancelled", Order.created_at >= since).group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at))).all()
    return {"days": days, "series": [{"date": str(d), "orders": n, "revenue": round(float(revenue), 2)} for d, n, revenue in rows]}

@router.get("/reports/inventory")
def report_inventory(db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "ops"))):
    rows = db.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.stock, Product.name)).all()
    return {"low_stock_threshold": 5, "products": [{"id": p.id, "sku": p.sku, "name": p.name, "stock": p.stock, "unit_price": p.price, "inventory_value": round(p.stock * p.price, 2)} for p in rows]}

@router.get("/audit-logs")
def audit_logs(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), actor: User = Depends(require_roles("admin"))):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)).all()
    return [{"id": x.id, "actor_id": x.actor_id, "action": x.action, "entity_type": x.entity_type, "entity_id": x.entity_id, "details": x.details, "created_at": x.created_at} for x in rows]

