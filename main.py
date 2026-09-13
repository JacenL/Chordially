"""Vercel entrypoint.

Vercel's Python runtime looks for a top-level ``app`` in ``main.py`` at the
project root; the application itself lives in ``src/app/main.py``. This shim
only re-exports it. Local development is unchanged:

    python -m uvicorn src.app.main:app --reload
"""

from src.app.main import app

__all__ = ["app"]
