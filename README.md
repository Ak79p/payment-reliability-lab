# Payment Reliability Lab

A miniature payment platform built for learning enterprise-quality software testing.

The system consists of:

- **Order Service** — System Under Test (SUT)
- **Fake Payment Gateway** — fault-injectable test double
- **PostgreSQL** — source of truth for payment state
- pytest integration test suite (written separately)

The project focuses on proving payment correctness through database assertions rather than trusting HTTP responses.

---

## Architecture

### System Under Test: Order Service (port 8000)

The Order Service is the SUT. All test assertions should be made against it and the Postgres database it writes to. It owns the business logic: idempotent checkout, order + payment persistence, and order lookup.

### Test Double: Fake Payment Gateway (port 8001)

The fake gateway is **not** the SUT — it is a controllable stand-in for a real payment processor. It is designed to be fault-injectable in later phases (chaos endpoint, failure modes). For now it is honest: every charge succeeds, and the same `idempotency_key` always returns the same `charge_id` without creating a second charge. The `GET /_charges` inspection endpoint lets tests count how many charges were actually created.

### Database: PostgreSQL (port 5432)

Schema is applied automatically on first `docker-compose up` via `infra/schema.sql` mounted into Postgres's `initdb` directory. Four tables: `orders`, `payments`, `outbox` (stub), `webhook_events` (stub). All money is stored as integer minor units (pence, cents, etc.) — no floats anywhere.

---

## Running

```bash
# Copy env template (only needed for local dev outside Docker)
cp .env.example .env

# Build and start all three containers
docker-compose up --build

# Check all containers are healthy
docker-compose ps
```

All three services expose a `/health` endpoint. `docker-compose ps` will show `healthy` once the healthchecks pass (allow ~30 s on first build).

---

## Manual Verification (curl)

Run these after `docker-compose up` to confirm the happy path before writing automation.

### 1. Confirm all services are up

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl http://localhost:8001/health
# {"status":"ok"}
```

### 2. Create an order (POST /checkout)

```bash
curl -s -X POST http://localhost:8000/checkout \
  -H "Content-Type: application/json" \
  -d '{"amount": 1999, "currency": "GBP", "idempotency_key": "test-key-001"}' | python -m json.tool
# {
#   "order_id": "<uuid>",
#   "status": "paid"
# }
```

Save the returned `order_id` for the next steps.

### 3. Retrieve the order (GET /orders/{id})

```bash
ORDER_ID=<paste-order-id-here>

curl -s http://localhost:8000/orders/$ORDER_ID | python -m json.tool
# {
#   "order_id": "...",
#   "amount": 1999,
#   "currency": "GBP",
#   "status": "paid",
#   "idempotency_key": "test-key-001",
#   "created_at": "...",
#   "updated_at": "..."
# }
```

### 4. Confirm 404 for unknown order

```bash
curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/orders/00000000-0000-0000-0000-000000000000
# 404
```

### 5. Confirm idempotency — same key returns same order, no second charge

```bash
# Submit the same idempotency_key a second time
curl -s -X POST http://localhost:8000/checkout \
  -H "Content-Type: application/json" \
  -d '{"amount": 1999, "currency": "GBP", "idempotency_key": "test-key-001"}' | python -m json.tool
# Returns the same order_id as step 2

# Inspect the gateway — should still show count: 1 (not 2)
curl -s http://localhost:8001/_charges | python -m json.tool
# {
#   "count": 1,
#   "charges": { ... }
# }
```

### 6. Verify data directly in Postgres

```bash
docker exec -it postgres psql -U postgres -d payments \
  -c "SELECT id, amount, currency, status, idempotency_key FROM orders;"

docker exec -it postgres psql -U postgres -d payments \
  -c "SELECT id, order_id, charge_id, amount, status FROM payments;"
```

---

## Project layout

```
.
├── app/                  # Order Service (SUT)
│   ├── app/
│   │   ├── main.py       # FastAPI routes
│   │   ├── entities.py   # SQLAlchemy 2.0 ORM models
│   │   ├── db.py         # Engine + SessionLocal
│   │   └── models.py     # Pydantic request models
│   ├── Dockerfile
│   └── requirements.txt
├── gateway/              # Fake payment gateway (test double)
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py
│   │   └── storage.py    # In-memory charge store
│   ├── Dockerfile
│   └── requirements.txt
├── infra/
│   └── schema.sql        # Applied by Postgres on first start
├── docker-compose.yml
└── .env.example
```

## What is NOT built yet

- Reconciler worker
- `/_chaos` endpoint on the gateway
- Webhook delivery
- Refunds

These are later phases.
