from .models import Order, Ticket

def order_json(order: Order):
    return {"id": order.id, "customer_id": order.customer_id, "status": order.status, "subtotal": order.subtotal, "discount": order.discount, "total": order.total, "promotion_code": order.promotion_code, "created_at": order.created_at, "items": [{"id": x.id, "product_id": x.product_id, "sku": x.sku, "name": x.name, "unit_price": x.unit_price, "quantity": x.quantity, "allocated_quantity": x.allocated_quantity, "shipped_quantity": x.shipped_quantity, "cancelled_quantity": x.cancelled_quantity, "backordered_quantity": x.backordered_quantity} for x in order.lines]}

def ticket_json(t: Ticket):
    return {"id": t.id, "customer_id": t.customer_id, "order_id": t.order_id, "subject": t.subject, "message": t.message, "status": t.status, "priority": t.priority, "assigned_to": t.assigned_to, "resolution": t.resolution, "created_at": t.created_at, "updated_at": t.updated_at}
