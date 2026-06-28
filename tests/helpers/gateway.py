import httpx
from tests.conftest import GATEWAY_URL

def gateway_charges_for_key(idempotency_key):
    response = httpx.get(f"{GATEWAY_URL}/_charges")
    response.raise_for_status()
    charges = response.json()["charges"]
    return [
        charge
        for charge in charges
        if charge["idempotency_key"] == idempotency_key
    ]

def gateway_charge_count(idempotency_key):
    return len(gateway_charges_for_key(idempotency_key))