from datetime import datetime
import uuid
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid = True),
        primary_key = True,
        default = uuid.uuid4
    )

    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    # status values: 'paid' | 'refunded' | 'failed'  — CHECK constraint deferred
    status: Mapped[str] = mapped_column(String(20))

    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        unique = True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default = func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default = func.now(),
        onupdate = func.now()
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid = True),
        primary_key = True,
        default = uuid.uuid4
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid = True),
        ForeignKey("orders.id")
    )

    charge_id: Mapped[str] = mapped_column(
        String(255),
        unique = True
    )

    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    # status values: 'succeeded' | 'failed' | 'refunded'  — CHECK constraint deferred
    status: Mapped[str] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default = func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default = func.now(),
        onupdate = func.now()
    )