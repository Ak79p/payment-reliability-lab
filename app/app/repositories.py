from app.db import SessionLocal
from app.entities import Order, Payment

class OrderRepository:

    def create_order(self, order: Order) -> None:
        session = SessionLocal()

        try:
            session.add(order)
            session.commit()

        finally:
            session.close()


class PaymentRepository:

    def create_payment(self, payment: Payment) -> None:
        session = SessionLocal()

        try:
            session.add(payment)
            session.commit()

        finally:
            session.close()