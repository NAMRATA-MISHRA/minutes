"""
ASGI entry for hosts that run from the repository root (e.g. Render with an empty Root Directory).

Use: uvicorn server:app --host 0.0.0.0 --port $PORT

If your host sets Root Directory to `backend`, use `uvicorn app.main:app` instead.
"""
from pathlib import Path
import sys

_backend = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(_backend))

from app.main import app  # noqa: E402

__all__ = ["app"]
