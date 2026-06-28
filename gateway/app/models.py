from pydantic import BaseModel

class ChargeRequest(BaseModel):
    amount: int
    currency: str
    idempotency_key: str