import os
from uuid import uuid4
import pytest
import httpx
from sqlalchemy import create_engine, text

ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://localhost:8000")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8001")
DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/payments")

# --- Session-scoped: expensive, created once for the whole run ---

@pytest.fixture(scope = "session")
def engine():
    """
    Verification engine.
    Separate from the application's engine so the test harness
    never shares the application's session.
    """
    engine = create_engine(
        url = DATABASE_URL,
        echo = False
    )
    yield engine
    engine.dispose()

@pytest.fixture(scope = "session")
def client():
    """
    HTTP client for driving the Order Service.
    """
    with httpx.Client(base_url = ORDER_SERVICE_URL) as client:
        yield client

# --- Function-scoped: fresh per test ---

@pytest.fixture(scope = "function")
def db(engine):
    """
    Fresh connection for every test.
    """
    return engine

@pytest.fixture(scope = "function", autouse = True)
def clean_ledger(engine):
    """
    Start every test with a clean ledger.
    """
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE TABLE payments, orders CASCADE;")
        )
    yield

@pytest.fixture
def idempotency_key():
    """
    Unique key for every test.
    """
    return str(uuid4())