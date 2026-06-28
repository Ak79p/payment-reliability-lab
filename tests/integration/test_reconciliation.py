import httpx

from tests.helpers.db import (
    get_order_by_key,
    get_payment_by_order,
    payment_count_for_order
)
from tests.helpers.gateway import gateway_charge_count

GATEWAY_URL = "http://localhost:8001"


def test_reconcile_charged_but_unconfirmed(
    client,
    db,
    idempotency_key
):
    """
    Risk:
        The payment succeeds but confirmation is lost,
        leaving the customer charged while the order
        remains incomplete.

    Hypothesis:
        Reconciliation converges the order to the
        gateway's authoritative state without
        charging twice.

    Invariant:
        Money moved <=> ledger eventually reflects reality.
    """

    # Arrange
    response = httpx.post(
        f"{GATEWAY_URL}/_chaos",
        json={
            "mode": "lose_confirmation"
        }
    )
    assert response.status_code == 200
    payload = {
        "amount": 1999,
        "currency": "GBP",
        "idempotency_key": idempotency_key
    }

    # Act
    checkout = client.post(
        "/checkout",
        json=payload
    )

    # Broken state
    assert checkout.status_code == 504
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