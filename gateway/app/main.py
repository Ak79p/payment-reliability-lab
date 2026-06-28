from uuid import uuid4
from fastapi import FastAPI
from app.models import ChargeRequest

app = FastAPI(title = "Fake Gateway")

charges = {}

@app.get("/")
async def root():
    return {"service": "fake-gateway"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/charge")
async def charge(request: ChargeRequest):
    if request.idempotency_key in charges:
        return charges[request.idempotency_key]

    response = {
        "charge_id": str(uuid4()),
        "status": "succeeded"
    }

    charges[request.idempotency_key] = response

    return response