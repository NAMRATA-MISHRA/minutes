import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# `app/` lives at backend/app — backend root is one level up (where .env and requirements.txt live).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Load env before reading variables. Many people run `uvicorn` from the repo root, so cwd-based
# load_dotenv() would miss backend/.env unless we use explicit paths.
load_dotenv(_BACKEND_ROOT / ".env")
load_dotenv(_BACKEND_ROOT.parent / ".env")


def _env_str(name: str, default: str = "") -> str:
    raw = (os.getenv(name) or default).strip()
    if len(raw) >= 2 and ((raw[0] == raw[-1] == '"') or (raw[0] == raw[-1] == "'")):
        raw = raw[1:-1].strip()
    return raw


def _gemini_api_key() -> str:
    return _env_str("GEMINI_API_KEY") or _env_str("GOOGLE_API_KEY")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = field(default_factory=_gemini_api_key)
    gemini_model: str = field(default_factory=lambda: _env_str("GEMINI_MODEL", "gemini-2.0-flash"))
    upload_dir: str = field(default_factory=lambda: _env_str("UPLOAD_DIR", "uploads"))
    database_path: str = field(default_factory=lambda: _env_str("DATABASE_PATH", "meetings.db"))


settings = Settings()
