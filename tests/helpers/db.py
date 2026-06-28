from sqlalchemy import text

def get_order(db, order_id):
    result = db.execute(
        text(
            """
            SELECT *
            FROM orders
            WHERE id = :order_id
            """
        ),
        {"order_id": str(order_id)}
    )
    return result.mappings().first()

def get_payment_by_order(db, order_id):
    result = db.execute(
        text(
            """
            SELECT *
            FROM payments
            WHERE order_id = :order_id
            """
        ),
        {"order_id": str(order_id)}
    )
    return result.mappings().first()