"""Налаштування з змінних середовища (.env локально, Environment на Render)."""
import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Перша модель – основна, решта – запасні: якщо модель перевантажена (503)
# або вичерпано ліміт (429), запит автоматично йде до наступної.
GEMINI_MODELS = [
    m.strip()
    for m in os.getenv("GEMINI_MODELS", "gemini-3.8-flash,gemini-3.5-flash,gemini-2.5-flash").split(",")
    if m.strip()
]

# Локально – файл SQLite; у хмарі – рядок підключення до Supabase (PostgreSQL).
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./receipts.db")

MAX_IMAGE_MB = float(os.getenv("MAX_IMAGE_MB", "10"))
