import asyncio
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

    elif chaos["mode"] == "timeout_ambiguous":
        # Charge is already recorded above. Hang long enough that the
        # caller's HTTP client times out — no status code is ever sent.
        # The caller cannot distinguish "charge never happened" from
        # "charge happened, response was lost in transit."
        chaos["mode"] = None

        await asyncio.sleep(10)

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
    
@app.get("/charge/{idempotency_key}")
async def get_charge(idempotency_key: str):

    charge = charges.get(idempotency_key)

    if charge is None:
        raise HTTPException(
            status_code = 404,
            detail = "Charge not found."
        )

    return charge