from tests.helpers.db import get_order, get_payment_by_order
from tests.helpers.gateway import gateway_charge_count


def test_checkout_happy_path(client, db, idempotency_key):
    """
    Risk:
        The payment gateway reports success but the order service
        fails to persist the transaction correctly.

    Hypothesis:
        A successful checkout creates exactly one gateway charge,
        one paid order and one succeeded payment.

    Invariant:
        Money charged <=> order recorded, exactly once.
    """

    # Act
    response = client.post(
        "/checkout",
        json = {
            "amount": 1999,
            "currency": "GBP",
            "idempotency_key": idempotency_key
        }
    )

    # Trace 1 — HTTP response
    assert response.status_code == 200

    body = response.json()

    assert "order_id" in body
    assert body["status"] == "paid"

    order_id = body["order_id"]

    # Trace 2 — Gateway state
    assert gateway_charge_count(idempotency_key) == 1

    # Trace 3 — Order ledger
    order = get_order(db, order_id)

    assert order is not None
    assert order["status"] == "paid"
    assert order["amount"] == 1999
    assert order["currency"] == "GBP"
    assert order["idempotency_key"] == idempotency_key

    # Trace 4 — Payment ledger
    payment = get_payment_by_order(db, order_id)

    assert payment is not None
    assert payment["status"] == "succeeded"
    assert payment["amount"] == order["amount"]
    assert payment["currency"] == order["currency"]