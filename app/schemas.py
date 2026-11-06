"""Схеми даних.

`ParsedReceipt` передається в Gemini як `response_schema`: модель зобов'язана
повернути JSON саме такої структури. Тому в ній немає значень за замовчуванням
(Gemini API їх не підтримує) – необов'язкові поля просто можуть бути null.
"""
from datetime import date as Date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Category(str, Enum):
    groceries = "Продукти"
    drinks = "Напої"
    sweets = "Солодощі та снеки"
    alcohol = "Алкоголь"
    household = "Побутова хімія"
    hygiene = "Гігієна та косметика"
    pharmacy = "Аптека"
    cafe = "Кафе та ресторани"
    fuel = "Пальне та транспорт"
    clothes = "Одяг та взуття"
    electronics = "Техніка"
    other = "Інше"


class ParsedItem(BaseModel):
    name: str = Field(description="Назва товару, як у чеку, але без скорочень, якщо їх легко розшифрувати")
    quantity: float = Field(description="Кількість або вага (кг). Якщо не вказано – 1")
    total: float = Field(description="Сума за рядок у валюті чека (з урахуванням знижки на цей товар)")
    category: Category = Field(description="Категорія витрат")


class ParsedReceipt(BaseModel):
    store: Optional[str] = Field(description="Назва магазину чи закладу")
    purchase_date: Optional[str] = Field(description="Дата покупки у форматі YYYY-MM-DD")
    currency: str = Field(description="Код валюти ISO 4217, напр. UAH")
    total: Optional[float] = Field(description="Підсумкова сума до сплати з чека")
    items: list[ParsedItem]


# ---- Схеми REST API (те, що надсилає/отримує фронтенд) ----

class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: float = Field(default=1, gt=0)
    total: float
    category: Category = Category.other


class ReceiptIn(BaseModel):
    store: Optional[str] = Field(default=None, max_length=200)
    purchase_date: Optional[Date] = None
    currency: str = Field(default="UAH", min_length=3, max_length=3)
    total: Optional[float] = None
    items: list[ItemIn] = Field(min_length=1)


class ItemOut(ItemIn):
    id: int


class ReceiptOut(BaseModel):
    id: int
    store: Optional[str]
    purchase_date: Optional[Date]
    currency: str
    total: float
    items: list[ItemOut]


class ParseResult(BaseModel):
    receipt: ParsedReceipt
    model: str = Field(description="Яка модель Gemini розпізнала чек")
    seconds: float = Field(description="Скільки тривало розпізнавання")
    items_sum: float = Field(description="Сума рядків – для звірки з підсумком чека")


class CategoryStat(BaseModel):
    category: str
    total: float


class DayStat(BaseModel):
    day: Date
    total: float


class StoreStat(BaseModel):
    store: str
    total: float
    receipts: int


class Stats(BaseModel):
    total: float
    receipts: int
    average_receipt: float
    by_category: list[CategoryStat]
    by_day: list[DayStat]
    top_stores: list[StoreStat]
