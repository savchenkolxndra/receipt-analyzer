"""Розпізнавання чека через Google Gemini API (хмарний AI-сервіс).

Одним запитом модель:
  1) читає фото (OCR),
  2) розбирає текст на товари й суми,
  3) відносить кожен товар до категорії,
і повертає JSON строго за схемою ParsedReceipt.
"""
import time

from google import genai
from google.genai import errors, types

from . import config
from .schemas import ParsedReceipt

PROMPT = """Ти – система обліку витрат. На фото – касовий чек.
Витягни з нього дані:
- store: назва магазину/закладу (без юридичної форми на кшталт ТОВ, ФОП, якщо є торгова назва);
- purchase_date: дата покупки у форматі YYYY-MM-DD;
- currency: валюта (для українських чеків – UAH);
- total: підсумок «СУМА» / «ДО СПЛАТИ»;
- items: кожна товарна позиція окремо:
    name – зрозуміла назва українською (розшифруй очевидні скорочення, напр. «МОЛ.ПРОСТОКВ 2,5% 0,9Л» → «Молоко Простоквашино 2,5% 0,9 л»),
    quantity – кількість або вага,
    total – сума за рядок з урахуванням знижки на цю позицію,
    category – одна з дозволених категорій.
Не додавай рядки ПДВ, решту, готівку, картку, бонуси як товари.
Якщо значення неможливо прочитати – поверни null. Нічого не вигадуй.
Якщо на фото не чек – поверни порожній список items."""

RETRYABLE = {429, 500, 503}


class GeminiError(RuntimeError):
    pass


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise GeminiError("Не задано GEMINI_API_KEY (див. .env.example)")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def parse_receipt(image: bytes, mime_type: str) -> tuple[ParsedReceipt, str, float]:
    """Повертає (розпізнаний чек, назва моделі, час у секундах)."""
    client = _get_client()
    last_error: Exception | None = None
    start = time.perf_counter()

    for model in config.GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[types.Part.from_bytes(data=image, mime_type=mime_type), PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ParsedReceipt,
                    temperature=0,
                ),
            )
            receipt = response.parsed
            if receipt is None:  # про всяк випадок – розбираємо текст вручну
                receipt = ParsedReceipt.model_validate_json(response.text)
            return receipt, model, time.perf_counter() - start
        except errors.APIError as e:
            last_error = e
            if e.code in RETRYABLE:
                continue  # модель перевантажена – пробуємо запасну
            raise GeminiError(f"Gemini API: {e.code} {e.message}") from e

    raise GeminiError(f"Усі моделі недоступні, остання помилка: {last_error}")
