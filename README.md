# Payment Reliability Lab

A payment reliability testing project that reproduces one of the most common distributed systems failures: the customer is charged, but the application never records the payment.

Instead of testing HTTP responses, this project verifies the database ledger, where financial truth actually lives.

The system intentionally creates payment failures, proves the inconsistency exists, and then demonstrates automatic recovery without charging the customer twice.

---

## The Problem

Imagine buying something online.

You click **Pay**.
Your bank immediately shows the payment.
But the website displays:

> "Payment failed."

The customer has been charged.
The application believes the payment failed.
Both systems are now telling different stories.

This project recreates that exact failure and verifies that the system eventually converges back to the correct financial state.

---

## What this project demonstrates

Unlike a typical CRUD application, this project focuses on payment correctness under distributed failures.

It demonstrates how to test:

- Idempotent payment processing
- Concurrent duplicate requests
- Lost payment confirmations
- Database reconciliation
- Financial invariants
- Fault injection
- Integration testing with PostgreSQL

The emphasis is on verifying persisted financial state, not simply asserting HTTP responses.

---

## Architecture

![Architecture](images/architecture.svg)

The project contains three components.

### Order Service (System Under Test)

The Order Service owns the payment workflow. It:

- creates orders
- charges the gateway
- records payments
- reconciles failed confirmations

### Fake Payment Gateway

The gateway is **not** the system under test. Instead, it is a deterministic test double that allows payment failures to be reproduced on demand.

It supports:

- successful charges
- idempotent charging
- intentionally lost confirmations (`504`)
- gateway inspection endpoints

This makes normally rare production failures completely repeatable inside automated tests.

### PostgreSQL

PostgreSQL is treated as the financial source of truth. Every integration test verifies:

- order state
- payment rows
- charge count
- financial consistency

rather than trusting API responses alone.

> For a full code-and-design walkthrough, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Test Scenarios

### Happy Path

A successful payment should produce:

- one order
- one payment
- one gateway charge

### Idempotency

A customer retries the same payment.

Expected result:

- same order
- same payment
- exactly one gateway charge

Even under concurrent requests.

### Flagship Scenario — Customer Charged, Order Shows Pending

This is the primary scenario demonstrated by the project.

**Symptom**

- The customer is charged successfully.
- The application returns HTTP `504`.
- The order remains `pending`.
- No payment record exists.

**Root Cause**

The order is persisted before contacting the payment gateway. The gateway successfully charges the customer. The payment confirmation is then intentionally lost.

As a result:

- money has moved
- the application never records the payment

The system has entered a classic dual-write inconsistency.

**Recovery**

A reconciler scans pending orders. Using the durable idempotency key, it queries the payment gateway to determine the actual payment state.

If the gateway reports that the charge succeeded:

- the missing payment row is created
- the order becomes `paid`
- no additional charge is issued

**Flagship Integration Test** — `test_reconcile_charged_but_unconfirmed`

This test proves the complete recovery flow. It:

1. injects a lost-confirmation fault
2. verifies the customer has been charged
3. verifies the order remains pending
4. verifies no payment record exists
5. executes reconciliation
6. verifies the order becomes paid
7. verifies exactly one gateway charge still exists

**Invariant:** Money moved ⇔ the ledger eventually reflects reality.

> The full incident write-up — symptom, evidence trail, root cause, recovery, and the catching test — is in [`docs/INCIDENT_PLAYBOOK.md`](docs/INCIDENT_PLAYBOOK.md). Every scenario in depth, including those scoped out, is in [`docs/SCENARIOS.md`](docs/SCENARIOS.md).

---

## Technology

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- pytest
- httpx
- Docker
- Docker Compose

---

## Running the project

```bash
docker compose up --build
pytest tests -v
```

Reset the database:

```bash
docker compose down -v
```
---

## Future Enhancements

The project is intentionally scoped around the highest-value payment failure scenarios. Future extensions could include:

- Webhook processing
- Signature verification
- Out-of-order event delivery
- Refund workflows
- State-machine validation
- Money correctness and partial refunds
- GitHub Actions CI/CD