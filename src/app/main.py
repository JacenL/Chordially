"""Chordially web application.

Serves the whole product from one process: the score viewer, the upload
endpoint, and the practice sidebar. Run it with

    python -m uvicorn src.app.main:app --reload

and open http://127.0.0.1:8000.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from src.config import PROJECT_ROOT, has_app_credentials, load_env
from src.features.difficulty.rubric import DEFAULT_TEMPO_BPM
from src.features.practice.coach import PassageNotFound, build_guidance
from src.features.score_viewer.view_model import build_view, client_payload
from src.server.recognition.audiveris_source import is_available as audiveris_available
from src.server.analysis import jobs
from src.server.analysis import upload as upload_mod
from src.server.analysis.example import ExampleUnavailable, load_example
from src.features.segmentation.edit import EditRefused, merge_phrase, split_phrase
from src.features.segmentation.section_edit import (
    merge_section,
    reset_sections,
    split_section,
)
from src.server.analysis import store
from src.server.analysis.recompute import parse_tempo, retune

load_env()

APP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(APP_DIR / "templates"))
STATIC_DIR = PROJECT_ROOT / "src" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Only the rendered page images are served, not the whole fixtures tree. The
# viewer needs the scan it is annotating and nothing else.
PAGE_IMAGE_DIR = PROJECT_ROOT / "fixtures" / "pages"

app = FastAPI(title="Chordially", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if PAGE_IMAGE_DIR.exists():
    app.mount(
        "/fixtures/pages", StaticFiles(directory=str(PAGE_IMAGE_DIR)), name="page-images"
    )

# Rendered pages from uploads. Under work/, which git ignores: an uploaded score
# belongs to the user and is never committed.
upload_mod.PAGE_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/uploads/pages", StaticFiles(directory=str(upload_mod.PAGE_DIR)), name="upload-pages"
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
        context={"audiveris_available": audiveris_available()},
    )


@app.post("/upload")
async def upload(file: UploadFile) -> dict:
    """Accept a scan and start analyzing that actual file.

    Returns a job id immediately. The analysis runs in the background and the
    page polls for its stage, because a warm cache finishes in seconds and a
    cold one takes minutes, and holding the request open for either is wrong.
    """
    data = await file.read()
    try:
        upload_mod.validate(data, file.filename or "", file.content_type)
    except upload_mod.UploadRejected as exc:
        # 415 rather than 400: the file was received intact and understood, it
        # is simply not something this build can read. The recovery action
        # matters more than the code.
        raise HTTPException(
            status_code=415, detail={"error": exc.message, "recovery": exc.recovery}
        ) from exc

    job = jobs.start(data, file.filename or "upload", file.content_type)
    return job.as_dict()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such analysis job.")
    return job.as_dict()


def _bundle_for(score_id: str):
    """Resolve a score id to its analysis: an edited copy if one exists.

    Edits win over the inferred segmentation, which is the point of making
    them. Everything downstream -- the viewer, the practice endpoint -- reads
    through here, so there is no path that renders the original after an edit.
    """
    edited = store.get(score_id)
    if edited is not None:
        return edited
    if score_id == "example":
        return load_example()
    bundle = jobs.get_bundle(score_id)
    if bundle is None:
        raise HTTPException(
            status_code=404,
            detail="That analysis is no longer available. Upload the file again.",
        )
    return bundle


def _apply_edit(score_id: str, operation) -> dict:
    """Run one phrase edit and keep the result for later requests."""
    try:
        source = _bundle_for(score_id)
    except ExampleUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    working = store.seed(score_id, source)
    phrases = [p for p in working.phrases if p.level == "phrase"]
    try:
        edited = operation(working.score, phrases)
    except EditRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # Trouble spots are derived from ratings and phrase membership, so the old
    # ones are dropped here and rebuilt by the next retune rather than left
    # pointing at phrases that no longer exist.
    working.phrases = edited
    store.put(score_id, working)
    return {"ok": True, "phrases": len(edited)}


@app.post("/api/phrases/{score_id}/split")
def split(score_id: str, phrase_id: str, at_measure_id: str) -> dict:
    """Begin a new phrase at the given measure."""
    return _apply_edit(
        score_id,
        lambda score, phrases: split_phrase(score, phrases, phrase_id, at_measure_id),
    )


@app.post("/api/phrases/{score_id}/merge")
def merge(score_id: str, phrase_id: str) -> dict:
    """Join this phrase to the one after it."""
    return _apply_edit(
        score_id, lambda score, phrases: merge_phrase(score, phrases, phrase_id)
    )


@app.post("/api/phrases/{score_id}/reset")
def reset_edits(score_id: str) -> dict:
    """Discard edits and go back to the inferred segmentation."""
    return {"ok": True, "had_edits": store.clear(score_id)}


def _apply_section_edit(score_id: str, operation) -> dict:
    """Run one section edit and keep the result for later requests.

    Section edits are recorded as measure-keyed decisions rather than as
    sections, because sections are re-derived on every request -- see
    `src/features/segmentation/section_edit.py`.
    """
    try:
        source = _bundle_for(score_id)
    except ExampleUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    working = store.seed(score_id, source)
    try:
        operation(working)
    except EditRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    store.put(score_id, working)
    return {
        "ok": True,
        "starts": list(working.section_edits.starts),
        "joins": list(working.section_edits.joins),
    }


@app.post("/api/sections/{score_id}/split")
def split_passage(score_id: str, at_measure_id: str) -> dict:
    """Begin a new practice section at this measure."""
    return _apply_section_edit(score_id, lambda b: split_section(b, at_measure_id))


@app.post("/api/sections/{score_id}/merge")
def merge_passage(score_id: str, section_id: str) -> dict:
    """Join this practice section to the one after it."""
    return _apply_section_edit(score_id, lambda b: merge_section(b, section_id))


@app.post("/api/sections/{score_id}/reset")
def reset_passages(score_id: str) -> dict:
    """Discard section edits and go back to the derived grouping."""
    return _apply_section_edit(score_id, reset_sections)


@app.get("/api/practice/{score_id}/{phrase_id}")
def practice(score_id: str, phrase_id: str, tempo: str | None = None) -> dict:
    """Practice instruction for one passage of one score.

    The score id is part of the path on purpose: an exercise built for one
    score must never be served for another, and a phrase id that does not
    belong to this score is a 404 rather than a best guess.

    The bundle is retuned before lookup for two reasons: trouble spots are
    derived rather than stored, so a spot id only resolves against a retuned
    bundle; and technique selection reads rating factors, which move with
    tempo, so advice must be computed at the tempo the page is showing.
    """
    try:
        bundle = retune(_bundle_for(score_id), parse_tempo(tempo))
    except ExampleUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        guidance = build_guidance(bundle, phrase_id)
    except PassageNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "phraseId": guidance.phrase_id,
        "phraseLabel": guidance.phrase_label,
        "rangeText": guidance.range_text,
        "noteRangeText": guidance.note_range_text,
        "challenge": guidance.challenge,
        "observations": guidance.observations,
        "primary": _exercise_payload(guidance.primary),
        "alternatives": [_exercise_payload(a) for a in guidance.alternatives],
        "noFitReason": guidance.no_fit_reason,
    }


def _exercise_payload(exercise) -> dict | None:
    if exercise is None:
        return None
    return {
        "techniqueId": exercise.technique_id,
        "title": exercise.title,
        "fits": exercise.fits,
        "evidenceCategory": exercise.evidence_category,
        "steps": exercise.steps,
        "listeningGoals": exercise.listening_goals,
        "tempoRule": exercise.tempo_rule,
        "successCriteria": exercise.success_criteria,
        "returnToContext": exercise.return_to_context,
        "cautions": exercise.cautions,
        "sources": exercise.sources,
        "appliesTo": exercise.applies_to,
        "triggerReason": exercise.trigger_reason,
        "variants": exercise.variants,
        "variantNote": exercise.variant_note,
    }


@app.get("/score/example", response_class=HTMLResponse)
def example_score(request: Request, tempo: str | None = None) -> HTMLResponse:
    """The prepared example, annotated over its original scan.

    Labelled as the example everywhere it appears. It is never served in place
    of a failed upload: an upload that fails reports its own failure.
    """
    try:
        bundle = _bundle_for("example")
    except ExampleUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _render_score(request, bundle, "example", tempo, provenance=None)


@app.get("/score/{score_id}", response_class=HTMLResponse)
def uploaded_score(request: Request, score_id: str, tempo: str | None = None) -> HTMLResponse:
    """An analyzed upload. Held in memory for the life of the process."""
    return _render_score(
        request,
        _bundle_for(score_id),
        score_id,
        tempo,
        provenance=jobs.get_provenance(score_id),
    )


def _render_score(request: Request, bundle, score_key: str, tempo_raw, provenance):
    """Render one analysis, optionally re-rated at a supplied tempo.

    `retune` returns a copy, so the cached example bundle is never modified by a
    request that sets a tempo.
    """
    tempo_bpm = parse_tempo(tempo_raw)
    view = build_view(retune(bundle, tempo_bpm), supplied_tempo=tempo_bpm)
    return TEMPLATES.TemplateResponse(
        request=request,
        name="score.html",
        context={
            "view": view,
            "payload": client_payload(view),
            "live_recognition": has_app_credentials(),
            "provenance": provenance,
            "score_key": score_key,
            "tempo_bpm": tempo_bpm,
            "default_tempo": DEFAULT_TEMPO_BPM,
        },
    )
