# Payment Reliability Lab

A miniature payment platform built for learning enterprise-quality software testing.

The system consists of:

- **Order Service** — System Under Test (SUT)
- **Fake Payment Gateway** — fault-injectable test double
- **PostgreSQL** — source of truth for payment state
- **pytest integration test suite** — drives the SUT and asserts at the database layer

The project focuses on proving payment correctness through database assertions rather than trusting HTTP responses.

---

## Architecture

### System Under Test: Order Service (port 8000)

The Order Service is the SUT. All test assertions are made against it and the Postgres database it writes to. It owns the business logic: idempotent checkout, order + payment persistence, order lookup, and on-demand reconciliation.

Endpoints:

| Method | Path | What it does |
|--------|------|--------------|
| GET | `/health` | Database connectivity check |
| POST | `/checkout` | Idempotent charge + order/payment persistence |
| GET | `/orders/{order_id}` | Retrieve order state |
| POST | `/reconcile` | On-demand reconciliation — heals all pending orders against gateway truth |

### Test Double: Fake Payment Gateway (port 8001)

The fake gateway is **not** the SUT — it is a controllable stand-in for a real payment processor. Every charge succeeds by default. The same `idempotency_key` always returns the same `charge_id` without creating a second charge.

The gateway is fault-injectable via `POST /_chaos`:

| Mode | Behavior |
|------|----------|
| `"lose_confirmation"` | Stores the charge, then returns 504 — a definitive failure signal. The charge succeeded; the confirmation was lost. Auto-resets after one injection. |
| `"timeout_ambiguous"` | Stores the charge, then hangs for 10 s — long enough to force the order service's 5 s client timeout. No status code is ever returned. The caller cannot distinguish "charge happened" from "charge never started." Auto-resets after one injection. |
| `null` | Clears any active chaos mode (honest behavior restored). |

Inspection endpoint `GET /_charges` returns all charges created in the current process, allowing tests to assert charge cardinality independently of the Order Service response.

### Database: PostgreSQL (port 5432)

Schema is applied automatically on first `docker compose up` via `infra/schema.sql` mounted into Postgres's `initdb` directory. Four tables:

- `orders` — idempotency_key is UNIQUE NOT NULL; status is NOT NULL
- `payments` — foreign key to orders; charge_id is UNIQUE NOT NULL
- `outbox` — stub table, provisioned for future transactional outbox work
- `webhook_events` — stub table, provisioned for future webhook deduplication

All money is stored as integer minor units (pence, cents, etc.) — no floats anywhere.

### Reconciler

The reconciler runs **synchronously on demand** — it is triggered by `POST /reconcile` and heals before returning the response. It is not a background worker or polling loop. For each order with `status = "pending"`, it calls `GET /charge/{idempotency_key}` on the gateway. If the gateway has a record, it creates the missing `Payment` row and sets the order to `"paid"`. If the gateway has no record (charge never happened), the order is left as-is.

---

## Running

### First start (cold)

```bash
# Build and start all three containers
docker compose up --build

# In another terminal — confirm all services are healthy
docker compose ps
```

All three services expose a `/health` endpoint. `docker compose ps` will show `(healthy)` once the healthchecks pass — allow ~30 s on first build.

### Resetting to a clean state

If you change `infra/schema.sql` or want a guaranteed clean database:

```bash
# Remove all containers AND the postgres_data volume
docker compose down -v

# Cold start
docker compose up --build
```

`docker compose down` without `-v` leaves the database volume intact. Use `-v` any time you need schema changes to take effect.

### Running the tests

With the stack running:

```bash
pip install -r requirements-test.txt

# Full suite
pytest tests/ -v

# Single file
pytest tests/integration/test_timeout_ambiguity.py -v
```

> **Note:** `test_timeout_ambiguous_charge_is_reconciled` takes ~7–8 s to run. The wait is the scenario — the order service's 5 s client timeout firing against the gateway's deliberate hang. It is not a slow test; it is the correct duration of a network timeout.

Or let CI handle it (see [CI](#ci)).

---

## Manual Verification (curl)

Run these after `docker compose up` to confirm the happy path before writing automation.

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

# Inspect the gateway — should still show one charge, not two
curl -s http://localhost:8001/_charges | python -m json.tool
```

### 6. Inject a fault and reconcile

```bash
# Arm the gateway to lose the next confirmation
curl -s -X POST http://localhost:8001/_chaos \
  -H "Content-Type: application/json" \
  -d '{"mode": "lose_confirmation"}'

# Attempt checkout — expect 504 (gateway accepted the charge but dropped the response)
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/checkout \
  -H "Content-Type: application/json" \
  -d '{"amount": 999, "currency": "USD", "idempotency_key": "chaos-key-001"}'
# 504

# Order exists in DB but is still "pending" — no payment row
docker exec -it postgres psql -U postgres -d payments \
  -c "SELECT id, status FROM orders WHERE idempotency_key = 'chaos-key-001';"

# Heal via reconciler
curl -s -X POST http://localhost:8000/reconcile | python -m json.tool
# {"reconciled": true}

# Order is now "paid"
docker exec -it postgres psql -U postgres -d payments \
  -c "SELECT id, status FROM orders WHERE idempotency_key = 'chaos-key-001';"
```

### 7. Verify data directly in Postgres

```bash
docker exec -it postgres psql -U postgres -d payments \
  -c "SELECT id, amount, currency, status, idempotency_key FROM orders;"

docker exec -it postgres psql -U postgres -d payments \
  -c "SELECT id, order_id, charge_id, amount, status FROM payments;"
```

---

## Test Suite

Five integration tests across four files. All tests assert at the database layer — HTTP responses are checked as a secondary signal only.

### Failure classes with real coverage

**Idempotency** (`tests/integration/test_idempotency.py`)

- `test_sequential_retry` — sends the same `idempotency_key` twice in sequence. Asserts one order row, one payment row, one gateway charge.
- `test_concurrent_duplicate` — sends two identical requests simultaneously via `ThreadPoolExecutor`. Asserts the database UNIQUE constraint resolves the race to exactly one order, one payment, one gateway charge.

**Dual-write reconciliation** (`tests/integration/test_reconciliation.py`)

- `test_reconcile_charged_but_unconfirmed` — arms `lose_confirmation`, submits a checkout (expects 504 — a definitive failure signal), asserts the order is stuck `"pending"` with no payment row. Calls `POST /reconcile`. Asserts the order transitions to `"paid"`, one payment row exists, and the gateway charge count is still 1.

**Timeout ambiguity** (`tests/integration/test_timeout_ambiguity.py`)

- `test_timeout_ambiguous_charge_is_reconciled` — arms `timeout_ambiguous`, submits a checkout. The order service's 5 s client timeout fires; the endpoint returns **502** (the deliberate ambiguity signal, distinct from `lose_confirmation`'s 504). Asserts the gateway has the charge, the order is `"pending"`, and zero payment rows exist. Calls `POST /reconcile`. Asserts convergence to `"paid"`, one payment row, no second charge. This test runs in ~7–8 s — the wait is the timeout firing, not test overhead.

**Baseline** (`tests/integration/test_checkout.py`)

- `test_checkout_happy_path` — successful end-to-end checkout. Asserts HTTP 200, correct order row in DB, correct payment row in DB, exactly one gateway charge.

### Test harness

`tests/conftest.py` provides:

- `engine` (session scope) — SQLAlchemy engine for direct DB inspection, separate from the application's connection pool
- `client` (session scope) — `httpx.Client` pointed at the Order Service
- `clean_ledger` (function scope, autouse) — truncates `payments` and `orders` before every test
- `reset_gateway_chaos` (function scope, autouse) — POSTs `{"mode": null}` to `/_chaos` before every test
- `idempotency_key` (function scope) — generates a fresh `uuid4` string per test

DB inspection helpers in `tests/helpers/db.py` query raw SQL against the `engine`, not through the application. Gateway inspection helpers in `tests/helpers/gateway.py` call `GET /_charges` on the fake gateway.

---

## CI

GitHub Actions runs the full stack on every push and pull request. See `.github/workflows/ci.yml`.

The workflow:
1. Installs test dependencies on the runner
2. Runs `docker compose up --build --wait` — builds all images from scratch and blocks until all three healthchecks pass (no arbitrary sleep)
3. Runs `pytest tests/integration/ -v` with service URLs set as environment variables
4. Runs `docker compose down -v` to clean up volumes (always, even on failure)

Each CI job runs on a fresh ephemeral runner with no pre-existing volumes, so it is structurally equivalent to `docker compose down -v && docker compose up` — schema is applied exactly once from `infra/schema.sql`.

---

## How to Add Your Own Test

1. Pick a failure class (see "Scoped out" below for candidates).
2. Create a new file in `tests/integration/` named `test_<failure_class>.py`.
3. Import the fixtures you need — `client`, `db`, `idempotency_key` are available from `conftest.py` by default. `clean_ledger` and `reset_gateway_chaos` run automatically before every test.
4. Use `tests/helpers/db.py` to assert against the database directly. Do not rely solely on HTTP responses.
5. Use `tests/helpers/gateway.py` to verify charge cardinality at the gateway.
6. To inject a fault, POST to `http://localhost:8001/_chaos` before the act step. Available modes: `"lose_confirmation"` (gateway returns 504 — definitive failure) and `"timeout_ambiguous"` (gateway hangs until the caller times out — genuine ambiguity). Both auto-reset after one use.

Example skeleton:

```python
def test_my_scenario(client, db, idempotency_key):
    # Arrange
    payload = {"amount": 500, "currency": "GBP", "idempotency_key": idempotency_key}

    # Act
    response = client.post("/checkout", json=payload)

    # Assert at HTTP layer
    assert response.status_code == 200

    # Assert at DB layer (source of truth)
    from tests.helpers.db import get_order_by_key, get_payment_by_order
    order = get_order_by_key(db, idempotency_key)
    assert order["status"] == "paid"
    payment = get_payment_by_order(db, order["id"])
    assert payment is not None
```

---

## Project Layout

```
.
├── app/                        # Order Service (SUT)
│   ├── app/
│   │   ├── main.py             # FastAPI routes
│   │   ├── entities.py         # SQLAlchemy ORM models (Order, Payment)
│   │   ├── db.py               # Engine + SessionLocal
│   │   ├── models.py           # Pydantic request models
│   │   ├── reconciler.py       # reconcile() coroutine (on-demand, synchronous)
│   │   └── repositories.py     # Repository classes (defined, available for future use)
│   ├── Dockerfile
│   └── requirements.txt
├── gateway/                    # Fake payment gateway (test double)
│   ├── app/
│   │   ├── main.py             # Routes including /_chaos, /_charges
│   │   ├── models.py
│   │   └── storage.py          # In-memory charge store
│   ├── Dockerfile
│   └── requirements.txt
├── infra/
│   └── schema.sql              # Applied by Postgres on first start via initdb
├── tests/
│   ├── conftest.py             # Fixtures: engine, client, clean_ledger, reset_gateway_chaos
│   ├── helpers/
│   │   ├── db.py               # Raw-SQL inspection helpers
│   │   └── gateway.py          # Gateway HTTP inspection helpers
│   └── integration/
│       ├── test_checkout.py
│       ├── test_idempotency.py
│       ├── test_reconciliation.py
│       └── test_timeout_ambiguity.py
├── .github/workflows/ci.yml   # GitHub Actions CI
├── docker-compose.yml
├── pytest.ini
├── requirements-test.txt
└── .env.example
```

---

## Scoped Out — Designed but Deferred

These three failure classes are deliberately not implemented. The schema stubs (`outbox`, `webhook_events`) are already provisioned for the first two.

### Webhooks

The gateway would deliver async charge notifications to the Order Service via signed POST requests. The `webhook_events` table (already in schema) would deduplicate incoming events on `event_id` (UNIQUE NOT NULL), and a signature verification step would reject tampered payloads before any state change. An out-of-order winner rule (e.g. ignore a `charge.failed` event if the order is already `"paid"`) would prevent late arrivals from corrupting settled state.

### State-Machine Integrity

Valid status transitions (e.g. `pending → paid` is allowed; `paid → pending` is not) are not currently enforced at the schema or application layer. Enforcement would be a CHECK constraint on `orders.status` combined with a transition guard in the application, and tests would attempt forbidden transitions and assert rejection. Without this, a bug or a reconciler edge case could silently reverse a settled order.

### Money Correctness

No test currently verifies that `payments.amount` equals `orders.amount` for the same order, or that `payments.currency` matches `orders.currency`, across the full charge round-trip. The `amount` column is `INTEGER` (minor units) which eliminates float precision risk at the schema level, but the end-to-end invariant — that the amount charged is exactly the amount ordered — is unverified. Tests would assert equality across both rows and confirm no transformation occurs at the gateway boundary.

---

## Incident Playbook

See [INCIDENT_PLAYBOOK.md](./INCIDENT_PLAYBOOK.md) for runbooks covering known failure modes and recovery steps.
