"""База даних: SQLite локально або PostgreSQL у хмарі (Supabase).

Один і той самий код працює з обома – різниця лише в DATABASE_URL.
"""
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from . import config


def _normalize(url: str) -> str:
    # Supabase дає рядок postgresql://..., а SQLAlchemy потрібен драйвер psycopg 3
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


url = _normalize(config.DATABASE_URL)
engine = create_engine(
    url,
    connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    store: Mapped[str | None] = mapped_column(String(200))
    purchase_date: Mapped[date | None] = mapped_column(Date, index=True)
    currency: Mapped[str] = mapped_column(String(3), default="UAH")
    total: Mapped[float] = mapped_column(Float)

    items: Mapped[list["Item"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", order_by="Item.id"
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[float] = mapped_column(Float, default=1)
    total: Mapped[float] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(50), index=True)

    receipt: Mapped[Receipt] = relationship(back_populates="items")


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session():
    with SessionLocal() as session:
        yield session
