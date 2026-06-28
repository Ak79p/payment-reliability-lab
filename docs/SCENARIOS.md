# Failure Scenarios

This project exists to test the seam between **charging money** and **recording that you charged it** — the place real payment systems break. A `200 OK` proves nothing here; every scenario is verified against the database ledger and the gateway's own record, never the HTTP response alone.

The system is organized around **six failure classes**. Four are implemented with real, passing tests. Two are deliberately scoped out and documented as future work — the schema already provisions for them.

---

## Implemented (with passing tests)

### 1. Idempotency — "a retry is not a second purchase"

**The risk.** A client submits a checkout, the response is slow or lost, and the client retries. Or two identical requests race each other. Either way, the customer intended *one* purchase. A naive system charges them twice.

**What's tested.**
- **Sequential retry** (`test_sequential_retry`) — the same `idempotency_key` submitted twice returns the *same* order, one gateway charge, one order row, one payment row.
- **Concurrent duplicate** (`test_concurrent_duplicate`) — two identical requests fired simultaneously (via a thread pool) still resolve to one order, one charge.

**The lesson.** The HTTP status lies; the row count is the truth. The application performs a pre-check for an existing key, but the real guarantee is the **`UNIQUE` constraint on `idempotency_key` at the database level** — under true concurrency, both requests can pass the pre-check before either commits, and the database constraint is what stops the second insert. The pre-check is an optimization; the constraint is the backstop.

**The invariant.** One purchase → one order → one payment → one charge.

---

### 2. Dual-write reconciliation — "the paid-but-declined problem" *(flagship)*

**The risk.** This is the scenario the whole project is built around. The gateway charges the customer successfully, but the confirmation never reaches the order service. The money has moved; the application doesn't know. The customer sees "declined" while their card statement says otherwise.

**What's tested.** `test_reconcile_charged_but_unconfirmed` arms a fault that makes the charge succeed but loses the confirmation, then proves both halves of the story:
- **The broken state** — the gateway shows a successful charge, the order is stuck `pending`, and *zero* payment rows exist. This is the bug exactly as the customer experiences it.
- **The recovery** — after the reconciler runs, the order converges to `paid`, the missing payment row is written from the gateway's authoritative record, and the gateway charge count is *still one* (healing must never re-charge).

**The lesson.** You don't prevent the crash — distributed systems fail between any two steps. You **design for recovery and test the recovery**. The order is persisted as `pending` *before* the charge precisely so that a durable record exists to reconcile against. No pre-persisted order, no recovery.

**The invariant.** Money moved ⟺ the ledger eventually reflects reality.

> A full incident write-up of this scenario — symptom, evidence trail, root cause, recovery, and the catching test — lives in [`INCIDENT_PLAYBOOK.md`](./INCIDENT_PLAYBOOK.md).

---

### 3. Timeout ambiguity — "ambiguous is not the same as failed"

**The risk.** A network timeout leaves the caller with no signal at all — the TCP connection closes without returning any status code. Unlike the `lose_confirmation` case, which returns a definitive 504 (the gateway explicitly says "I did it but confirmation was lost"), a timeout is genuinely uninformative: the charge may have succeeded, or it may never have started. Treating this as a confirmed failure risks stranding a real charge — the customer is debited, no order is ever fulfilled.

**What's tested.** `test_timeout_ambiguous_charge_is_reconciled` arms the `timeout_ambiguous` chaos mode, which records the charge in the gateway's store and then hangs until the order service's client timeout fires. The test proves both halves:
- **The ambiguous state** — the checkout call returns **502** (the deliberate ambiguity signal, distinct from `lose_confirmation`'s 504), the gateway shows one charge, the order is `pending`, and zero payment rows exist. The order is not marked failed.
- **The recovery** — after the reconciler runs, the order converges to `paid`, the payment row is written from the gateway's record, and the gateway charge count is still one.

**The lesson.** The 502-vs-504 distinction is load-bearing. 504 means "the gateway told me it failed" — a definitive signal the service can propagate. 502 means "I don't know what happened" — the only honest response is to leave the order in a recoverable state and let the reconciler determine truth from the gateway. Collapsing both into the same error code or the same exception handler would destroy the distinction. An ambiguous timeout is not a failure; it is a deferred decision.

**The invariant.** An ambiguous outcome is recoverable, not a failure — money moved ⟺ the ledger eventually reflects reality.

---

## Scoped out — designed, deliberately deferred

These are real failure classes a complete payment platform must handle. They are **out of scope by design**, not by oversight: they introduce a separate async-eventing subsystem whose testing surface is a different project's worth of work. Scoping to one coherent mechanism — a durable record plus convergence to truth — and testing it thoroughly beats scattering shallow coverage across six classes. The `outbox` and `webhook_events` tables are already in the schema to receive this work.

### 4. Webhooks — async confirmation

How it would be built: an event model with a `webhook_events` table keyed on the gateway's `event_id` (a `UNIQUE` constraint giving at-most-once processing — the same idempotency idea as the order key, applied to events); signature verification to reject forged deliveries; and a documented winner rule for conflicting events (e.g. success-after-cancel). Tests would assert at the data layer with a poll-until pattern, since webhook processing is genuinely asynchronous.

### 5. State-machine integrity

How it would be built: an explicit order state machine with illegal transitions rejected (a `paid` order cannot silently return to `pending`; a terminal `failed` order cannot drop a late success on the floor). Enforced with a `CHECK` constraint or a transition guard, with a parametrized test asserting every legal transition succeeds and every illegal one is refused.

### 6. Money correctness

How it would be built: amounts are already stored as integer **minor units** (no floats, no rounding drift). Tests would extend this to mismatch detection (order amount vs. payment amount, currency mismatch), partial refunds with correct arithmetic, and over-refund rejection.

---

## How to read the test suite

Every test follows the same shape, and it's worth internalizing because it's the discipline that makes the suite trustworthy:

1. **Arrange** — set up state, optionally arm a fault via the gateway's chaos endpoint.
2. **Act** — drive the system under test over HTTP.
3. **Assert the trace** — verify state at each layer in order: the HTTP response, then the gateway's own record, then the `orders` row, then the `payments` row.

The assertions read against **committed database state and the gateway's record — never the HTTP status code alone**. That single principle is what separates testing a payment system from testing that an endpoint returns 200.
