from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field

class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class RefreshIn(BaseModel):
    refresh_token: str

class LogoutIn(BaseModel):
    refresh_token: Optional[str] = None

class EmployeeCreateIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=128)
    role: str = Field(pattern="^(ops|support)$")

class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    description: str = ""
    price: float = Field(gt=0)
    stock: int = Field(ge=0)
    active: bool = True

class ProductPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = None
    price: Optional[float] = Field(default=None, gt=0)
    active: Optional[bool] = None

class StockIn(BaseModel):
    adjustment: int
    reason: str = Field(min_length=1, max_length=200)

class PromotionIn(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    kind: str
    value: float = Field(gt=0)
    minimum_order: float = Field(default=0, ge=0)
    max_uses: Optional[int] = Field(default=None, gt=0)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    active: bool = True

class OrderItemIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=100)

class OrderIn(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1)
    promotion_code: Optional[str] = None
    allow_backorder: bool = False

class StatusIn(BaseModel):
    status: str
    reason: str = Field(min_length=1, max_length=1000)

class CancelOrderLineIn(BaseModel):
    quantity: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=1000)

class BackorderAllocationIn(BaseModel):
    quantity: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=1000)

class FulfillmentItemIn(BaseModel):
    order_line_id: int
    quantity: int = Field(gt=0)

class FulfillmentCreateIn(BaseModel):
    items: list[FulfillmentItemIn] = Field(min_length=1)
    carrier: Optional[str] = Field(default=None, max_length=100)
    tracking_number: Optional[str] = Field(default=None, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)

class ShipmentStatusIn(BaseModel):
    status: str
    reason: str = Field(min_length=1, max_length=1000)

class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=1, max_length=5000)
    order_id: Optional[int] = None
    priority: str = "normal"

class TicketUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[int] = None
    resolution: Optional[str] = None

class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    role: str

class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    refresh_expires_in: int
    role: str
    status: str = "active"
    permissions: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None

class UserUpdateIn(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    role: Optional[str] = Field(default=None, pattern="^(customer|ops|support|admin)$")
    status: Optional[str] = Field(default=None, pattern="^(active|inactive|suspended)$")
    permissions: Optional[list[str]] = None

class UserCreateIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="customer", pattern="^(customer|ops|support|admin)$")
    permissions: list[str] = Field(default_factory=list)

class UserActivityOut(BaseModel):
    id: int
    actor_id: Optional[int]
    action: str
    entity_type: str
    entity_id: Optional[int]
    details: str
    created_at: datetime

class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    description: str = ""
    price: float
    stock: int
    active: bool = True

class PromotionOut(BaseModel):
    id: int
    code: str
    kind: str
    value: float
    active: bool

class OrderLineOut(BaseModel):
    id: int
    product_id: int
    sku: str
    name: str
    unit_price: float
    quantity: int
    allocated_quantity: int = 0
    shipped_quantity: int = 0
    cancelled_quantity: int = 0
    backordered_quantity: int = 0

class OrderOut(BaseModel):
    id: int
    customer_id: int
    status: str
    subtotal: float
    discount: float
    total: float
    promotion_code: Optional[str]
    created_at: datetime
    items: list[OrderLineOut]

class TicketOut(BaseModel):
    id: int
    customer_id: int
    order_id: Optional[int]
    subject: str
    message: str
    status: str
    priority: str
    assigned_to: Optional[int]
    resolution: Optional[str]
    created_at: datetime
    updated_at: datetime

class SummaryReportOut(BaseModel):
    revenue: float
    orders: int
    average_order_value: float
    low_stock_products: int
    open_tickets: int

class SalesPointOut(BaseModel):
    date: str
    orders: int
    revenue: float

class SalesReportOut(BaseModel):
    days: int
    series: list[SalesPointOut]

class FulfillmentLineOut(BaseModel):
    order_line_id: int
    sku: str
    name: str
    quantity: int

class FulfillmentOut(BaseModel):
    id: int
    order_id: int
    status: str
    carrier: Optional[str]
    tracking_number: Optional[str]
    actor_id: int
    reason: str
    created_at: datetime
    shipped_at: datetime
    delivered_at: Optional[datetime]
    delivered_by: Optional[int]
    delivery_reason: Optional[str]
    items: list[FulfillmentLineOut]

class OrderTimelineEventOut(BaseModel):
    event_type: str
    actor_id: int
    timestamp: datetime
    reason: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    shipment_id: Optional[int] = None
    shipment_status: Optional[str] = None
    order_line_id: Optional[int] = None
    quantity: Optional[int] = None

class OrderTimelineOut(BaseModel):
    order_id: int
    current_status: str
    events: list[OrderTimelineEventOut]
