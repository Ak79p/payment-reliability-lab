from uuid import uuid4
from fastapi import FastAPI, HTTPException
from app.models import ChargeRequest, ChaosRequest
from app.storage import charges

app = FastAPI(title = "Fake Gateway")

chaos = {"mode": None}

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
        "idempotency_key": request.idempotency_key,
        "amount": request.amount,
        "currency": request.currency,
        "status": "succeeded"
    }

    charges[request.idempotency_key] = response
    #
    # Simulate: payment succeeded,
    # confirmation never reached the caller.
    #
    if chaos["mode"] == "lose_confirmation":

        chaos["mode"] = None

        raise HTTPException(
            status_code = 504,
            detail = "Charge succeeded but confirmation was lost."
        )

    return response

@app.post("/_chaos")
async def set_chaos(request: ChaosRequest):
    chaos["mode"] = request.mode

    return {
        "mode": chaos["mode"]
    }

@app.get("/_charges")
async def get_charges():
    return {
        "count": len(charges),
        "charges": list(charges.values())
    }