"""Тести API. Виклик Gemini замінено заглушкою – ключ і інтернет не потрібні."""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")

import pytest
from fastapi.testclient import TestClient

from app import gemini, main
from app.schemas import ParsedItem, ParsedReceipt

FAKE = ParsedReceipt(
    store="Сільпо",
    purchase_date="2026-10-28",
    currency="UAH",
    total=187.40,
    items=[
        ParsedItem(name="Молоко 2,5% 0,9 л", quantity=1, total=42.90, category="Продукти"),
        ParsedItem(name="Хліб житній", quantity=1, total=31.50, category="Продукти"),
        ParsedItem(name="Сік апельсиновий 1 л", quantity=1, total=68.00, category="Напої"),
        ParsedItem(name="Шоколад молочний", quantity=1, total=45.00, category="Солодощі та снеки"),
    ],
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(gemini, "parse_receipt", lambda image, mime: (FAKE, "stub-model", 0.1))
    with TestClient(main.app) as c:
        yield c


def test_parse_returns_receipt(client):
    r = client.post("/api/receipts/parse", files={"file": ("check.jpg", b"fake", "image/jpeg")})
    assert r.status_code == 200
    data = r.json()
    assert data["receipt"]["store"] == "Сільпо"
    assert len(data["receipt"]["items"]) == 4
    assert data["items_sum"] == 187.40


def test_parse_rejects_non_image(client):
    r = client.post("/api/receipts/parse", files={"file": ("doc.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 415


def test_save_and_stats(client):
    body = FAKE.model_dump(mode="json")
    r = client.post("/api/receipts", json=body)
    assert r.status_code == 201
    rid = r.json()["id"]

    stats = client.get("/api/stats").json()
    assert stats["receipts"] >= 1
    cats = {c["category"]: c["total"] for c in stats["by_category"]}
    assert cats["Продукти"] >= 74.40
    assert stats["top_stores"][0]["store"] == "Сільпо"

    # фільтр за періодом, у який чек не потрапляє
    empty = client.get("/api/stats", params={"date_from": "2030-01-01"}).json()
    assert empty["receipts"] == 0

    assert client.delete(f"/api/receipts/{rid}").status_code == 204
    assert client.delete(f"/api/receipts/{rid}").status_code == 404


def test_save_requires_items(client):
    r = client.post("/api/receipts", json={"store": "X", "items": []})
    assert r.status_code == 422
