"""PracticeMap web application.

Serves the whole product from one process: the score viewer, the upload
endpoint, and the practice sidebar. Run it with

    python -m uvicorn src.app.main:app --reload

and open http://127.0.0.1:8000.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from src.config import PROJECT_ROOT, has_app_credentials, load_env
from src.features.score_viewer.view_model import build_view, client_payload
from src.server.analysis.example import ExampleUnavailable, load_example

load_env()

APP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(APP_DIR / "templates"))
STATIC_DIR = PROJECT_ROOT / "src" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Only the rendered page images are served, not the whole fixtures tree. The
# viewer needs the scan it is annotating and nothing else.
PAGE_IMAGE_DIR = PROJECT_ROOT / "fixtures" / "pages"

app = FastAPI(title="PracticeMap", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if PAGE_IMAGE_DIR.exists():
    app.mount(
        "/fixtures/pages", StaticFiles(directory=str(PAGE_IMAGE_DIR)), name="page-images"
    )

def _script_json(value: object) -> Markup:
    """JSON for embedding inside a <script> element.

    Two things have to be true at once: the template's autoescaping must not
    mangle the quotes, and the data must not be able to close the script tag.
    Escaping the three characters that could start a tag or an entity satisfies
    both, and stays valid JSON. Recognition output is data, never markup, and
    this is the boundary where that is enforced.
    """
    encoded = (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return Markup(encoded)


TEMPLATES.env.filters["tojson_safe"] = _script_json


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


@app.get("/score/example", response_class=HTMLResponse)
def example_score(request: Request) -> HTMLResponse:
    """The prepared example, annotated over its original scan.

    Labelled as the example everywhere it appears. It is never served in place
    of a failed upload: an upload that fails reports its own failure.
    """
    try:
        bundle = load_example()
    except ExampleUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    view = build_view(bundle)
    return TEMPLATES.TemplateResponse(
        request=request,
        name="score.html",
        context={
            "view": view,
            "payload": client_payload(view),
            "live_recognition": has_app_credentials(),
        },
    )
