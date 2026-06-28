# Incident Playbook

Runbooks for known failure modes in the Payment Reliability Lab — the symptom an operator sees, where to look, the root cause, how the system recovers, and the test that proves it.

---

## Incident: Customer charged, order shows unpaid

### Symptom

A customer reports that their card was charged, but the application shows the order stuck as `pending`.

### Evidence trail

- The payment gateway's `/_charges` endpoint shows a successful charge.
- The `orders` table contains the order with status `pending`.
- The `payments` table contains no payment record for that order.

Money moved, but the application's ledger has not yet reflected reality.

### Root cause

Checkout persists the order as `pending` before calling the payment gateway and commits that database transaction. It then calls the gateway to perform the charge.

If the gateway successfully charges the customer but the confirmation is lost (simulated by the `lose_confirmation` chaos mode returning HTTP 504), the second database transaction — which inserts the payment record and updates the order to `paid` — never executes.

The inconsistency exists in the window between those two committed database transactions.

### Recovery

The reconciler scans for pending orders and re-queries the payment gateway using the durable `idempotency_key`. If the gateway reports that the charge already succeeded, the reconciler creates the missing payment record and updates the order to `paid`. Recovery is idempotent and never issues a second charge.

### Test that proves recovery

`test_reconcile_charged_but_unconfirmed`

The test:

1. Arms the lost-confirmation chaos mode.
2. Performs checkout.
3. Verifies the inconsistent state:
   - gateway charge exists,
   - order is `pending`,
   - no payment record exists.
4. Executes reconciliation.
5. Verifies convergence:
   - order becomes `paid`,
   - exactly one payment record exists,
   - gateway charge count remains 1.

### Invariant

Money moved ⇔ the ledger eventually reflects reality.
