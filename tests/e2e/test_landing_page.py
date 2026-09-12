"""The landing page in a real browser.

What is being guarded is that the redesign did not quietly drop anything the
page is required to carry. A cleaner screen that has lost its error handling,
its format information or its data-handling disclosure is not an improvement --
it is the same page with the honest parts removed.

Skipped, not failed, when Chromium is not installed. Install it with:

    python -m playwright install chromium
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


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def server() -> str:
    port = free_port()
    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "src.app.main:app",
            "--port", str(port), "--log-level", "warning",
        ],
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


@pytest.fixture()
def page(server):
    with playwright_api.sync_playwright() as play:
        try:
            browser = play.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium is not installed: {exc}")
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        current = context.new_page()
        errors: list[str] = []
        current.on("pageerror", lambda exc: errors.append(str(exc)))
        current.goto(f"{server}/", wait_until="networkidle")
        current.errors = errors  # type: ignore[attr-defined]
        yield current
        browser.close()


def test_one_primary_action_and_one_secondary(page):
    """Visual hierarchy, asserted rather than eyeballed."""
    assert page.locator(".button--primary").count() == 1
    assert page.locator("#upload-submit").is_visible()
    secondary = page.locator('.secondary-action a[href="/score/example"]')
    assert secondary.count() == 1
    assert secondary.is_visible()

    # The primary really is the more prominent of the two.
    primary_size = page.locator("#upload-submit").bounding_box()
    secondary_size = secondary.bounding_box()
    assert primary_size["height"] > secondary_size["height"]


def test_the_technical_detail_is_folded_away_but_present(page):
    """Detail moved behind a summary, not deleted."""
    details = page.locator(".detail")
    assert details.count() >= 3
    for index in range(details.count()):
        body = details.nth(index).locator(".detail-body")
        assert body.count() == 1
        assert not body.is_visible(), "detail should start closed"

    page.locator(".detail summary").first.click()
    assert page.locator(".detail").first.locator(".detail-body").is_visible()


def test_the_data_handling_disclosure_is_still_reachable(page):
    """Sending a scan to a provider has to be stated somewhere a user can find."""
    summaries = page.eval_on_selector_all(
        ".detail summary", "els => els.map(e => e.textContent.trim())"
    )
    index = next(i for i, text in enumerate(summaries) if "your file" in text.lower())
    page.locator(".detail summary").nth(index).click()
    body = page.locator(".detail").nth(index).locator(".detail-body").inner_text()
    assert "Anthropic" in body
    assert "not stored" in body
    assert "never leaves this machine" in body


def test_supported_formats_are_visible_without_opening_anything(page):
    formats = page.locator(".upload-formats").inner_text()
    for expected in ("PDF", "PNG", "JPEG", "MusicXML", "20"):
        assert expected in formats, expected


def test_the_submit_button_is_disabled_until_a_file_is_chosen(page):
    assert page.locator("#upload-submit").is_disabled()
    if not DEMO_PDF.exists():
        pytest.skip("demo PDF not present")
    page.set_input_files("#file-input", str(DEMO_PDF))
    assert page.locator("#upload-submit").is_enabled()
    assert DEMO_PDF.name in page.locator(".file-field-label").inner_text()
    assert "has-file" in (page.locator("#upload-form").get_attribute("class") or "")


def test_a_rejected_upload_reports_itself_and_stays_on_this_screen(page, tmp_path):
    """The rule the redesign must not lose: a failure never becomes the example."""
    bad = tmp_path / "not-music.txt"
    bad.write_text("this is not sheet music", encoding="utf-8")

    page.set_input_files("#file-input", str(bad))
    page.click("#upload-submit")
    page.wait_for_selector("#upload-error:not([hidden])", timeout=15_000)

    assert page.locator("#upload-error-message").inner_text().strip()
    assert page.locator("#upload-error-recovery").inner_text().strip()
    # Still here, and specifically not handed the example score instead.
    assert "/score/" not in page.url
    assert page.locator("#upload-form").is_visible()
    # The form is usable again rather than left in a dead state.
    assert page.locator("#upload-submit").is_enabled()


def test_the_progress_area_exists_and_names_a_stage_not_a_percentage(page):
    progress = page.locator("#upload-progress")
    assert progress.count() == 1
    assert page.locator("#upload-stage").count() == 1
    assert "No progress bar" in progress.inner_text()


def test_the_page_works_at_phone_width(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(150)
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow == 0
    assert page.locator("#upload-submit").is_visible()
    assert page.locator('.secondary-action a[href="/score/example"]').is_visible()
    assert page.errors == [], page.errors  # type: ignore[attr-defined]


def test_the_credential_status_is_stated(page):
    status = page.locator(".status").inner_text()
    assert "credentials" in status.lower()
