# ShopSphere Pro API — Phase 2

Backend-only FastAPI implementation for commerce operations, customer service, access control, and reporting. It uses MySQL, SQLAlchemy ORM, Alembic migrations, Pydantic schemas, JWT bearer authentication, Swagger UI, and pytest.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SHOPSPHERE_SECRET_KEY = "replace-this-with-a-long-random-secret"
$env:SHOPSPHERE_DATABASE_URL = "mysql+pymysql://shopsphere:password@localhost:3306/shopsphere_pro"
$env:SHOPSPHERE_ADMIN_EMAIL = "admin@shopsphere.local"
$env:SHOPSPHERE_ADMIN_PASSWORD = "replace-with-a-strong-password"
alembic upgrade head
uvicorn app.main:app --reload
```

Create the MySQL database and user before applying migrations. `SHOPSPHERE_DATABASE_URL` accepts a SQLAlchemy URL; the default is a local MySQL connection. Configure the admin environment variables to bootstrap the initial administrator; public registration can only create customer accounts. Run migrations with `alembic upgrade head` before starting the API. Open `/docs` for Swagger UI.

## API areas

- Authentication: registration, login, current user, signed bearer tokens.
- Products and operations: browse/search, admin/operations catalog edits, guarded stock adjustments.
- Promotions: create, validate, usage limits, date windows, minimum order and percentage/fixed discounts.
- Orders: stock validation, promotions, status history, split shipments, item cancellation, back-order allocation, timelines and fulfillment details.
- Customer service: customer-owned support tickets and support/admin queue, assignment and resolution.
- Reporting: summary, daily sales, inventory valuation and admin audit log.

Roles are `customer`, `ops`, `support`, and `admin`. Orders transition through `placed`, `processing`, `partially_fulfilled`, `fulfilled`, and `delivered`, with `backordered` and `cancelled` paths. Shipments can cover part of an order, leaving remaining items for later split shipments. Backorders reserve stock when explicitly allocated, and item cancellation releases allocated stock. Status changes retain the acting user, timestamp, and reason. Money is represented as decimal-like floats in this starter database schema, so a production payment/ledger integration should use integer minor units or a fixed precision decimal type.

## API tests

Run `pytest -q` to exercise the main ordering, authorization, promotions, stock, ticket, and reporting workflows against an isolated in-memory SQLite database. The in-memory database is test-only; production configuration targets MySQL. Import `postman/ShopSphere-Pro.postman_collection.json` into Postman and set its `baseUrl` and `token` collection variables to verify the documented endpoints.

## Project structure

```text
app/
  main.py                 FastAPI application and router registration
  config.py               Environment-based configuration
  database.py             SQLAlchemy engine, session, and base
  models.py               ORM entities
  schemas.py              Pydantic request and response schemas
  security.py             Password hashing and JWT creation/validation
  dependencies.py         Database, authentication, and role dependencies
  services.py             Shared response helpers
  order_workflows.py      Order state and fulfillment rules
  routers/
    auth.py               Registration and login APIs
    products.py           Catalog and stock APIs
    promotions.py         Promotion APIs
    orders.py             Order lifecycle APIs
    tickets.py            Customer-service APIs
    reports.py            Reporting and audit APIs
migrations/               Alembic configuration and revisions
tests/                    Pytest API tests
postman/                  Postman collection
```

Start with `uvicorn app.main:app --reload`. The root `main.py` remains as a compatibility entry point for `uvicorn main:app --reload`.
