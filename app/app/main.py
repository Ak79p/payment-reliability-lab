import os
import uuid
import httpx
from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.db import engine, SessionLocal
from app.models import CheckoutRequest
from app.entities import Order, Payment
from app.reconciler import reconcile

GATEWAY_URL = os.getenv("GATEWAY_URL")

app = FastAPI(title="Order Service")


@app.get("/")
async def root():
    return {"service": "order-service"}


@app.get("/health")
async def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/checkout")
async def checkout(request: CheckoutRequest):
    # Application-level pre-check.
    session = SessionLocal()
    try:
        existing = (
            session.query(Order)
            .filter_by(idempotency_key = request.idempotency_key)
            .first()
        )

        if existing:
            return {
                "order_id": str(existing.id),
                "status": existing.status
            }

    finally:
        session.close()

    #
    # Create the order FIRST.
    #
    order_id = uuid.uuid4()

    order = Order(
        id = order_id,
        amount = request.amount,
        currency = request.currency,
        status = "pending",
        idempotency_key = request.idempotency_key
    )

    session = SessionLocal()

    try:
        session.add(order)
        session.commit()

    except IntegrityError:
        session.rollback()

        existing = (
            session.query(Order)
            .filter_by(idempotency_key = request.idempotency_key)
            .first()
        )

        if existing:
            return {
                "order_id": str(existing.id),
                "status": existing.status
            }

        raise

    finally:
        session.close()

    #
    # Charge the customer.
    #
    try:
        async with httpx.AsyncClient() as client:

            response = await client.post(
                f"{GATEWAY_URL}/charge",
                json = request.model_dump(),
                timeout = 5.0
            )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code = 502,
            detail = "Payment outcome unknown; order persisted as pending and will be reconciled."
        )

    #
    # Lost confirmation.
    #
    if response.status_code != 200:

        raise HTTPException(
            status_code = response.status_code,
            detail = response.json()["detail"]
        )

    charge = response.json()

    payment = Payment(
        id = uuid.uuid4(),
        order_id = order_id,
        charge_id = charge["charge_id"],
        amount = request.amount,
        currency = request.currency,
        status = charge["status"]
    )

    session = SessionLocal()

    try:

        order = session.get(Order, order_id)

        order.status = "paid"

        session.add(payment)

        session.commit()

    finally:
        session.close()

    return {
        "order_id": str(order_id),
        "status": "paid"
    }


@app.get("/orders/{order_id}")
async def get_order(order_id: uuid.UUID):
    session = SessionLocal()
    try:
        order = session.get(Order, order_id)
    finally:
        session.close()

    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    return {
        "order_id": str(order.id),
        "amount": order.amount,
        "currency": order.currency,
        "status": order.status,
        "idempotency_key": order.idempotency_key,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }

@app.post("/reconcile")
async def run_reconciler():
    await reconcile()

    return {
        "status": "completed"
    }