import os
import httpx
from app.models import CheckoutRequest
from fastapi import FastAPI
from sqlalchemy import text
from app.database import engine

GATEWAY_URL = os.getenv("GATEWAY_URL")

app = FastAPI(title = "Order Service")

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
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{GATEWAY_URL}/charge",
            json = request.model_dump()
        )

    return response.json()

@app.get("/_charges")
async def get_charges():
    return {
        "count": len(charges),
        "charges": charges
    }