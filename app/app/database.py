from sqlalchemy import create_engine

DATABASE_URL = "postgresql+psycopg://postgres:postgres@postgres:5432/payments"

engine = create_engine(
    url = DATABASE_URL,
    echo = True
)