from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine

app = FastAPI(title = "Order Service")

@app.get("/")
async def root():
    return {"service": "order-service"}

@app.get("/health")
async def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return {"status": "ok"}

@app.get("/_charges")
async def get_charges():
    return {
        "count": len(charges),
        "charges": charges
    }