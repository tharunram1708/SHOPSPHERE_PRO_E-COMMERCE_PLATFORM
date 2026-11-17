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

- Authentication: customer registration, customer and employee login, 15-minute access JWTs, rotating 7-day refresh JWTs, logout/revocation, password hashing, and role checks.
- User management: admin search/filter, profile and role updates, explicit permission grants, activation/deactivation, account status, and user activity history.
- Products and operations: browse/search, admin/operations catalog edits, guarded stock adjustments.
- Promotions: create, validate, usage limits, date windows, minimum order and percentage/fixed discounts.
- Orders: stock validation, promotions, status history, split shipments, item cancellation, back-order allocation, timelines and fulfillment details.
- Customer service: customer-owned support tickets and support/admin queue, assignment and resolution.
- Reporting: summary, daily sales, inventory valuation and admin audit log.

Roles are `customer`, `ops`, `support`, and `admin`. Orders transition through `placed`, `processing`, `partially_fulfilled`, `fulfilled`, and `delivered`, with `backordered` and `cancelled` paths. Shipments can cover part of an order, leaving remaining items for later split shipments. Backorders reserve stock when explicitly allocated, and item cancellation releases allocated stock. Status changes retain the acting user, timestamp, and reason. Money is represented as decimal-like floats in this starter database schema, so a production payment/ledger integration should use integer minor units or a fixed precision decimal type.

### Authentication endpoints

- `POST /auth/register` creates a customer account. Public registration cannot set an employee role.
- `POST /auth/customer/login` and `POST /auth/employee/login` issue access and refresh tokens for the matching account type. `POST /auth/login` remains as a compatibility endpoint for either type.
- `POST /auth/refresh` accepts `{ "refresh_token": "..." }`, revokes that refresh token, and returns a fresh token pair. A refresh token can only be used once.
- `POST /auth/logout` requires the access bearer token and revokes that login session's access and refresh tokens. It optionally accepts `{ "refresh_token": "..." }` for clients that want to supply the refresh token explicitly. Revoked tokens fail authentication immediately.
- `POST /auth/employees` is admin only and creates `ops` or `support` accounts. The initial admin can be bootstrapped with `SHOPSPHERE_ADMIN_EMAIL` and `SHOPSPHERE_ADMIN_PASSWORD`.
- `GET /auth/me` returns the authenticated account. Existing role guarded endpoints enforce permissions for `customer`, `ops`, `support`, and `admin` roles.

Apply the new token persistence table with `alembic upgrade head` before using managed access and refresh tokens.

### User management endpoints

Admin users can use `GET /users` with optional `q`, `role`, and `status` filters; `GET /users/{id}`; and `PATCH /users/{id}` to update email, name, role, status (`active`, `inactive`, or `suspended`), and explicit permissions. `POST /users/{id}/deactivate` and `/activate` provide account status actions. `GET /users/{id}/activity` returns the audit trail for that user. Deactivation revokes existing sessions and prevents new logins; reactivation does not restore old tokens.

Roles grant their standard permission bundles (`ops`, `support`, `admin`); admins can add per-user permissions from `products:write`, `stock:adjust`, `promotions:write`, `orders:manage`, `tickets:manage`, `reports:read`, and `audit:read`. Apply all migrations with `alembic upgrade head`.

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
