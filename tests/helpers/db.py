from sqlalchemy import text


def get_order(engine, order_id):
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
                "order_id": order_id
            }
        )

        return result.mappings().first()


def get_order_by_key(engine, idempotency_key):
    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT *
                FROM orders
                WHERE idempotency_key = :idempotency_key
                """
            ),
            {
                "idempotency_key": idempotency_key
            }
        )

        return result.mappings().first()


def order_count_for_key(engine, idempotency_key):
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


def get_payment_by_order(engine, order_id):
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
                "order_id": order_id
            }
        )

        return result.mappings().first()


def payment_count_for_order(engine, order_id):
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
                "order_id": order_id
            }
        )

        return result.scalar_one()