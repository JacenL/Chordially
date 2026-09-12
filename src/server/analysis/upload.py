"""Take an uploaded file and produce a validated analysis of that actual file.

Scope is disclosed rather than discovered: one page, printed solo violin
notation, PDF or PNG or JPEG, under a stated size. A file outside that scope is
rejected by name with a specific recovery action, never analyzed badly and
presented as if it were fine.

The geometry half of this pipeline needs no credentials at all -- staves,
barlines and measure regions come from OpenCV reading the uploaded pixels. Only
the notation content needs the provider. That split is what lets an upload
still produce a real page map when transcription is unavailable: the measures are
real and located, and every one whose content could not be read is marked
`not_attempted` rather than guessed at.
"""

from __future__ import annotations

import dataclasses
import os
import time
from typing import Callable

import numpy as np

from src.config import PROJECT_ROOT
from src.schemas.analysis import AnalysisBundle, RecognitionReport
from src.server.analysis import orchestrate
from src.server.analysis.assemble import (
    build_score,
    fingerprint,
    rate_phrases,
    rate_score,
    segment_score,
)
from src.server.recognition import audiveris_source as omr
from src.server.recognition import cv_geometry as cg
from src.server.recognition import musicxml_source as mx

# Disclosed limits. Stated in the upload UI, enforced here.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
SUPPORTED = {
    "application/pdf": "pdf_scan",
    "image/png": "image_scan",
    "image/jpeg": "image_scan",
    "image/jpg": "image_scan",
    "application/vnd.recordare.musicxml+xml": "musicxml",
    "application/vnd.recordare.musicxml": "musicxml",
}
SUPPORTED_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".musicxml", ".xml", ".mxl")

# One page is analyzed. A multi-page PDF is accepted, and the page chosen is the
# first one that actually contains staff notation -- page 1 of a real etude book
# is a cover or a preface, and analyzing it would produce an empty result for a
# perfectly good file. Which page was chosen is always reported, because
# silently analyzing page 4 of a 40-page part book and calling it "your score"
# would be a lie of omission.
PAGES_ANALYZED = 1

# How far into a PDF to look for notation before giving up. Bounds the work a
# pathological upload can cause.
MAX_PAGES_SCANNED = 12

# Where rendered page images live so the browser can show them. Under work/,
# which .gitignore excludes: an uploaded score is the user's, and it does not
# belong in the repository.
PAGE_DIR = PROJECT_ROOT / "work" / "pages"


class UploadRejected(ValueError):
    """An upload outside the disclosed scope, with what to do about it."""

    def __init__(self, message: str, recovery: str) -> None:
        super().__init__(message)
        self.message = message
        self.recovery = recovery


@dataclasses.dataclass
class Provenance:
    """Where each measure's content actually came from.

    The demo runs with an exhausted provider credit balance, so this is not a
    diagnostic detail -- it is the difference between "we read your score" and
    "we reused a reading of this exact image". Both are legitimate; conflating
    them is not.
    """

    chunks_total: int = 0
    chunks_from_cache: int = 0
    chunks_from_provider: int = 0
    chunks_failed: int = 0
    provider_unavailable: str = ""
    # A MusicXML import reads notes from the file itself. Reporting that as
    # "0 sections read live" would describe a recognition run that never
    # happened, and would understate the result: these notes are exact.
    from_file: bool = False
    # A scan read by Audiveris on this machine. Kept distinct from `from_file`
    # on purpose: "read directly from the MusicXML file" would be a false claim
    # about a page that was recognized, and recognition can be wrong in ways
    # reading a file cannot. What the two share is that nothing left the machine.
    from_local_omr: bool = False

    @property
    def used_provider(self) -> bool:
        return self.chunks_from_provider > 0

    def sentence(self) -> str:
        if self.from_local_omr:
            return (
                "Notation recognized on this machine by Audiveris — no "
                "transcription service was called and nothing was sent "
                "anywhere. The page below is re-engraved from what it read, "
                "not your original scan."
            )
        if self.from_file:
            return (
                "Notes read directly from the MusicXML file — exact, with no "
                "recognition step and no transcription service involved."
            )
        if self.chunks_total == 0:
            return "No notation was transcribed for this page."
        parts = []
        if self.chunks_from_provider:
            parts.append(f"{self.chunks_from_provider} read live")
        if self.chunks_from_cache:
            parts.append(f"{self.chunks_from_cache} reused from an earlier reading of this exact image")
        if self.chunks_failed:
            parts.append(f"{self.chunks_failed} not read")
        return f"Notation sections: {', '.join(parts)}."


# Which engine reads a scan. "audiveris" runs locally and calls no provider;
# "vision" is the original path and is kept reachable rather than deleted, so a
# machine without Audiveris installed still has a route. The default is local:
# a demo that depends on a credit balance is a demo that can stop working.
SCAN_ENGINE = os.environ.get("PRACTICEMAP_SCAN_ENGINE", "audiveris").strip().lower()


def validate(data: bytes, filename: str, content_type: str | None) -> str:
    """Check the upload against the disclosed scope. Returns the input kind."""
    if not data:
        raise UploadRejected(
            "That file is empty.", "Choose a file that contains a scanned page."
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected(
            f"That file is {len(data) / 1_048_576:.1f} MB, above the "
            f"{MAX_UPLOAD_BYTES // 1_048_576} MB limit.",
            "Export a single page, or reduce the scan resolution, and try again.",
        )

    lowered = (filename or "").lower()
    kind = SUPPORTED.get((content_type or "").lower())
    if kind is None and lowered.endswith(".pdf"):
        kind = "pdf_scan"
    elif kind is None and lowered.endswith((".png", ".jpg", ".jpeg")):
        kind = "image_scan"
    elif kind is None and lowered.endswith(mx.SUPPORTED_EXTENSIONS):
        kind = "musicxml"

    # A .xml or .mxl extension is not proof. Sniff before committing, so a
    # misnamed file fails with a sentence instead of a stack trace from music21.
    if kind == "musicxml" and not mx.looks_like_musicxml(data):
        raise UploadRejected(
            f"{filename or 'That file'} is named like MusicXML but does not "
            "contain a score.",
            "Export it again from your notation software as MusicXML, "
            "compressed (.mxl) or not (.musicxml).",
        )

    if kind is None:
        raise UploadRejected(
            f"{filename or 'That file'} is not a supported format.",
            "Chordially reads PDF, PNG and JPEG scans of printed notation, and "
            "MusicXML files (.musicxml, .xml, .mxl). Export your score to one of "
            "those and try again.",
        )

    # Sniff the actual bytes. A .png extension on a PDF, or the reverse, would
    # otherwise fail deep inside a decoder with an unhelpful message.
    if kind == "pdf_scan" and not data.startswith(b"%PDF"):
        raise UploadRejected(
            "That file is named like a PDF but its contents are not a PDF.",
            "Re-export the page and try again.",
        )
    return kind


@dataclasses.dataclass
class RenderedPage:
    gray: np.ndarray          # 200 DPI equivalent, for geometry
    hires: np.ndarray         # 400 DPI equivalent, for transcription crops
    page_count: int
    page_index: int           # which page was actually analyzed, 0-based


def render_upload(data: bytes, kind: str) -> RenderedPage:
    """Grayscale arrays for geometry and for crops, plus which page they are.

    A PDF is rendered twice, at 200 DPI for geometry and 400 for crops, because
    geometry is cheap at low resolution and pitch reading is not. An uploaded
    image arrives at whatever resolution it has; it is upscaled for crops when
    small, since the crop is what a reader has to see noteheads in.
    """
    if kind == "pdf_scan":
        import pymupdf

        path = PAGE_DIR / f"src-{fingerprint(data)[:16]}.pdf"
        PAGE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        try:
            with pymupdf.open(path) as doc:
                page_count = doc.page_count
            if page_count < 1:
                raise UploadRejected(
                    "That PDF has no pages.", "Check the file and try again."
                )

            # Find the first page carrying staves. Detection runs at the cheap
            # geometry resolution; the expensive crop render happens once, for
            # the page actually chosen.
            chosen = None
            for index in range(min(page_count, MAX_PAGES_SCANNED)):
                candidate = cg.render_page(str(path), index, dpi=cg.RENDER_DPI)
                if cg.analyze_page(candidate).systems:
                    chosen = (index, candidate)
                    break
            if chosen is None:
                raise UploadRejected(
                    "No staff lines were found in the first "
                    f"{min(page_count, MAX_PAGES_SCANNED)} page(s) of that PDF.",
                    "Chordially reads clear printed notation. Check that the "
                    "pages are upright, in focus, and not handwritten.",
                )
            index, gray = chosen
            hires = cg.render_page(str(path), index, dpi=cg.CROP_DPI)
        finally:
            path.unlink(missing_ok=True)
        return RenderedPage(gray=gray, hires=hires, page_count=page_count, page_index=index)

    try:
        gray = cg.load_image(data)
    except ValueError as exc:
        raise UploadRejected(
            "That image could not be decoded.",
            "Re-save it as a PNG or JPEG and try again.",
        ) from exc

    if min(gray.shape) < 400:
        raise UploadRejected(
            f"That image is {gray.shape[1]}×{gray.shape[0]} pixels, too small to "
            "find staff lines in.",
            "Scan the page at 200 DPI or higher and try again.",
        )

    # Crops want roughly the 2:1 advantage a 400 DPI render gives a PDF.
    import cv2

    hires = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    return RenderedPage(gray=gray, hires=hires, page_count=1, page_index=0)


def _analyze_musicxml(
    data: bytes, filename: str, score_id: str, started: float, say
) -> tuple[AnalysisBundle, Provenance]:
    """The MusicXML path: exact notes, exact geometry, no provider.

    Deliberately short, because it reuses everything. Verovio engraves the part
    and the measure boxes are read out of that engraving; music21 supplies the
    notes; `build_score` assembles them with the same function a scan uses.
    """
    say("Reading the score")
    page = mx.load_musicxml(data)

    say("Engraving the page and measuring it")
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    svg_path = PAGE_DIR / f"{score_id}.svg"
    svg_path.write_bytes(page.svg)

    say("Rating measures and grouping phrases")
    score = build_score(
        score_id=score_id,
        content_fingerprint=fingerprint(data),
        geometry=page.geometry,
        transcriptions=page.transcriptions,
        signatures_by_system=page.signatures_by_system,
        not_attempted=None,
        input_kind="musicxml",
        title=page.title or filename or "Uploaded score",
        is_example=False,
        image_url=f"/uploads/pages/{score_id}.svg",
        # MusicXML states the sounding pitch, key signature already applied.
        accidental_convention="sounding",
        tempo_bpm=page.printed_tempo_bpm,
    )

    if page.part_count > 1:
        score.warnings.append(
            f"This file has {page.part_count} parts. "
            f"{page.part_name} was analyzed; the others were not read."
        )
    if page.measures_on_page < page.measures_in_part:
        score.warnings.append(
            f"The part has {page.measures_in_part} measures and engraves to "
            f"{page.page_count} pages. The {page.measures_on_page} measures on "
            "page 1 were analyzed; the rest were not."
        )

    measure_ratings = rate_score(score)
    phrases = segment_score(score)

    bundle = AnalysisBundle(
        score=score,
        measure_difficulty=measure_ratings,
        phrases=phrases,
        phrase_difficulty=rate_phrases(phrases, measure_ratings),
        recognition=RecognitionReport(latency_s=round(time.monotonic() - started, 1)),
    )
    return bundle, Provenance(from_file=True)


def analyze_upload(
    data: bytes,
    filename: str,
    content_type: str | None,
    *,
    progress: Callable[[str], None] | None = None,
    use_cache: bool = True,
) -> tuple[AnalysisBundle, Provenance]:
    """The whole path: bytes in, validated analysis of those bytes out."""

    def say(message: str) -> None:
        if progress:
            progress(message)

    started = time.monotonic()
    kind = validate(data, filename, content_type)
    score_id = f"upload-{fingerprint(data)[:12]}"

    if kind == "musicxml":
        return _analyze_musicxml(data, filename, score_id, started, say)

    if SCAN_ENGINE == "audiveris":
        # A scan becomes MusicXML first, and then takes the MusicXML path
        # exactly as an imported file would. Notes and measure boxes then come
        # from one document instead of two that have to be reconciled -- see
        # `audiveris_source` for why that matters here specifically.
        say("Reading the notation on this machine with Audiveris")
        exported = omr.transcribe(data, filename)
        bundle, _ = _analyze_musicxml(exported, filename, score_id, started, say)
        return bundle, Provenance(from_local_omr=True)

    say("Rendering the page")
    rendered = render_upload(data, kind)
    gray, hires = rendered.gray, rendered.hires

    say("Finding staves, barlines and measures")
    analysis = orchestrate.analyze_page(gray, hires, use_cache=use_cache, progress=say)
    geometry = analysis.geometry

    if not geometry.systems:
        raise UploadRejected(
            "No staff lines were found on that page.",
            "Chordially reads clear printed notation. Check that the page is "
            "upright, in focus, and not handwritten, then try again.",
        )

    say("Rating measures and grouping phrases")
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    page_png = PAGE_DIR / f"{score_id}.png"
    page_png.write_bytes(cg.encode_png(hires))

    warnings: list[str] = []
    if rendered.page_count > PAGES_ANALYZED:
        warnings.append(
            f"This file has {rendered.page_count} pages. Page "
            f"{rendered.page_index + 1} was analyzed, the first page containing "
            "staff notation; the rest of the file was not read."
        )

    score = build_score(
        score_id=score_id,
        content_fingerprint=fingerprint(data),
        geometry=geometry,
        transcriptions=analysis.transcriptions,
        signatures_by_system=analysis.signatures_by_system,
        not_attempted=analysis.not_attempted,
        input_kind=kind,
        title=filename or "Uploaded score",
        is_example=False,
        image_url=f"/uploads/pages/{score_id}.png",
    )
    score.warnings.extend(warnings)

    measure_ratings = rate_score(score)
    phrases = segment_score(score)
    phrase_ratings = rate_phrases(phrases, measure_ratings)

    provenance = Provenance(
        chunks_total=analysis.chunks_attempted,
        chunks_from_cache=analysis.cache_hits,
        chunks_from_provider=max(
            0,
            analysis.chunks_attempted - analysis.cache_hits - analysis.chunks_failed,
        ),
        chunks_failed=analysis.chunks_failed,
        provider_unavailable=analysis.provider_unavailable,
    )

    bundle = AnalysisBundle(
        score=score,
        measure_difficulty=measure_ratings,
        phrases=phrases,
        phrase_difficulty=phrase_ratings,
        recognition=RecognitionReport(
            chunks_attempted=analysis.chunks_attempted,
            mismatched_chunks=analysis.mismatched_chunks,
            errors=analysis.errors,
            latency_s=round(time.monotonic() - started, 1),
            input_tokens=analysis.input_tokens,
            output_tokens=analysis.output_tokens,
            cache_read_tokens=analysis.cache_read_tokens,
        ),
    )
    return bundle, provenance
