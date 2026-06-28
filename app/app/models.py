from pydantic import BaseModel

class CheckoutRequest(BaseModel):
    amount: int
    currency: str
    idempotency_key: str