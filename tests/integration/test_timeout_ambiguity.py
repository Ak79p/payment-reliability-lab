import httpx

from tests.helpers.db import (
    get_order_by_key,
    get_payment_by_order,
    payment_count_for_order
)
from tests.helpers.gateway import gateway_charge_count

GATEWAY_URL = "http://localhost:8001"


def test_timeout_ambiguous_charge_is_reconciled(
    client,
    db,
    idempotency_key
):
    """
    Risk:
        A network timeout leaves the caller unable to tell whether the
        charge happened; treating that ambiguity as failure would strand
        a real charge — the customer has been debited but no order is
        ever fulfilled.

    Hypothesis:
        The service returns a deliberate ambiguity signal (502) and
        leaves the order pending rather than marking it failed; the
        reconciler later converges it to paid against the gateway's true
        state without issuing a second charge.

    Invariant:
        An ambiguous outcome is recoverable, not a failure —
        money moved <=> the ledger eventually reflects reality.
    """

    # Arrange
    response = httpx.post(
        f"{GATEWAY_URL}/_chaos",
        json={
            "mode": "timeout_ambiguous"
        }
    )
    assert response.status_code == 200
    payload = {
        "amount": 1999,
        "currency": "GBP",
        "idempotency_key": idempotency_key
    }

    # Act — blocks for ~5 s while the order service's client timeout fires
    checkout = client.post(
        "/checkout",
        json=payload,
        timeout=15.0
    )

    # Ambiguous state
    assert checkout.status_code == 502
    assert gateway_charge_count(idempotency_key) == 1
    order = get_order_by_key(
        db,
        idempotency_key
    )
    assert order is not None
    assert order["status"] == "pending"
    assert payment_count_for_order(
        db,
        order["id"]
    ) == 0

    # Heal
    reconcile = client.post("/reconcile")
    assert reconcile.status_code == 200

    # Healed state
    order = get_order_by_key(
        db,
        idempotency_key
    )
    assert order["status"] == "paid"
    assert payment_count_for_order(
        db,
        order["id"]
    ) == 1
    payment = get_payment_by_order(
        db,
        order["id"]
    )
    assert payment["status"] == "succeeded"
    assert gateway_charge_count(idempotency_key) == 1
