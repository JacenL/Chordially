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
    assert "20" in page.locator(".start-card--upload .note").first.inner_text()

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
    assert page.locator(".ribbon-segment").count() == page.locator(".measure").count()

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
