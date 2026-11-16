import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app import main
from app.security import make_token, password_hash


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    main.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    with TestClient(main.app) as client:
        yield client
    main.Base.metadata.drop_all(engine)
    engine.dispose()


def register_and_login(client, email="buyer@example.com"):
    response = client.post("/auth/register", json={"email": email, "name": "Buyer", "password": "strong-pass-123"})
    assert response.status_code == 201
    response = client.post("/auth/login", json={"email": email, "password": "strong-pass-123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_commerce_workflow_and_permissions(client):
    buyer_headers = register_and_login(client)
    with database.SessionLocal() as db:
        admin = main.User(email="admin@example.com", name="Admin", password_hash=password_hash("admin-pass-123"), role="admin")
        ops = main.User(email="ops@example.com", name="Ops", password_hash=password_hash("ops-pass-123"), role="ops")
        db.add_all([admin, ops]); db.commit()
    admin_headers = {"Authorization": f"Bearer {make_token(admin)}"}
    ops_headers = {"Authorization": f"Bearer {make_token(ops)}"}

    assert client.post("/products", headers=buyer_headers, json={"sku": "SKU-1", "name": "Widget", "price": 20, "stock": 10}).status_code == 403
    product = client.post("/products", headers=ops_headers, json={"sku": "SKU-1", "name": "Widget", "price": 20, "stock": 10}).json()
    promo = client.post("/promotions", headers=admin_headers, json={"code": "SAVE10", "kind": "percent", "value": 10, "max_uses": 1})
    assert promo.status_code == 201

    placed = client.post("/orders", headers=buyer_headers, json={"items": [{"product_id": product["id"], "quantity": 2}], "promotion_code": "SAVE10"})
    assert placed.status_code == 201
    assert placed.json()["total"] == 36
    assert client.get("/products").json()[0]["stock"] == 8
    assert client.post("/orders", headers=buyer_headers, json={"items": [{"product_id": product["id"], "quantity": 1}], "promotion_code": "SAVE10"}).status_code == 409

    order_id = placed.json()["id"]
    assert client.patch(f"/orders/{order_id}/status", headers=ops_headers, json={"status": "processing", "reason": "Picking started"}).status_code == 200
    assert client.patch(f"/orders/{order_id}/status", headers=ops_headers, json={"status": "delivered", "reason": "Attempt invalid transition"}).status_code == 409
    ticket = client.post("/tickets", headers=buyer_headers, json={"subject": "Delivery question", "message": "Where is my package?", "order_id": order_id})
    assert ticket.status_code == 201
    assert client.get("/reports/summary", headers=ops_headers).json()["revenue"] == 36
    assert client.get("/reports/summary", headers=buyer_headers).status_code == 403
    assert client.patch(f"/tickets/{ticket.json()['id']}", headers=admin_headers, json={"status": "resolved", "resolution": "Shipment is in transit"}).json()["status"] == "resolved"


def test_customer_cannot_read_another_customers_order(client):
    buyer = register_and_login(client, "first@example.com")
    other = register_and_login(client, "second@example.com")
    with database.SessionLocal() as db:
        ops = main.User(email="ops@example.com", name="Ops", password_hash=password_hash("ops-pass-123"), role="ops")
        db.add(ops); db.commit()
    ops_headers = {"Authorization": f"Bearer {make_token(ops)}"}
    product = client.post("/products", headers=ops_headers, json={"sku": "SKU-2", "name": "Book", "price": 8, "stock": 2}).json()
    order = client.post("/orders", headers=buyer, json={"items": [{"product_id": product["id"], "quantity": 1}]}).json()
    assert client.get(f"/orders/{order['id']}", headers=other).status_code == 403


def test_split_fulfillments_status_history_and_timeline(client):
    buyer = register_and_login(client)
    with database.SessionLocal() as db:
        ops = main.User(email="ops@example.com", name="Ops", password_hash=password_hash("ops-pass-123"), role="ops")
        db.add(ops); db.commit()
    ops_headers = {"Authorization": f"Bearer {make_token(ops)}"}
    product = client.post("/products", headers=ops_headers, json={"sku": "SPLIT-1", "name": "Split item", "price": 12, "stock": 5}).json()
    order = client.post("/orders", headers=buyer, json={"items": [{"product_id": product["id"], "quantity": 3}]}).json()
    order_id, line_id = order["id"], order["items"][0]["id"]
    started = client.patch(f"/orders/{order_id}/status", headers=ops_headers,
                           json={"status": "processing", "reason": "Warehouse started picking"})
    assert started.status_code == 200

    first = client.post(f"/orders/{order_id}/fulfillments", headers=ops_headers, json={
        "items": [{"order_line_id": line_id, "quantity": 1}], "carrier": "ParcelCo",
        "tracking_number": "TRACK-1", "reason": "First parcel dispatched"})
    assert first.status_code == 201
    assert client.get(f"/orders/{order_id}", headers=buyer).json()["status"] == "partially_fulfilled"
    second = client.post(f"/orders/{order_id}/fulfillments", headers=ops_headers, json={
        "items": [{"order_line_id": line_id, "quantity": 2}], "carrier": "ParcelCo",
        "tracking_number": "TRACK-2", "reason": "Remaining items dispatched"})
    assert second.status_code == 201
    assert client.get(f"/orders/{order_id}", headers=buyer).json()["status"] == "fulfilled"
    assert len(client.get(f"/orders/{order_id}/fulfillments", headers=buyer).json()) == 2
    assert client.patch(f"/orders/{order_id}/fulfillments/{first.json()['id']}/status", headers=ops_headers,
                        json={"status": "delivered", "reason": "First parcel received"}).status_code == 200
    delivered = client.patch(f"/orders/{order_id}/fulfillments/{second.json()['id']}/status", headers=ops_headers,
                            json={"status": "delivered", "reason": "Second parcel received"})
    assert delivered.status_code == 200
    timeline = client.get(f"/orders/{order_id}/timeline", headers=buyer).json()
    assert timeline["current_status"] == "delivered"
    assert any(event["reason"] == "Warehouse started picking" for event in timeline["events"])
    assert sum(event["event_type"] == "shipment_delivered" for event in timeline["events"]) == 2


def test_backorder_allocation_and_item_cancellation(client):
    buyer = register_and_login(client)
    with database.SessionLocal() as db:
        ops = main.User(email="ops@example.com", name="Ops", password_hash=password_hash("ops-pass-123"), role="ops")
        db.add(ops); db.commit()
    ops_headers = {"Authorization": f"Bearer {make_token(ops)}"}
    product = client.post("/products", headers=ops_headers, json={"sku": "BACK-1", "name": "Backorder item", "price": 10, "stock": 2}).json()
    order = client.post("/orders", headers=buyer, json={
        "items": [{"product_id": product["id"], "quantity": 4}], "allow_backorder": True}).json()
    order_id, line_id = order["id"], order["items"][0]["id"]
    assert order["status"] == "backordered"
    assert order["items"][0]["backordered_quantity"] == 2

    first_shipment = client.post(f"/orders/{order_id}/fulfillments", headers=ops_headers, json={
        "items": [{"order_line_id": line_id, "quantity": 1}], "reason": "Ship available stock"})
    assert first_shipment.status_code == 201
    assert client.get(f"/orders/{order_id}", headers=buyer).json()["status"] == "partially_fulfilled"
    assert client.post(f"/products/{product['id']}/stock-adjustments", headers=ops_headers,
                       json={"adjustment": 2, "reason": "Supplier delivery"}).status_code == 200
    allocated = client.post(f"/orders/{order_id}/backorders/{line_id}/allocate", headers=ops_headers,
                            json={"quantity": 2, "reason": "Allocated replenished inventory"})
    assert allocated.status_code == 200
    cancelled = client.post(f"/orders/{order_id}/items/{line_id}/cancel", headers=buyer,
                            json={"quantity": 1, "reason": "Customer reduced quantity"})
    assert cancelled.status_code == 200
    assert cancelled.json()["items"][0]["cancelled_quantity"] == 1
    shipment = client.post(f"/orders/{order_id}/fulfillments", headers=ops_headers, json={
        "items": [{"order_line_id": line_id, "quantity": 2}], "reason": "Remaining quantity shipped"})
    assert shipment.status_code == 201
    order_after = client.get(f"/orders/{order_id}", headers=buyer).json()
    assert order_after["status"] == "fulfilled"
    assert order_after["items"][0]["backordered_quantity"] == 0
    timeline = client.get(f"/orders/{order_id}/timeline", headers=buyer).json()
    assert any(event["event_type"] == "backorder_allocated" for event in timeline["events"])
    assert any(event["event_type"] == "item_cancelled" for event in timeline["events"])
