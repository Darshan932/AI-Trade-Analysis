import os
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    # SQLite by default (zero setup). For MySQL set e.g.
    # DATABASE_URL=mysql://root:password@localhost:3306/trade_ai
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'trade_ai.db')}")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge_base")
    SAMPLE_CSV = os.path.join(BASE_DIR, "sample_data", "sample_ohlc.csv")
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024          # 8 MB upload limit
    ALLOWED_IMAGES = {"png", "jpg", "jpeg", "webp"}
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
