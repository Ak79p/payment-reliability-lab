from sqlalchemy import text


def get_order(engine, order_id):
    """
    Return the committed order row.
    """

    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT *
                FROM orders
                WHERE id = :order_id
                """
            ),
            {
                "order_id": str(order_id)
            }
        )

        return result.mappings().first()


def get_payment_by_order(engine, order_id):
    """
    Return the committed payment row.
    """

    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT *
                FROM payments
                WHERE order_id = :order_id
                """
            ),
            {
                "order_id": str(order_id)
            }
        )

        return result.mappings().first()


def order_count_for_key(engine, idempotency_key):
    """
    Return the number of orders for an idempotency key.
    """

    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM orders
                WHERE idempotency_key = :idempotency_key
                """
            ),
            {
                "idempotency_key": idempotency_key
            }
        )

        return result.scalar_one()


def payment_count_for_order(engine, order_id):
    """
    Return the number of payments for an order.
    """

    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM payments
                WHERE order_id = :order_id
                """
            ),
            {
                "order_id": str(order_id)
            }
        )

        return result.scalar_one()