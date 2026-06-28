import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/payments"
)

engine = create_engine(
    url = DATABASE_URL,
    echo = True
)

SessionLocal = sessionmaker(
    bind = engine,
    autoflush = False,
    autocommit = False,
    expire_on_commit = False
)