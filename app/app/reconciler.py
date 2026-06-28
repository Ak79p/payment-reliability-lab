import os
import uuid
import httpx
from app.db import SessionLocal
from app.entities import Order, Payment

GATEWAY_URL = os.getenv("GATEWAY_URL")

async def reconcile():
    """
    Heal pending orders by querying the payment gateway.
    """
    session = SessionLocal()

    try:

        pending_orders = (
            session.query(Order)
            .filter_by(status = "pending")
            .all()
        )

        async with httpx.AsyncClient() as client:

            for order in pending_orders:

                response = await client.get(
                    f"{GATEWAY_URL}/charge/{order.idempotency_key}"
                )

                if response.status_code != 200:
                    continue

                charge = response.json()

                payment = Payment(
                    id = uuid.uuid4(),
                    order_id = order.id,
                    charge_id = charge["charge_id"],
                    amount = charge["amount"],
                    currency = charge["currency"],
                    status = charge["status"]
                )

                session.add(payment)

                order.status = "paid"

            session.commit()

    finally:
        session.close()