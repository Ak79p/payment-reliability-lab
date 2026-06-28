from sqlalchemy import text


def get_order(engine, order_id):
    """
    Read the committed order row.
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
    Read the committed payment row.
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