"""The demo, end to end, in a real browser.

This is the journey that gets shown: choose a file, watch it analyze, land on
the annotated score, select a passage, read the exercise. It is a separate file
from the viewer tests because it is the one that must not break, and it should
be runnable on its own in the minute before a demo.

Marked `live` because analysis may call the provider. With a warm transcription
cache it makes no network calls at all and finishes in seconds.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from src.config import PROJECT_ROOT

playwright_api = pytest.importorskip("playwright.sync_api")

DEMO_PDF = PROJECT_ROOT / "fixtures" / "scores" / "wohlfahrt-op45-bk1-p3.pdf"

pytestmark = pytest.mark.live


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def server() -> str:
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if process.poll() is not None:
                raise RuntimeError("the application exited before serving")
            try:
                with urllib.request.urlopen(f"{base}/health", timeout=1):
                    break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.2)
        else:
            raise RuntimeError("the application did not start within 30s")
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture(scope="module")
def browser_page(server):
    with playwright_api.sync_playwright() as play:
        try:
            browser = play.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium is not installed: {exc}")
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )
        page.errors = errors  # type: ignore[attr-defined]
        yield page
        context.close()
        browser.close()


@pytest.mark.skipif(not DEMO_PDF.exists(), reason="demo PDF not present")
def test_upload_analyze_select_and_read_an_exercise(server, browser_page):
    page = browser_page

    # 1. The start screen.
    page.goto(f"{server}/", wait_until="networkidle")
    assert page.locator("#upload-submit").is_disabled()
    assert "20" in page.locator(".upload-formats").inner_text()

    # 2. Choose the real file and analyze it.
    page.set_input_files("#file-input", str(DEMO_PDF))
    assert page.locator("#upload-submit").is_enabled()
    page.click("#upload-submit")

    # 3. Honest progress, then the score. Generous timeout: a cold cache means
    #    real provider calls, and the point of the stage text is that a slow run
    #    still says what it is doing.
    page.wait_for_url("**/score/upload-**", timeout=600_000)
    page.wait_for_load_state("networkidle")

    # 4. The analysis is of the uploaded file, over the uploaded page image.
    assert page.locator(".page-image").get_attribute("src").startswith("/uploads/pages/")
    assert page.locator(".measure").count() > 40
    # Bands are practice passages, so there are fewer of them than measures,
    # and between them they still account for every measure.
    measures = page.locator(".measure").count()
    bands = page.locator(".difficulty-highlight").count()
    assert bands == measures
    covered = page.eval_on_selector_all(
        ".difficulty-highlight",
        "els => els.map(e => e.dataset.measureId)",
    )
    assert len(set(covered)) == measures

    # 5. Provenance is always stated.
    provenance = page.locator(".notice--provenance").inner_text()
    assert "Notation sections" in provenance

    # 6. Ratings are one decimal, phrases are listed.
    assert page.locator(".phrase-item").count() > 3
    import re

    scores = page.eval_on_selector_all(
        ".phrase-item-score", "els => els.map(e => e.textContent.trim())"
    )
    for score in scores:
        assert re.fullmatch(r"\d+\.\d", score) or score == "Needs review", score

    # 7. Selecting a passage opens practice instruction for that passage.
    page.locator(".phrase-item").first.click()
    page.wait_for_selector(".exercise-card--primary .exercise-title", timeout=15_000)
    title = page.locator(".exercise-card--primary .exercise-title").inner_text()
    assert title.strip()
    why = page.locator(".exercise-card--primary .exercise-why").inner_text()
    assert "Chosen because" in why and "Applies to" in why

    # 8. Steps, listening goals and the return to the music are all present.
    body = page.locator("#practice-body").inner_text()
    assert "STEPS" in body.upper()
    assert "LISTEN FOR" in body.upper()
    assert "Back to the music" in body

    # 9. No JavaScript errors anywhere in the journey.
    assert page.errors == [], page.errors  # type: ignore[attr-defined]


@pytest.mark.skipif(not DEMO_PDF.exists(), reason="demo PDF not present")
def test_a_rhythm_variation_is_offered_somewhere_and_its_pairs_balance(server, browser_page):
    """Demo requirement: complementary rhythm variations where appropriate."""
    page = browser_page
    page.goto(f"{server}/score/example", wait_until="networkidle")

    found = False
    count = page.locator(".phrase-item").count()
    for index in range(min(count, 6)):
        page.locator(".phrase-item").nth(index).click()
        page.wait_for_timeout(400)
        if page.locator(".variant").count() >= 2:
            found = True
            break
    assert found, "no phrase in the example offered a rhythm variation"

    names = page.eval_on_selector_all(
        ".variant-name", "els => els.map(e => e.textContent)"
    )
    assert any("Long" in n for n in names) and any("Short" in n for n in names)

    longs = page.locator(".variant").first.locator(".variant-note--long").count()
    shorts = page.locator(".variant").first.locator(".variant-note--short").count()
    assert longs == shorts and longs > 0


@pytest.mark.skipif(not DEMO_PDF.exists(), reason="demo PDF not present")
def test_correcting_a_passage_boundary(server, browser_page):
    """Split, merge, refuse and undo, through the real interface.

    The controls act on the practice passage, which is what the score is
    coloured by and what a click selects. Console errors are not asserted here
    the way they are in the journey test: a refused edit is a 409, and the
    browser logs every non-2xx fetch to the console. The refusal is the
    behaviour under test, so its log line is expected rather than a fault.
    """
    page = browser_page
    page.goto(f"{server}/score/example", wait_until="networkidle")

    def passage_rows() -> int:
        return page.locator(".phrase-item--section").count()

    def click_and_reload(selector: str) -> None:
        """Click something that edits, and wait for the reload it triggers.

        Waiting on a row count is not enough and was actively wrong for the
        reset button: the count after an undo equals the count before it, so the
        wait returned instantly and left a navigation in flight, which then
        aborted the *next* test's `goto`. Stamping the document and waiting for
        the stamp to disappear waits for the reload itself, whatever it changes.
        """
        page.evaluate("window.__beforeReload = true")
        page.click(selector)
        page.wait_for_function("() => window.__beforeReload === undefined", timeout=15_000)
        page.wait_for_load_state("networkidle")

    before = passage_rows()
    assert before >= 2

    # Split the first passage at its first offered boundary.
    page.locator(".phrase-item--section").first.click()
    page.wait_for_selector("#edit-row:not([hidden])")
    assert page.locator("#split-at option").count() > 0
    page.select_option("#split-at", index=0)
    click_and_reload("#split-btn")
    assert passage_rows() == before + 1

    # The corrected boundary is marked as the user's, not as inference.
    page.locator(".phrase-item--section").nth(1).click()
    page.wait_for_selector("#edit-row:not([hidden])")
    assert page.locator("#edited-pill").is_visible()

    # Merging puts it back.
    page.locator(".phrase-item--section").first.click()
    page.wait_for_selector("#edit-row:not([hidden])")
    click_and_reload("#merge-btn")
    assert passage_rows() == before

    # The last passage has nothing to merge with, and says so.
    page.locator(".phrase-item--section").last.click()
    page.wait_for_selector("#edit-row:not([hidden])")
    page.click("#merge-btn")
    page.wait_for_selector("#edit-note:not([hidden])")
    assert "last passage" in page.locator("#edit-note").inner_text()

    # Undo returns to the derived grouping.
    click_and_reload("#reset-edits")
    assert passage_rows() == before


@pytest.mark.skipif(not DEMO_PDF.exists(), reason="demo PDF not present")
def test_a_trouble_spot_keeps_its_parent_passage_in_view(server, browser_page):
    """Journey step 6, made literal: going one level in loses nothing.

    A hard spot is secondary guidance inside a passage. It is reachable, and
    reaching it keeps the passage and the phrase above it in the breadcrumb --
    but it is never what a click on the score resolves to, which is what stopped
    "click a measure, get advice about this passage" from being true.
    """
    page = browser_page
    page.goto(f"{server}/score/example", wait_until="networkidle")

    spots = page.locator(".phrase-item--spot")
    assert spots.count() > 0, "the example should contain at least one hard spot"
    spot_id = spots.first.get_attribute("data-phrase-id")
    spots.first.click()
    page.wait_for_timeout(500)

    assert page.locator("#sel-title").inner_text() == "Hard spot"
    assert page.locator("#sel-breadcrumb").is_visible()
    trail = page.locator("#sel-breadcrumb").inner_text()
    assert "Measures" in trail and "Phrase" in trail
    # The passage around it is still outlined and still highlighted.
    assert page.locator(".section-outline.is-selected").count() >= 1
    assert page.locator(".trouble-outline.is-selected").count() >= 1

    # Clicking a measure the spot covers selects the passage, not the spot.
    covered = page.evaluate(
        """(spotId) => {
            const data = JSON.parse(document.getElementById('score-data').textContent);
            const spot = data.phrases[spotId];
            return spot ? spot.measureIds[0] : null;
        }""",
        spot_id,
    )
    assert covered
    page.locator(f'.measure[data-measure-id="{covered}"]').click()
    page.wait_for_timeout(300)
    assert page.locator("#sel-title").inner_text() != "Hard spot"
