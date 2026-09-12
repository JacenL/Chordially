"""The upload path: validation, rejection, and analysis of the actual file.

The tests that touch the network are marked and skipped by default. Everything
about scope enforcement and failure reporting runs offline, because those are
the paths a demo is most likely to hit and least likely to have exercised.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from src.app.main import app
from src.config import PROJECT_ROOT
from src.server.analysis import upload as up

ONE_PAGE_PDF = PROJECT_ROOT / "fixtures" / "scores" / "wohlfahrt-op45-bk1-p3.pdf"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def post(client: TestClient, name: str, data: bytes, content_type: str):
    return client.post("/upload", files={"file": (name, io.BytesIO(data), content_type)})


# --------------------------------------------------------------------------
# Scope enforcement. Every rejection must name a recovery action.
# --------------------------------------------------------------------------


def test_empty_file_is_rejected_with_a_recovery(client):
    response = post(client, "empty.pdf", b"", "application/pdf")
    assert response.status_code == 415
    detail = response.json()["detail"]
    assert "empty" in detail["error"].lower()
    assert detail["recovery"]


def test_unsupported_format_is_rejected_by_name(client):
    """A format outside the disclosed set. MusicXML is no longer one of them."""
    response = post(client, "score.sib", b"not a supported format", "application/octet-stream")
    assert response.status_code == 415
    detail = response.json()["detail"]
    assert "score.sib" in detail["error"]
    assert "PDF, PNG and JPEG" in detail["recovery"]
    assert "MusicXML" in detail["recovery"]


def test_a_file_lying_about_being_a_pdf_is_caught(client):
    response = post(client, "fake.pdf", b"GIF89a not a pdf at all", "application/pdf")
    assert response.status_code == 415
    assert "not a PDF" in response.json()["detail"]["error"]


def test_oversized_upload_is_rejected_before_analysis(client):
    oversized = b"%PDF" + b"\0" * (up.MAX_UPLOAD_BYTES + 1)
    response = post(client, "huge.pdf", oversized, "application/pdf")
    assert response.status_code == 415
    assert "limit" in response.json()["detail"]["error"]


def test_tiny_image_is_rejected_with_a_scanning_instruction():
    import cv2
    import numpy as np

    tiny = cv2.imencode(".png", np.full((80, 80), 255, dtype=np.uint8))[1].tobytes()
    with pytest.raises(up.UploadRejected) as excinfo:
        up.render_upload(tiny, "image_scan")
    assert "too small" in excinfo.value.message
    assert "200 DPI" in excinfo.value.recovery


def test_validate_accepts_the_supported_formats():
    assert up.validate(b"%PDF-1.4 ...", "a.pdf", "application/pdf") == "pdf_scan"
    assert up.validate(b"\x89PNG\r\n", "a.png", "image/png") == "image_scan"
    assert up.validate(b"\xff\xd8\xff", "a.jpg", "image/jpeg") == "image_scan"
    # Content type missing entirely: fall back to the extension.
    assert up.validate(b"%PDF-1.4", "a.pdf", None) == "pdf_scan"


def test_missing_job_is_reported_not_invented(client):
    assert client.get("/api/jobs/does-not-exist").status_code == 404


def test_missing_uploaded_score_says_to_upload_again(client):
    response = client.get("/score/upload-never-existed")
    assert response.status_code == 404
    assert "Upload the file again" in response.json()["detail"]


def test_example_route_is_not_shadowed_by_the_upload_route(client):
    """/score/example must keep resolving to the example, not to a lookup."""
    assert client.get("/score/example").status_code == 200


# --------------------------------------------------------------------------
# Provenance wording. This is what keeps a cached run from claiming a live one.
# --------------------------------------------------------------------------


def test_provenance_distinguishes_live_from_cached_from_unread():
    p = up.Provenance(chunks_total=34, chunks_from_cache=22, chunks_from_provider=12)
    text = p.sentence()
    assert "12 read live" in text
    assert "22 reused" in text
    assert p.used_provider is True

    cached_only = up.Provenance(chunks_total=34, chunks_from_cache=34)
    assert cached_only.used_provider is False
    assert "read live" not in cached_only.sentence()

    failed = up.Provenance(chunks_total=10, chunks_failed=10)
    assert "10 not read" in failed.sentence()


# --------------------------------------------------------------------------
# The real thing. Network-touching; run with -m live.
# --------------------------------------------------------------------------


@pytest.mark.live
@pytest.mark.skipif(not ONE_PAGE_PDF.exists(), reason="demo PDF not present")
def test_uploading_the_real_page_produces_a_real_analysis(client):
    response = post(
        client, ONE_PAGE_PDF.name, ONE_PAGE_PDF.read_bytes(), "application/pdf"
    )
    assert response.status_code == 200
    job_id = response.json()["id"]

    import time

    deadline = time.time() + 600
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "failed"):
            break
        time.sleep(1.0)

    assert job is not None and job["state"] == "done", job
    page = client.get(f"/score/{job['scoreId']}")
    assert page.status_code == 200
    assert 'class="difficulty-highlight' in page.text
    assert "Source" in page.text  # provenance disclosure is always present


# --------------------------------------------------------------------------
# MusicXML: the path with no recognition risk
# --------------------------------------------------------------------------

MUSICXML = PROJECT_ROOT / "fixtures" / "scores" / "mozart-k156-mvt1.mxl"


def test_musicxml_is_accepted_by_validation():
    assert MUSICXML.exists()
    assert up.validate(MUSICXML.read_bytes(), MUSICXML.name, None) == "musicxml"
    assert up.validate(b"<score-partwise/>", "a.musicxml", None) == "musicxml"


def test_xml_that_is_not_a_score_is_rejected_by_name(client):
    response = post(client, "notes.xml", b"<html><body>hello</body></html>", "text/xml")
    assert response.status_code == 415
    detail = response.json()["detail"]
    assert "does not" in detail["error"] and "score" in detail["error"]
    assert "MusicXML" in detail["recovery"]


def test_the_unsupported_message_now_mentions_musicxml(client):
    response = post(client, "score.txt", b"plain text", "text/plain")
    assert "MusicXML" in response.json()["detail"]["recovery"]


@pytest.mark.skipif(not MUSICXML.exists(), reason="MusicXML fixture absent")
def test_musicxml_analysis_leaves_nothing_for_review():
    """The headline claim: exact notes mean no measure is ever unrated.

    Asserted against the real fixture rather than a contrived one, because the
    claim is about real repertoire -- 145 measures of Mozart with ties, chords
    and mixed values, all of which a scan would have had to guess at.
    """
    bundle, provenance = up.analyze_upload(
        MUSICXML.read_bytes(), MUSICXML.name, None
    )

    measures = bundle.score.measures
    assert len(measures) > 100
    assert all(m.quality == "confident" for m in measures), "nothing should be uncertain"
    assert all(
        d.score is not None for d in bundle.measure_difficulty.values()
    ), "every measure must carry a rating"

    scores = [d.score for d in bundle.measure_difficulty.values()]
    assert max(scores) > min(scores), "a real score should vary in difficulty"

    # No provider was involved, and the disclosure says that rather than
    # reporting a recognition run that never happened.
    assert provenance.from_file is True
    assert provenance.used_provider is False
    assert "MusicXML" in provenance.sentence()
    assert "read live" not in provenance.sentence()


@pytest.mark.skipif(not MUSICXML.exists(), reason="MusicXML fixture absent")
def test_musicxml_discloses_what_it_did_not_analyse():
    bundle, _ = up.analyze_upload(MUSICXML.read_bytes(), MUSICXML.name, None)
    warnings = " ".join(bundle.score.warnings)
    assert "4 parts" in warnings and "Violin I" in warnings
    assert "180 measures" in warnings and "page 1" in warnings


@pytest.mark.skipif(not MUSICXML.exists(), reason="MusicXML fixture absent")
def test_musicxml_reaches_a_rendered_score_through_http(client):
    response = post(
        client, MUSICXML.name, MUSICXML.read_bytes(),
        "application/vnd.recordare.musicxml+xml",
    )
    assert response.status_code == 200
    job_id = response.json()["id"]

    import time

    deadline = time.time() + 300
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert job and job["state"] == "done", job

    page = client.get(f"/score/{job['scoreId']}")
    assert page.status_code == 200
    assert ".svg" in page.text, "the engraved page should be served as SVG"
    assert 'class="difficulty-highlight' in page.text
    assert "difficulty-highlight--unrated" not in page.text, "nothing should be hatched"
