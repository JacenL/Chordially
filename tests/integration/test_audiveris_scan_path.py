"""The scan path reads notation locally and calls no provider.

Audiveris itself is not invoked here. Running a Java program on a 61-measure
page takes about fifteen seconds, which does not belong in a suite that has to
stay fast, and the thing worth pinning is not "Audiveris works" -- that was
measured in B2a -- but that *our* wiring sends a scan down the local route,
never touches the provider, and reports a missing engine with something the user
can act on.

The canned export lives under `work/`, which is gitignored, so the tests that
need real recognized notation skip themselves rather than fail on a fresh clone.
"""

from __future__ import annotations

import pytest

from src.config import PROJECT_ROOT
from src.server.analysis import upload as upload_mod
from src.server.recognition import audiveris_source as omr

CANNED_EXPORT = PROJECT_ROOT / "work" / "audiveris-out" / "wohlfahrt-op45-bk1-p3.mxl"
FIXTURE_PDF = PROJECT_ROOT / "fixtures" / "scores" / "wohlfahrt-op45-bk1-p3.pdf"


@pytest.fixture()
def canned() -> bytes:
    if not CANNED_EXPORT.exists():
        pytest.skip(f"no canned Audiveris export at {CANNED_EXPORT}")
    return CANNED_EXPORT.read_bytes()


def test_a_missing_engine_is_reported_with_a_recovery_action(monkeypatch):
    """Never a traceback, and never a silent fall back to a provider."""
    monkeypatch.setattr(omr, "executable", lambda: None)
    with pytest.raises(omr.AudiverisUnavailable) as caught:
        omr.transcribe(b"not really a pdf", "page.pdf")

    assert caught.value.message.strip()
    assert caught.value.recovery.strip()
    # The action names what to do, not merely that something went wrong.
    assert omr.ENV_VAR in caught.value.recovery
    assert "MusicXML" in caught.value.recovery


def test_the_default_scan_engine_is_the_local_one():
    """A demo that depends on a credit balance is a demo that can stop working."""
    assert upload_mod.SCAN_ENGINE == "audiveris"


def test_a_scan_never_reaches_the_vision_path(monkeypatch, canned):
    """The load-bearing assertion: zero provider calls for an uploaded scan."""
    monkeypatch.setattr(upload_mod.omr, "transcribe", lambda data, name: canned)

    def explode(*args, **kwargs):
        raise AssertionError("the vision path was entered for a scan upload")

    monkeypatch.setattr(upload_mod.orchestrate, "analyze_page", explode)

    bundle, provenance = upload_mod.analyze_upload(
        FIXTURE_PDF.read_bytes() if FIXTURE_PDF.exists() else b"%PDF-1.4 stub",
        "wohlfahrt-op45-bk1-p3.pdf",
        "application/pdf",
    )

    assert bundle.score.measures
    assert provenance.used_provider is False
    assert provenance.chunks_from_provider == 0


def test_the_provenance_says_where_the_notes_came_from(monkeypatch, canned):
    """Recognized locally is a different fact from read from a file, and from
    read by a service. The notice must not blur the three."""
    monkeypatch.setattr(upload_mod.omr, "transcribe", lambda data, name: canned)
    _, provenance = upload_mod.analyze_upload(
        FIXTURE_PDF.read_bytes() if FIXTURE_PDF.exists() else b"%PDF-1.4 stub",
        "page.pdf",
        "application/pdf",
    )
    sentence = provenance.sentence()

    assert "Audiveris" in sentence
    assert "nothing was sent" in sentence
    # It also has to admit the page on screen is not the upload.
    assert "re-engraved" in sentence
    # And it must not claim the exactness that only a real MusicXML file has.
    assert provenance.from_file is False
    assert "directly from the MusicXML file" not in sentence


def test_a_scan_upload_produces_rated_music(monkeypatch, canned):
    """End to end over the canned export: the page analyzes, and it analyzes
    better than the cached vision run it replaces (32 of 61)."""
    monkeypatch.setattr(upload_mod.omr, "transcribe", lambda data, name: canned)
    bundle, _ = upload_mod.analyze_upload(
        FIXTURE_PDF.read_bytes() if FIXTURE_PDF.exists() else b"%PDF-1.4 stub",
        "page.pdf",
        "application/pdf",
    )

    rated = [d.score for d in bundle.measure_difficulty.values() if d.score is not None]
    assert len(rated) > 43, f"only {len(rated)} measures rated"
    # Beginner method repertoire still has to rate as beginner repertoire; the
    # engine change must not move the scale.
    assert max(rated) < 6.0, max(rated)
