from concurrent.futures import ThreadPoolExecutor

from tests.helpers.db import (
    get_order,
    get_payment_by_order,
    order_count_for_key,
    payment_count_for_order
)
from tests.helpers.gateway import gateway_charge_count


def test_sequential_retry(client, db, idempotency_key):
    """
    Risk:
        A client retries the same checkout and accidentally creates
        a second purchase.

    Hypothesis:
        Repeating a checkout with the same idempotency key returns
        the original order instead of creating another purchase.

    Invariant:
        One purchase -> one order -> one payment -> one charge.
    """

    payload = {
        "amount": 1999,
        "currency": "GBP",
        "idempotency_key": idempotency_key
    }

    response_1 = client.post(
        "/checkout",
        json = payload
    )

    response_2 = client.post(
        "/checkout",
        json = payload
    )

    assert response_1.status_code == 200
    assert response_2.status_code == 200

    body_1 = response_1.json()
    body_2 = response_2.json()

    #
    # Both requests represent the same logical purchase.
    #
    assert body_1["order_id"] == body_2["order_id"]

    order_id = body_1["order_id"]

    #
    # Exactly one gateway charge.
    #
    assert gateway_charge_count(idempotency_key) == 1

    #
    # Exactly one order row.
    #
    assert order_count_for_key(
        db,
        idempotency_key
    ) == 1

    order = get_order(
        db,
        order_id
    )

    assert order is not None
    assert order["status"] == "paid"
    assert order["amount"] == 1999
    assert order["currency"] == "GBP"

    #
    # Exactly one payment row.
    #
    assert payment_count_for_order(
        db,
        order_id
    ) == 1

    payment = get_payment_by_order(
        db,
        order_id
    )

    assert payment is not None
    assert payment["status"] == "succeeded"
    assert payment["amount"] == order["amount"]
    assert payment["currency"] == order["currency"]


def test_concurrent_duplicate(client, db, idempotency_key):
    """
    Risk:
        Two identical checkout requests arrive nearly simultaneously
        and create duplicate purchases.

    Hypothesis:
        Concurrent duplicate requests resolve to a single logical purchase.

    Invariant:
        One purchase -> one order -> one payment -> one charge.

    Note:
        This test is deterministic about the business outcome
        (exactly one purchase), but not about which deduplication
        mechanism handled the race (application lookup or database
        uniqueness constraint).
    """

    payload = {
        "amount": 1999,
        "currency": "GBP",
        "idempotency_key": idempotency_key
    }

    def checkout():
        return client.post(
            "/checkout",
            json = payload
        )

    with ThreadPoolExecutor(max_workers = 2) as executor:
        future_1 = executor.submit(checkout)
        future_2 = executor.submit(checkout)

    response_1 = future_1.result()
    response_2 = future_2.result()

    assert response_1.status_code == 200
    assert response_2.status_code == 200

    body_1 = response_1.json()
    body_2 = response_2.json()

    #
    # Both callers receive the same logical purchase.
    #
    assert body_1["order_id"] == body_2["order_id"]

    order_id = body_1["order_id"]

    #
    # Exactly one gateway charge.
    #
    assert gateway_charge_count(idempotency_key) == 1

    #
    # Exactly one order row.
    #
    assert order_count_for_key(
        db,
        idempotency_key
    ) == 1

    order = get_order(
        db,
        order_id
    )

    assert order is not None
    assert order["status"] == "paid"

    #
    # Exactly one payment row.
    #
    assert payment_count_for_order(
        db,
        order_id
    ) == 1

    payment = get_payment_by_order(
        db,
        order_id
    )

    assert payment is not None
    assert payment["status"] == "succeeded"