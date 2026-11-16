"""Transactional helpers for order lifecycle and fulfillment operations."""
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from .dependencies import log
from .models import Order, OrderActivity, OrderLine, OrderStatusHistory, Product, Shipment, ShipmentLine, User, now

ORDER_TRANSITIONS = {
    "placed": {"processing", "backordered", "cancelled"},
    "processing": {"backordered", "partially_fulfilled", "fulfilled", "shipped", "cancelled"},
    "backordered": {"processing", "partially_fulfilled", "fulfilled", "cancelled"},
    "partially_fulfilled": {"fulfilled"},
    "fulfilled": {"shipped", "delivered"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


def record_status(db: Session, order: Order, actor: User, new_status: str, reason: str) -> None:
    previous = order.status
    order.status = new_status
    order.updated_at = now()
    db.add(OrderStatusHistory(order_id=order.id, actor_id=actor.id, from_status=previous,
                              to_status=new_status, reason=reason))
    log(db, actor, "order.status_changed", "order", order.id, f"{previous} -> {new_status}: {reason}")


def validate_transition(order: Order, new_status: str) -> None:
    if new_status not in ORDER_TRANSITIONS.get(order.status, set()):
        raise HTTPException(409, f"Cannot transition order from {order.status} to {new_status}")


def record_activity(db: Session, order: Order, actor: User, event_type: str, reason: str,
                    order_line_id: int | None = None, quantity: int | None = None) -> None:
    db.add(OrderActivity(order_id=order.id, order_line_id=order_line_id, actor_id=actor.id,
                         event_type=event_type, quantity=quantity, reason=reason))


def cancel_line_quantity(db: Session, order: Order, line: OrderLine, quantity: int,
                         reason: str, actor: User) -> None:
    if quantity <= 0:
        raise HTTPException(422, "Cancellation quantity must be positive")
    remaining = line.quantity - line.shipped_quantity - line.cancelled_quantity
    if quantity > remaining:
        raise HTTPException(409, f"Only {remaining} units remain eligible for cancellation")

    # Return reserved stock first, then remove the demand from backorder or unallocated units.
    allocated_remaining = max(0, line.allocated_quantity - line.shipped_quantity)
    release = min(quantity, allocated_remaining)
    reduce_backorder = min(quantity - release, line.backordered_quantity)
    line.allocated_quantity -= release
    line.backordered_quantity -= reduce_backorder
    line.cancelled_quantity += quantity
    if release:
        db.execute(update(Product).where(Product.id == line.product_id).values(stock=Product.stock + release))

    previous_subtotal = order.subtotal
    gross = line.unit_price * quantity
    discount_share = min(order.discount, order.discount * gross / previous_subtotal) if previous_subtotal else 0
    order.subtotal = round(max(0, previous_subtotal - gross), 2)
    order.discount = round(max(0, order.discount - discount_share), 2)
    order.total = round(max(0, order.subtotal - order.discount), 2)
    record_activity(db, order, actor, "item_cancelled", reason, line.id, quantity)
    log(db, actor, "order.item_cancelled", "order_line", line.id,
        f"quantity={quantity}; reason={reason}")


def sync_fulfillment_status(db: Session, order: Order, actor: User, reason: str) -> None:
    if not order.lines:
        return
    requested = sum(line.quantity for line in order.lines)
    cancelled = sum(line.cancelled_quantity for line in order.lines)
    shipped = sum(line.shipped_quantity for line in order.lines)
    outstanding_backorders = sum(line.backordered_quantity for line in order.lines)
    remaining = requested - cancelled

    if remaining == 0:
        target = "cancelled"
    elif shipped >= remaining:
        target = "fulfilled"
    elif shipped:
        target = "partially_fulfilled"
    elif outstanding_backorders:
        target = "backordered"
    else:
        target = "processing"

    if target != order.status and target in ORDER_TRANSITIONS.get(order.status, set()):
        record_status(db, order, actor, target, reason)


def cancel_remaining_order(db: Session, order: Order, actor: User, reason: str) -> None:
    if any(line.shipped_quantity for line in order.lines):
        raise HTTPException(409, "An order with shipped items cannot be fully cancelled; cancel eligible items individually")
    for line in order.lines:
        remaining = line.quantity - line.cancelled_quantity
        if remaining:
            cancel_line_quantity(db, order, line, remaining, reason, actor)
    if order.status != "cancelled":
        validate_transition(order, "cancelled")
        record_status(db, order, actor, "cancelled", reason)


def shipment_json(shipment: Shipment) -> dict:
    return {
        "id": shipment.id,
        "order_id": shipment.order_id,
        "status": shipment.status,
        "carrier": shipment.carrier,
        "tracking_number": shipment.tracking_number,
        "actor_id": shipment.actor_id,
        "reason": shipment.reason,
        "created_at": shipment.created_at,
        "shipped_at": shipment.shipped_at,
        "delivered_at": shipment.delivered_at,
        "delivered_by": shipment.delivered_by,
        "delivery_reason": shipment.delivery_reason,
        "items": [{"order_line_id": row.order_line_id, "sku": row.order_line.sku,
                   "name": row.order_line.name, "quantity": row.quantity} for row in shipment.lines],
    }
