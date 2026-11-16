from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import current_user, log, require_roles
from ..models import Order, Ticket, User
from ..schemas import TicketIn, TicketOut, TicketUpdate
from ..services import ticket_json
router = APIRouter()


@router.post("/tickets", status_code=201, response_model=TicketOut)
def create_ticket(data: TicketIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    if data.priority not in ("low", "normal", "high", "urgent"): raise HTTPException(422, "Invalid priority")
    if data.order_id:
        order = db.get(Order, data.order_id)
        if not order or (actor.role == "customer" and order.customer_id != actor.id): raise HTTPException(404, "Order not found")
    ticket = Ticket(customer_id=actor.id, **data.model_dump()); db.add(ticket); db.flush(); log(db, actor, "ticket.created", "ticket", ticket.id); db.commit(); db.refresh(ticket)
    return ticket_json(ticket)

@router.get("/tickets", response_model=list[TicketOut])
def tickets(status_filter: Optional[str] = Query(None, alias="status"), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), actor: User = Depends(current_user)):
    stmt = select(Ticket).order_by(Ticket.created_at.desc())
    if actor.role == "customer": stmt = stmt.where(Ticket.customer_id == actor.id)
    if status_filter: stmt = stmt.where(Ticket.status == status_filter)
    return [ticket_json(t) for t in db.scalars(stmt.offset(skip).limit(limit)).all()]

@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: int, data: TicketUpdate, db: Session = Depends(get_db), actor: User = Depends(require_roles("admin", "support"))):
    t = db.get(Ticket, ticket_id)
    if not t: raise HTTPException(404, "Ticket not found")
    changes = data.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] not in ("open", "in_progress", "resolved", "closed"): raise HTTPException(422, "Invalid ticket status")
    if "priority" in changes and changes["priority"] not in ("low", "normal", "high", "urgent"): raise HTTPException(422, "Invalid priority")
    if changes.get("assigned_to") is not None:
        assigned = db.get(User, changes["assigned_to"])
        if not assigned or assigned.role not in ("admin", "support"): raise HTTPException(422, "Assignee must be a support user")
    for key, value in changes.items(): setattr(t, key, value)
    log(db, actor, "ticket.updated", "ticket", t.id); db.commit(); db.refresh(t)
    return ticket_json(t)

