# Architecture & Code Walkthrough

A guide for QA/SDET engineers who want to understand how this project works, why it's built the way it is, and how to extend it. Read this alongside the code — file and function references are given throughout.

---

## What this project is

A miniature, containerized payment system built **specifically to be tested under failure**. It deliberately reproduces the failure modes that real checkout systems hit in production — most importantly, the case where a customer is charged but the order never records it.

The point is not the application. The point is the **test automation around it** and the reasoning that drives each test. The application exists to be a realistic, controllable target.

---

## The one distinction that matters: SUT vs. test double

Everything in this project flows from one separation:

- **The System Under Test (SUT)** is the **Order Service** — the code you own that orchestrates "charge money, then record fulfillment." Its correctness is what's being proven. It includes the order/payment domain, the reconciler, and the Postgres ledger.

- **The Fake Gateway is a test double** — a controllable stand-in for a real payment processor (Stripe, Adyen, etc.). It is *not* under test. You are not verifying the processor's correctness; you are verifying **how your system behaves when the processor does something inconvenient.**

This is the senior mental model of payment testing. You don't test Stripe. You test your own system's behavior when Stripe charges the card but the network eats the response. The fake gateway exists so you can *force* that situation on demand — something a real processor's test mode won't let you do reliably.

---

## The three services

The stack runs as three containers via `docker-compose.yml`:

| Service | Port | Role |
|---|---|---|
| **Order Service** (`app/`) | 8000 | The SUT — orchestrates checkout, reconciliation |
| **Fake Gateway** (`gateway/`) | 8001 | Test double — charges + fault injection |
| **PostgreSQL** | 5432 | The durable ledger |

```
        TEST HARNESS (pytest)
   ┌──────────────────────────────┐
   │ httpx clients · fixtures ·   │
   │ chaos controls · DB asserts  │
   └──────┬────────────────┬──────┘
          │ drives         │ inspects committed state
          ▼                ▼
   ┌──────────────┐   ┌────────────┐
   │ Order Svc    │──▶│  Postgres  │
   │ /checkout    │   │  orders    │
   │ /orders/:id  │   │  payments  │
   │ /reconcile   │   │  (outbox)  │
   └──────┬───────┘   │  (webhooks)│
          │ charge    └─────┬──────┘
          ▼                 │ reconciler converges
   ┌──────────────┐         │
   │ Fake Gateway │◀────────┘
   │ /charge      │   re-queried by idempotency_key
   │ /_chaos      │   during reconciliation
   │ /_charges    │
   └──────────────┘
```

---

## The data model

Four tables (`infra/schema.sql`). Two are active; two are provisioned for deferred work.

**`orders`** — the order record. Key field: `idempotency_key VARCHAR(255) UNIQUE NOT NULL`. That `UNIQUE` constraint is not decoration — it is the enforcement mechanism for idempotency under concurrency (explained below).

**`payments`** — the payment record, one per successful charge, linked to an order by a non-null foreign key. `charge_id` is `UNIQUE` so the same gateway charge can't be recorded twice.

**`outbox`** and **`webhook_events`** — present in the schema, written by no code yet. They exist to receive the deferred webhook/eventing work, and `webhook_events.event_id` already carries the `UNIQUE` constraint that would give at-most-once event processing.

All money is stored as **integer minor units** (e.g. cents). No floats anywhere — float arithmetic on money drifts, and that drift is itself a bug class.

---

## The critical code path: `/checkout`

This is the heart of the SUT, and its **ordering is deliberate**. Read `app/app/main.py`. The flow:

**Step 1 — Idempotency pre-check.** Query for an existing order with this `idempotency_key`. If found, return it immediately without charging. This is an *optimization* — it catches the common case cheaply.

**Step 2 — Write the order as `pending`, and commit (Transaction 1).** The order row is persisted *before* any money moves. If a concurrent request hits the `UNIQUE` constraint here, the `IntegrityError` is caught, the session rolled back, and the winning row re-queried and returned.

**Step 3 — Call the gateway to charge.** This is an external HTTP call, outside any database transaction.

**Step 4 — Write the payment and flip the order to `paid`, and commit (Transaction 2).**

```
Transaction 1:  INSERT order (status=pending)         ← before the charge
      │
      ▼
   gateway /charge   ← money moves here, outside any DB transaction
      │
      ▼
Transaction 2:  INSERT payment + UPDATE order=paid     ← after the charge
```

**Why persist `pending` before charging?** Because the gap between Transaction 1 and Transaction 2 is where the system can crash — and if it does, you need a durable record to recover from. The `pending` order, carrying the `idempotency_key`, is the thread that lets the reconciler find the money later. **If the order weren't persisted first, a lost confirmation would leave no record at all, and recovery would be impossible.** The "bug" (the dual-write window) and the "fix" (recoverability) are the same design decision.

---

## Idempotency: two mechanisms, one invariant

The project enforces "one purchase = one charge" with **two layers**, and understanding why both exist is the core lesson:

1. **Application pre-check** (Step 1 above) — fast, handles sequential retries, but **insufficient under concurrency**. Two simultaneous requests can both run the pre-check, both see no existing order, and both proceed — a classic time-of-check-to-time-of-use race.

2. **Database `UNIQUE` constraint** — the real guarantee. When both racing requests try to insert, the database lets exactly one win; the other gets an `IntegrityError`, which the service catches and resolves by returning the winning order.

The one-sentence version, worth being able to say aloud: *the pre-check is an optimization for the common case; the database constraint is the correctness guarantee under concurrency.*

---

## Fault injection: the chaos endpoint

The fake gateway (`gateway/app/main.py`) exposes `POST /_chaos` to arm a misbehavior on the next charge. Two modes are implemented, and the difference between them is itself a lesson:

**`lose_confirmation`** — the charge is recorded in the gateway's store first (the money moves), *then* the gateway returns an HTTP **504**. The caller gets a *definitive* failure signal — the gateway is explicitly saying "something went wrong" — but the charge exists and is queryable afterward via `/charge/{idempotency_key}`. The mode auto-resets after one use.

**`timeout_ambiguous`** — the charge is recorded first (the money moves), *then* the gateway hangs (~10s) until the order service's client timeout (~5s) fires. The caller receives **no response at all** — not a status code, just a closed connection. This is *genuine* ambiguity: the caller cannot tell whether the charge happened. The order service catches the `httpx.TimeoutException` and returns a deliberate **502**, leaving the order `pending`. The mode auto-resets after one use.

The distinction is the point: a **504 is a definitive failure the gateway reported**; a **timeout (surfaced as 502) is "I don't know what happened."** Both record the charge, both leave the order recoverable, but they reach that state through different signals — and the tests assert different status codes to lock that contract in. Both make the "charged but unconfirmed" split reproducible on demand, which is almost impossible against a real processor.

---

## Recovery: the reconciler

`app/app/reconciler.py`. The reconciler is the healing mechanism:

1. Find all orders stuck in `pending`.
2. For each, re-query the gateway by its `idempotency_key` — the durable identifier that survives a lost confirmation.
3. If the gateway confirms a successful charge, write the missing payment row and converge the order to `paid`.
4. If the gateway has no record (404), leave the order alone — there was no charge to heal.

**It is synchronous by design.** It's triggered by an HTTP call to `/reconcile` and completes all healing *before* returning the response — no background worker, no queue. For a learning project this is a deliberate simplification: it makes the behavior trivial to test (no polling needed) while still demonstrating the convergence pattern. In production this would be a background loop, and tests would use a poll-until pattern to assert eventual consistency.

Recovery is **idempotent**: re-running it never issues a second charge, because it only ever *reads* the gateway and writes the missing local record.

Note that the reconciler heals *both* implemented failure modes — the lost confirmation (504) and the ambiguous timeout (502) — through the exact same mechanism. It doesn't care *how* the confirmation was lost; it only cares that a durable `pending` order exists carrying an `idempotency_key` it can re-query. That generality is the point: the recovery path is robust across failure modes, not tailored to one.

---

## The test harness

`tests/conftest.py` plus `tests/helpers/`. The design decisions here are as important as the application code.

**Fixtures and their scopes:**

| Fixture | Scope | Purpose |
|---|---|---|
| `engine` | session | One database engine for the whole run (expensive, created once) |
| `client` | session | One httpx client driving the SUT |
| `db` | function | The engine, handed to helpers that each open their own short-lived connection |
| `clean_ledger` | function, autouse | `TRUNCATE` orders + payments **before** each test |
| `reset_gateway_chaos` | function, autouse | Disarms any leftover chaos **before** each test |
| `idempotency_key` | function | A fresh UUID per test |

**Two design decisions worth understanding:**

**Isolated reads.** The verification helpers (`tests/helpers/db.py`) read through a connection separate from the application's session, and each read opens its own short-lived connection. This guarantees the test sees **committed state** — not a stale or cached view from a session that participated in the writes. This matters acutely in the reconciliation test, which reads the order (`pending`), triggers a write (healing), then reads again (`paid`): if the read connection held a stale snapshot, it would see the wrong state and the test would pass or fail by luck. *Verification reads must begin after the write commits.*

**Truncate before, not after.** Cleanup runs at the *start* of each test, not the end. If a test fails mid-run, its rows are left behind for you to inspect — the evidence isn't destroyed by teardown. Combined with unique keys per test, every test is fully isolated and individually runnable.

**Assertion helpers read like business intent.** `get_order`, `get_payment_by_order`, `order_count_for_key`, `gateway_charge_count(key)` hide the SQL so a test reads as `assert order["status"] == "paid"` rather than raw queries. Note that `gateway_charge_count` is **key-scoped** — it asserts "exactly one charge *for this key*," never "one charge total," so tests don't interfere with each other's accounting.

---

## How the assertion trace works

Every test asserts state **layer by layer, in order** — this is the single most important habit in the suite:

```
1. HTTP response   →  what the SUT claims
2. Gateway record  →  did the money actually move (and how many times)
3. orders row      →  what the ledger says about fulfillment
4. payments row    →  is the payment recorded and consistent
```

A test that only checks the HTTP response is testing almost nothing. The `200` is what the service *claims*; the rows and the gateway record are what's *true*. Keeping both (response *and* ledger) means a test can catch a service that returns `paid` while writing `pending` — a real and dangerous bug class.

---

## How to extend this project

To add a new failure-class test:

1. **Name the risk in one sentence** — what real-world failure are you reproducing?
2. **Decide if you need a new fault mode.** If the scenario requires the gateway to misbehave in a new way, add a mode to `/_chaos` first, verify it manually, then write the test against it.
3. **Write the test in the standard shape** — arrange (arm fault), act (drive over HTTP), assert the trace (response → gateway → orders → payments).
4. **Assert at the data layer**, never the HTTP status alone. Use count assertions (`== 1`) where "exactly one" is the invariant, so duplicates can't hide behind a `.first()`.
5. **Write the reasoning** — a short docstring stating the risk, your hypothesis, and the invariant proven. This articulation is the actual skill the project builds.

The deferred failure classes (webhooks, state-machine integrity, money correctness) are the natural next extensions, and each is described in `SCENARIOS.md` with a sketch of how it would be built. Timeout ambiguity, originally on this list, is now implemented — its test is the model to follow for adding the rest.

---

## The philosophy in one paragraph

You cannot prevent distributed systems from failing between any two steps. What you can do is **persist enough durable state to recover**, build the recovery mechanism, and then **test that the recovery actually works** — asserting against the ledger and the money's real location, not against an HTTP status code. This project is a small, complete demonstration of that discipline applied to the most consequential domain there is: moving money.
