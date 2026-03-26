import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    upload_dir: str = os.getenv("UPLOAD_DIR", "uploads")
    database_path: str = os.getenv("DATABASE_PATH", "meetings.db")


settings = Settings()
