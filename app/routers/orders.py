from typing import Optional
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from ..database import get_db
from ..dependencies import current_user, log, require_permissions
from ..models import Order, OrderLine, OrderStatusHistory, Product, Promotion, Shipment, ShipmentLine, User, now
from ..schemas import (BackorderAllocationIn, CancelOrderLineIn, FulfillmentCreateIn,
                       FulfillmentOut, OrderIn, OrderOut, OrderTimelineOut,
                       ShipmentStatusIn, StatusIn)
from ..order_workflows import (cancel_line_quantity, cancel_remaining_order,
                               record_activity, record_status, shipment_json, sync_fulfillment_status,
                               validate_transition)
from ..services import order_json
router = APIRouter()


@router.post("/orders", status_code=201, response_model=OrderOut)
def place_order(data: OrderIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    quantities: dict[int, int] = {}
    for item in data.items: quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    products_by_id = {}
    for pid, qty in quantities.items():
        p = db.get(Product, pid)
        if not p or not p.active: raise HTTPException(404, f"Product {pid} is unavailable")
        if p.stock < qty and not data.allow_backorder: raise HTTPException(409, f"Insufficient stock for {p.sku}")
        products_by_id[pid] = p
    subtotal = sum(products_by_id[pid].price * qty for pid, qty in quantities.items())
    promo = None; discount = 0.0
    if data.promotion_code:
        promo = db.scalar(select(Promotion).where(Promotion.code == data.promotion_code.upper()))
        if not promo or not promo.active: raise HTTPException(409, "Promotion is unavailable")
        moment = now()
        if promo.starts_at and promo.starts_at > moment or promo.ends_at and promo.ends_at <= moment: raise HTTPException(409, "Promotion is outside its validity window")
        if promo.max_uses is not None and promo.uses >= promo.max_uses: raise HTTPException(409, "Promotion usage limit reached")
        if subtotal < promo.minimum_order: raise HTTPException(409, "Minimum order amount not met")
        discount = min(subtotal, subtotal * promo.value / 100 if promo.kind == "percent" else promo.value)
    # Conditional updates keep concurrent orders from overselling stock.
    allocated_by_product = {}
    for pid, qty in quantities.items():
        allocated = min(products_by_id[pid].stock, qty) if data.allow_backorder else qty
        allocated_by_product[pid] = allocated
        if allocated:
            result = db.execute(update(Product).where(Product.id == pid, Product.stock >= allocated).values(stock=Product.stock - allocated))
            if result.rowcount != 1:
                db.rollback(); raise HTTPException(409, f"Insufficient stock for {products_by_id[pid].sku}")
    order = Order(customer_id=actor.id, subtotal=round(subtotal, 2), discount=round(discount, 2), total=round(subtotal-discount, 2), promotion_code=promo.code if promo else None)
    for pid, qty in quantities.items():
        p = products_by_id[pid]
        allocated = allocated_by_product[pid]
        order.lines.append(OrderLine(product_id=pid, sku=p.sku, name=p.name, unit_price=p.price,
                                     quantity=qty, allocated_quantity=allocated,
                                     backordered_quantity=qty-allocated))
    if promo: promo.uses += 1
    db.add(order); db.flush()
    db.add(OrderStatusHistory(order_id=order.id, actor_id=actor.id, from_status=None,
                              to_status="placed", reason="Order placed"))
    log(db, actor, "order.placed", "order", order.id)
    if any(line.backordered_quantity for line in order.lines):
        record_status(db, order, actor, "backordered", "One or more items are awaiting inventory")
    db.commit(); db.refresh(order)
    return order_json(order)

@router.get("/orders", response_model=list[OrderOut])
def list_orders(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), actor: User = Depends(current_user)):
    stmt = select(Order).order_by(Order.created_at.desc()).offset(skip).limit(limit)
    if actor.role == "customer": stmt = select(Order).where(Order.customer_id == actor.id).order_by(Order.created_at.desc()).offset(skip).limit(limit)
    return [order_json(o) for o in db.scalars(stmt).all()]

@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    order = db.get(Order, order_id)
    if not order: raise HTTPException(404, "Order not found")
    if actor.role == "customer" and order.customer_id != actor.id: raise HTTPException(403, "You cannot view this order")
    return order_json(order)

@router.patch("/orders/{order_id}/status", response_model=OrderOut)
def change_order_status(order_id: int, data: StatusIn, db: Session = Depends(get_db), actor: User = Depends(require_permissions("orders:manage"))):
    order = db.get(Order, order_id)
    if not order: raise HTTPException(404, "Order not found")
    validate_transition(order, data.status)
    if data.status == "cancelled":
        cancel_remaining_order(db, order, actor, data.reason)
    elif data.status == "fulfilled" and any(line.shipped_quantity + line.cancelled_quantity < line.quantity for line in order.lines):
        raise HTTPException(409, "An order can be fulfilled only after every non-cancelled unit has shipped")
    elif data.status == "delivered" and order.status not in ("fulfilled", "shipped"):
        raise HTTPException(409, "Only a fulfilled or shipped order can be marked delivered")
    else:
        record_status(db, order, actor, data.status, data.reason)
    db.commit(); db.refresh(order)
    return order_json(order)


def get_order_for_actor(order_id: int, actor: User, db: Session) -> Order:
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if actor.role == "customer" and order.customer_id != actor.id:
        raise HTTPException(403, "You cannot view this order")
    return order


@router.get("/orders/{order_id}/timeline", response_model=OrderTimelineOut)
def order_timeline(order_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    order = get_order_for_actor(order_id, actor, db)
    events = []
    for item in order.status_history:
        events.append({"event_type": "status", "actor_id": item.actor_id, "timestamp": item.created_at,
                       "reason": item.reason, "from_status": item.from_status, "to_status": item.to_status})
    for activity in order.activities:
        events.append({"event_type": activity.event_type, "actor_id": activity.actor_id,
                       "timestamp": activity.created_at, "reason": activity.reason,
                       "order_line_id": activity.order_line_id, "quantity": activity.quantity})
    for shipment in order.shipments:
        events.append({"event_type": "shipment", "actor_id": shipment.actor_id, "timestamp": shipment.shipped_at,
                       "reason": shipment.reason, "shipment_id": shipment.id, "shipment_status": shipment.status})
        if shipment.delivered_at:
            events.append({"event_type": "shipment_delivered", "actor_id": shipment.delivered_by or shipment.actor_id,
                           "timestamp": shipment.delivered_at, "reason": shipment.delivery_reason or f"Shipment {shipment.id} delivered",
                           "shipment_id": shipment.id, "shipment_status": "delivered"})
    events.sort(key=lambda event: event["timestamp"])
    return {"order_id": order.id, "current_status": order.status, "events": events}


@router.get("/orders/{order_id}/fulfillments", response_model=list[FulfillmentOut])
def list_fulfillments(order_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    order = get_order_for_actor(order_id, actor, db)
    return [shipment_json(shipment) for shipment in order.shipments]


@router.post("/orders/{order_id}/fulfillments", status_code=201, response_model=FulfillmentOut)
def create_fulfillment(order_id: int, data: FulfillmentCreateIn, db: Session = Depends(get_db), actor: User = Depends(require_permissions("orders:manage"))):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status not in ("processing", "backordered", "partially_fulfilled"):
        raise HTTPException(409, f"Cannot ship an order in status {order.status}")
    requested = {}
    for item in data.items:
        requested[item.order_line_id] = requested.get(item.order_line_id, 0) + item.quantity
    lines = {line.id: line for line in order.lines}
    for line_id, quantity in requested.items():
        line = lines.get(line_id)
        if not line:
            raise HTTPException(404, f"Order line {line_id} does not belong to this order")
        ready = line.allocated_quantity - line.shipped_quantity
        if quantity > ready:
            raise HTTPException(409, f"Only {ready} allocated units are ready to ship for order line {line_id}")

    shipment = Shipment(order_id=order.id, status="shipped", carrier=data.carrier,
                        tracking_number=data.tracking_number, actor_id=actor.id,
                        reason=data.reason, shipped_at=now())
    db.add(shipment); db.flush()
    for line_id, quantity in requested.items():
        line = lines[line_id]
        result = db.execute(update(OrderLine).where(
            OrderLine.id == line_id,
            OrderLine.allocated_quantity - OrderLine.shipped_quantity >= quantity,
            OrderLine.quantity - OrderLine.shipped_quantity - OrderLine.cancelled_quantity >= quantity,
        ).values(shipped_quantity=OrderLine.shipped_quantity + quantity))
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(409, f"Order line {line_id} no longer has enough shippable units")
        db.expire(line, ["shipped_quantity"])
        shipment.lines.append(ShipmentLine(order_line_id=line_id, quantity=quantity))
    sync_fulfillment_status(db, order, actor, data.reason)
    log(db, actor, "order.fulfillment_created", "shipment", shipment.id, data.reason)
    db.commit(); db.refresh(shipment)
    return shipment_json(shipment)


@router.patch("/orders/{order_id}/fulfillments/{shipment_id}/status", response_model=FulfillmentOut)
def update_fulfillment_status(order_id: int, shipment_id: int, data: ShipmentStatusIn,
                              db: Session = Depends(get_db), actor: User = Depends(require_permissions("orders:manage"))):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    shipment = db.get(Shipment, shipment_id)
    if not shipment or shipment.order_id != order.id:
        raise HTTPException(404, "Fulfillment not found")
    if data.status != "delivered" or shipment.status != "shipped":
        raise HTTPException(409, "A shipped fulfillment can transition only to delivered")
    shipment.status = "delivered"
    shipment.delivered_at = now()
    shipment.delivered_by = actor.id
    shipment.delivery_reason = data.reason
    log(db, actor, "shipment.delivered", "shipment", shipment.id, data.reason)
    if order.status in ("fulfilled", "shipped") and all(item.status == "delivered" or item.id == shipment.id for item in order.shipments):
        record_status(db, order, actor, "delivered", data.reason)
    db.commit(); db.refresh(shipment)
    return shipment_json(shipment)


@router.post("/orders/{order_id}/items/{line_id}/cancel")
def cancel_order_item(order_id: int, line_id: int, data: CancelOrderLineIn,
                      db: Session = Depends(get_db), actor: User = Depends(current_user)):
    order = get_order_for_actor(order_id, actor, db)
    if actor.role not in ("customer", "admin", "ops"):
        raise HTTPException(403, "Insufficient permissions")
    line = next((item for item in order.lines if item.id == line_id), None)
    if not line:
        raise HTTPException(404, "Order line not found")
    cancel_line_quantity(db, order, line, data.quantity, data.reason, actor)
    sync_fulfillment_status(db, order, actor, data.reason)
    db.commit()
    return order_json(order)


@router.post("/orders/{order_id}/backorders/{line_id}/allocate")
def allocate_backorder(order_id: int, line_id: int, data: BackorderAllocationIn,
                       db: Session = Depends(get_db), actor: User = Depends(require_permissions("orders:manage"))):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    line = next((item for item in order.lines if item.id == line_id), None)
    if not line:
        raise HTTPException(404, "Order line not found")
    if data.quantity > line.backordered_quantity:
        raise HTTPException(409, f"Only {line.backordered_quantity} units are backordered")
    result = db.execute(update(Product).where(Product.id == line.product_id, Product.stock >= data.quantity)
                        .values(stock=Product.stock - data.quantity))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Insufficient inventory to allocate this backorder")
    result = db.execute(update(OrderLine).where(OrderLine.id == line.id,
                                                OrderLine.backordered_quantity >= data.quantity)
                        .values(backordered_quantity=OrderLine.backordered_quantity - data.quantity,
                                allocated_quantity=OrderLine.allocated_quantity + data.quantity))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Backorder quantity changed; refresh and retry")
    db.expire(line, ["backordered_quantity", "allocated_quantity"])
    record_activity(db, order, actor, "backorder_allocated", data.reason, line.id, data.quantity)
    log(db, actor, "order.backorder_allocated", "order_line", line.id,
        f"quantity={data.quantity}; reason={data.reason}")
    sync_fulfillment_status(db, order, actor, data.reason)
    db.commit()
    return {"order_id": order.id, "order_line_id": line.id,
            "allocated_quantity": line.allocated_quantity,
            "backordered_quantity": line.backordered_quantity,
            "ready_to_ship": line.allocated_quantity-line.shipped_quantity}

