from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from .database import Base

def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, index=True, nullable=False)
    name = Column(String(120), nullable=False)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(20), nullable=False, default="customer")
    created_at = Column(DateTime, default=now, nullable=False)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    sku = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(160), nullable=False)
    description = Column(Text, default="")
    price = Column(Float, nullable=False)
    stock = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=now, nullable=False)

class Promotion(Base):
    __tablename__ = "promotions"
    id = Column(Integer, primary_key=True)
    code = Column(String(40), unique=True, index=True, nullable=False)
    kind = Column(String(10), nullable=False)  # percent | fixed
    value = Column(Float, nullable=False)
    minimum_order = Column(Float, default=0, nullable=False)
    max_uses = Column(Integer, nullable=True)
    uses = Column(Integer, default=0, nullable=False)
    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    active = Column(Boolean, default=True, nullable=False)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    status = Column(String(24), default="placed", index=True, nullable=False)
    subtotal = Column(Float, nullable=False)
    discount = Column(Float, default=0, nullable=False)
    total = Column(Float, nullable=False)
    promotion_code = Column(String(40), nullable=True)
    created_at = Column(DateTime, default=now, nullable=False)
    updated_at = Column(DateTime, default=now, onupdate=now, nullable=False)
    lines = relationship("OrderLine", cascade="all, delete-orphan", lazy="selectin")
    status_history = relationship("OrderStatusHistory", cascade="all, delete-orphan", order_by="OrderStatusHistory.created_at", lazy="selectin")
    activities = relationship("OrderActivity", cascade="all, delete-orphan", order_by="OrderActivity.created_at", lazy="selectin")
    shipments = relationship("Shipment", cascade="all, delete-orphan", order_by="Shipment.created_at", lazy="selectin")

class OrderLine(Base):
    __tablename__ = "order_lines"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    sku = Column(String(64), nullable=False)
    name = Column(String(160), nullable=False)
    unit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    allocated_quantity = Column(Integer, nullable=False, default=0)
    shipped_quantity = Column(Integer, nullable=False, default=0)
    cancelled_quantity = Column(Integer, nullable=False, default=0)
    backordered_quantity = Column(Integer, nullable=False, default=0)


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    from_status = Column(String(24), nullable=True)
    to_status = Column(String(24), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now, nullable=False)


class OrderActivity(Base):
    __tablename__ = "order_activities"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False)
    order_line_id = Column(Integer, ForeignKey("order_lines.id"), nullable=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(String(40), nullable=False)
    quantity = Column(Integer, nullable=True)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now, nullable=False)


class Shipment(Base):
    __tablename__ = "shipments"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False)
    status = Column(String(20), default="shipped", nullable=False)
    carrier = Column(String(100), nullable=True)
    tracking_number = Column(String(120), nullable=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now, nullable=False)
    shipped_at = Column(DateTime, default=now, nullable=False)
    delivered_at = Column(DateTime, nullable=True)
    delivered_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    delivery_reason = Column(Text, nullable=True)
    lines = relationship("ShipmentLine", cascade="all, delete-orphan", lazy="selectin")


class ShipmentLine(Base):
    __tablename__ = "shipment_lines"
    id = Column(Integer, primary_key=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)
    order_line_id = Column(Integer, ForeignKey("order_lines.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    order_line = relationship("OrderLine")

class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    subject = Column(String(160), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), default="open", index=True, nullable=False)
    priority = Column(String(12), default="normal", nullable=False)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now, nullable=False)
    updated_at = Column(DateTime, default=now, onupdate=now, nullable=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(80), nullable=False)
    entity_type = Column(String(40), nullable=False)
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, default="")
    created_at = Column(DateTime, default=now, nullable=False)
