# Payment Reliability Lab

**Testing the seam where payments break:** the customer is charged, but the order never records it. This project reproduces that failure on demand and proves the system recovers — asserting against the money's real location, never an HTTP `200`.

![Architecture](images/architecture.svg)

A containerized **Order Service** (the system under test) charges a **fake, fault-injectable gateway** and writes to **PostgreSQL**. A pytest suite drives it and inspects the database directly.

---

## What it tests

Every test asserts at the database layer. A `200` is what the service *claims*; the rows are what's *true*.

| Scenario | Real-world failure | What's proven |
|---|---|---|
| **Idempotency** | A retry or double-tap charges the customer twice | Same key → one order, one charge — enforced by a DB `UNIQUE` constraint under concurrency |
| **Dual-write reconciliation** *(flagship)* | Card charged, but the confirmation is lost — app shows "failed" | Stranded order is healed to `paid`, with no second charge |
| **Timeout ambiguity** | The gateway call times out — did the charge happen? | "Unknown" is handled as recoverable (502 + pending), not assumed-failed |

Full detail in [`docs/SCENARIOS.md`](docs/SCENARIOS.md) · architecture and code walkthrough in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · the flagship incident write-up in [`docs/INCIDENT_PLAYBOOK.md`](docs/INCIDENT_PLAYBOOK.md).

---

## Quickstart

Requires [Docker](https://www.docker.com/products/docker-desktop/) (enable the **WSL 2** backend on Windows).

```bash
# Start the stack (three services)
docker compose up --build

# Run the tests
pip install -r requirements-test.txt
pytest tests/ -v
```

Reset the database (needed after schema changes): `docker compose down -v`

> One test takes ~7s — that's a real network timeout firing, which *is* the scenario.

---

## What's scoped out

Three failure classes are covered thoroughly rather than six shallowly. Deferred by design — **webhooks**, **state-machine integrity**, and **money correctness** — with how each would be built, and why it matters, in [`docs/SCENARIOS.md`](docs/SCENARIOS.md). The schema already provisions for the first two.
