"""REST API та веб-інтерфейс.

Потік роботи:
  1. POST /api/receipts/parse  – фото → Gemini → JSON чека (ще не зберігається);
  2. користувач перевіряє й за потреби виправляє дані на сторінці;
  3. POST /api/receipts        – збереження в базу;
  4. GET  /api/stats           – аналітика витрат для дашборда.
"""
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import config, gemini
from .db import Item, Receipt, get_session, init_db
from .schemas import (
    CategoryStat, DayStat, ParseResult, ReceiptIn, ReceiptOut, Stats, StoreStat,
)

STATIC = Path(__file__).parent / "static"
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="ЧекРадар",
    description="Облік витрат за фото чеків через Google Gemini API",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------- 1. Розпізнавання ----------

@app.post("/api/receipts/parse", response_model=ParseResult)
async def parse(file: UploadFile = File(..., description="Фото чека")):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Підтримуються лише зображення JPEG, PNG, WEBP або HEIC")
    image = await file.read()
    if len(image) > config.MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(413, f"Файл більший за {config.MAX_IMAGE_MB:g} МБ")

    try:
        receipt, model, seconds = gemini.parse_receipt(image, file.content_type)
    except gemini.GeminiError as e:
        raise HTTPException(502, str(e))

    if not receipt.items:
        raise HTTPException(422, "На фото не знайдено чека або товарів")

    return ParseResult(
        receipt=receipt,
        model=model,
        seconds=round(seconds, 1),
        items_sum=round(sum(i.total for i in receipt.items), 2),
    )


# ---------- 2. Збереження та перегляд ----------

def _to_out(r: Receipt) -> ReceiptOut:
    return ReceiptOut.model_validate(r, from_attributes=True)


@app.post("/api/receipts", response_model=ReceiptOut, status_code=201)
def create_receipt(data: ReceiptIn, db: Session = Depends(get_session)):
    items_sum = round(sum(i.total for i in data.items), 2)
    receipt = Receipt(
        store=data.store,
        purchase_date=data.purchase_date or date.today(),
        currency=data.currency.upper(),
        total=data.total if data.total is not None else items_sum,
        items=[Item(name=i.name, quantity=i.quantity, total=i.total, category=i.category.value)
               for i in data.items],
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return _to_out(receipt)


@app.get("/api/receipts", response_model=list[ReceiptOut])
def list_receipts(db: Session = Depends(get_session)):
    rows = db.scalars(
        select(Receipt).options(selectinload(Receipt.items))
        .order_by(Receipt.purchase_date.desc(), Receipt.id.desc())
    ).all()
    return [_to_out(r) for r in rows]


@app.delete("/api/receipts/{receipt_id}", status_code=204)
def delete_receipt(receipt_id: int, db: Session = Depends(get_session)):
    receipt = db.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(404, "Чек не знайдено")
    db.delete(receipt)
    db.commit()


# ---------- 3. Аналітика ----------

@app.get("/api/stats", response_model=Stats)
def stats(
    date_from: date | None = Query(None, description="Початок періоду"),
    date_to: date | None = Query(None, description="Кінець періоду"),
    db: Session = Depends(get_session),
):
    def period(q):
        if date_from:
            q = q.where(Receipt.purchase_date >= date_from)
        if date_to:
            q = q.where(Receipt.purchase_date <= date_to)
        return q

    total, count = db.execute(
        period(select(func.coalesce(func.sum(Receipt.total), 0), func.count(Receipt.id)))
    ).one()

    by_category = db.execute(
        period(
            select(Item.category, func.sum(Item.total).label("s"))
            .join(Receipt, Item.receipt_id == Receipt.id)
            .group_by(Item.category)
            .order_by(func.sum(Item.total).desc())
        )
    ).all()

    by_day = db.execute(
        period(
            select(Receipt.purchase_date, func.sum(Receipt.total))
            .group_by(Receipt.purchase_date)
            .order_by(Receipt.purchase_date)
        )
    ).all()

    store = func.coalesce(Receipt.store, "Невідомо")
    top_stores = db.execute(
        period(
            select(store, func.sum(Receipt.total), func.count(Receipt.id))
            .group_by(store)
            .order_by(func.sum(Receipt.total).desc())
            .limit(5)
        )
    ).all()

    return Stats(
        total=round(total, 2),
        receipts=count,
        average_receipt=round(total / count, 2) if count else 0,
        by_category=[CategoryStat(category=c, total=round(s, 2)) for c, s in by_category],
        by_day=[DayStat(day=d, total=round(s, 2)) for d, s in by_day if d],
        top_stores=[StoreStat(store=s, total=round(t, 2), receipts=n) for s, t, n in top_stores],
    )
