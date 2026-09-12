"""PracticeMap web application.

Serves the whole product from one process: the score viewer, the upload
endpoint, and the practice sidebar. Run it with

    python -m uvicorn src.app.main:app --reload

and open http://127.0.0.1:8000.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import PROJECT_ROOT, has_app_credentials, load_env

load_env()

APP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(APP_DIR / "templates"))
STATIC_DIR = PROJECT_ROOT / "src" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PracticeMap", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health")
def health() -> dict:
    """Liveness plus an honest statement of what this instance can do.

    `live_recognition` reflects only PRACTICEMAP_ANTHROPIC_API_KEY. An ambient
    ANTHROPIC_API_KEY deliberately does not count: the app must not look
    credentialed when its own key is unset.
    """
    return {
        "status": "ok",
        "live_recognition": has_app_credentials(),
        "example_mode": True,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request=request,
        name="index.html",
        context={"live_recognition": has_app_credentials()},
    )
