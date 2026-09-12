"""The viewer in a real browser.

Two of C3's acceptance conditions cannot honestly be checked without laying out
a page: that annotations stay on their measures through zoom and resize, and
that clicking a measure selects the right phrase. Percentage positioning makes
the first one true by construction, but "by construction" is a claim, and this
is where it gets tested rather than asserted.

Skipped, not failed, when Chromium is not installed -- a missing browser is a
missing tool, not a broken product. Install it with:

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

# How closely an overlay must track its page across layouts. 0.002 of page width
# on this fixture is under two pixels at 100% zoom -- far tighter than the
# margin between adjacent measures, so a drifting overlay cannot pass.
ALIGNMENT_TOLERANCE = 0.002


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
def page(server):
    with playwright_api.sync_playwright() as play:
        try:
            browser = play.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"Chromium is not installed: {exc}")
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()
        page.goto(f"{server}/score/example", wait_until="networkidle")
        yield page
        context.close()
        browser.close()


def relative_boxes(page) -> dict[str, tuple[float, float, float]]:
    """Each measure overlay expressed as a fraction of the page image."""
    return page.evaluate(
        """() => {
            const image = document.querySelector('.page-image').getBoundingClientRect();
            const out = {};
            for (const el of document.querySelectorAll('.measure')) {
                const box = el.getBoundingClientRect();
                out[el.dataset.measureId] = [
                    (box.left - image.left) / image.width,
                    (box.top - image.top) / image.height,
                    box.width / image.width,
                ];
            }
            return out;
        }"""
    )


def test_page_and_overlays_render(page):
    assert page.locator(".page-image").count() == 1
    assert page.locator(".measure").count() > 50
    # Bands are passages, so there are far fewer of them than measures, and
    # every measure is still accounted for by exactly one.
    measures = page.locator(".measure").count()
    bands = page.locator(".difficulty-highlight").count()
    assert bands == measures
    covered = page.eval_on_selector_all(
        ".difficulty-highlight",
        "els => els.map(e => e.dataset.measureId)",
    )
    assert len(covered) == measures
    assert len(set(covered)) == measures
    assert page.locator(".section-outline").count() > 0


def test_overlays_hold_their_place_through_resize(page):
    before = relative_boxes(page)
    page.set_viewport_size({"width": 820, "height": 900})
    page.wait_for_timeout(120)
    after = relative_boxes(page)

    assert set(before) == set(after)
    for measure_id, (x, y, w) in before.items():
        ax, ay, aw = after[measure_id]
        assert abs(ax - x) < ALIGNMENT_TOLERANCE, measure_id
        assert abs(ay - y) < ALIGNMENT_TOLERANCE, measure_id
        assert abs(aw - w) < ALIGNMENT_TOLERANCE, measure_id

    page.set_viewport_size({"width": 1400, "height": 900})
    page.wait_for_timeout(120)


def test_overlays_hold_their_place_through_zoom(page):
    before = relative_boxes(page)
    page.click('[data-zoom="in"]')
    page.click('[data-zoom="in"]')
    page.wait_for_timeout(120)
    assert page.locator("#zoom-value").inner_text() == "150%"

    after = relative_boxes(page)
    for measure_id, (x, y, w) in before.items():
        ax, ay, aw = after[measure_id]
        assert abs(ax - x) < ALIGNMENT_TOLERANCE, measure_id
        assert abs(ay - y) < ALIGNMENT_TOLERANCE, measure_id
        assert abs(aw - w) < ALIGNMENT_TOLERANCE, measure_id

    page.click('[data-zoom="reset"]')
    page.wait_for_timeout(120)


def test_highlights_preserve_notation_and_match_measure_regions(page):
    for width in (1400, 820):
        page.set_viewport_size({"width": width, "height": 900})
        checks = page.evaluate("""() => {
            const layer = getComputedStyle(document.querySelector('.layer--difficulty'));
            return {
                blend: layer.mixBlendMode,
                opacity: Number(layer.opacity),
                aligned: [...document.querySelectorAll('.difficulty-highlight')].every(el => {
                    const target = document.getElementById('hit-' + el.dataset.measureId);
                    const a = el.getBoundingClientRect(), b = target.getBoundingClientRect();
                    return Math.abs(a.x - b.x) < 1 && Math.abs(a.width - b.width) < 1
                        && Math.abs(a.height - b.height * 0.84) < 1
                        && Math.abs((a.y + a.height / 2) - (b.y + b.height / 2)) < 1;
                }),
            };
        }""")
        assert checks['blend'] == 'multiply'
        assert 0 < checks['opacity'] <= 0.2
        assert checks['aligned']
    assert page.locator('.ribbon-segment').count() == 0
    assert page.locator('.section-chip:visible').count() == 0
    page.set_viewport_size({"width": 1400, "height": 900})


def test_clicking_a_measure_selects_its_whole_passage(page):
    """The C17 rule: a click on the score resolves to a practice section."""
    target = page.locator(".measure").nth(7)
    measure_id = target.get_attribute("data-measure-id")
    section_id = target.get_attribute("data-section-id")
    assert section_id
    target.click()

    assert "is-selected" in (target.get_attribute("class") or "")
    assert page.locator(f'.phrase-item[data-phrase-id="{section_id}"].is-selected').count() == 1

    label = page.locator(
        f'.phrase-item[data-phrase-id="{section_id}"] .phrase-item-label'
    ).inner_text()
    assert page.locator("#sel-title").inner_text() == label

    # Every fragment of the passage lights up, on every system it touches.
    fragments = page.locator(f'.section-outline[data-section-id="{section_id}"]').count()
    selected = page.locator(
        f'.section-outline[data-section-id="{section_id}"].is-selected'
    ).count()
    assert fragments >= 1 and selected == fragments

    measure_label = target.locator(".measure-number").inner_text()
    assert f"measure {measure_label} selected" in page.locator("#sel-range").inner_text()
    assert measure_id in page.eval_on_selector_all(
        ".measure.is-selected", "els => els.map(e => e.dataset.measureId)"
    )


def test_two_measures_in_one_passage_select_the_same_passage(page):
    """Clicking different measures inside a passage must not change the answer."""
    pair = page.evaluate(
        """() => {
            const measures = Array.from(document.querySelectorAll('.measure'));
            const bySection = new Map();
            for (const el of measures) {
                const id = el.dataset.sectionId;
                if (!id) continue;
                (bySection.get(id) || bySection.set(id, []).get(id)).push(el.dataset.measureId);
            }
            for (const [sectionId, ids] of bySection) {
                if (ids.length >= 2) return [sectionId, ids[0], ids[ids.length - 1]];
            }
            return null;
        }"""
    )
    assert pair, "the example should contain a passage spanning several measures"
    section_id, first, last = pair

    def select(measure_id):
        page.locator(f'.measure[data-measure-id="{measure_id}"]').click()
        return {
            "title": page.locator("#sel-title").inner_text(),
            "range": page.locator("#sel-range").inner_text(),
            "selected": page.locator(".phrase-item.is-selected").get_attribute(
                "data-phrase-id"
            ),
        }

    a = select(first)
    b = select(last)
    assert a["selected"] == section_id
    assert b["selected"] == section_id
    assert a["title"] == b["title"]
    # Only the "measure N selected" tail differs, which is the point of keeping
    # it: the passage is the same, the measure you clicked is not.
    assert a["range"].split(" · ")[0] == b["range"].split(" · ")[0]


def test_different_passages_load_different_guidance(page):
    items = page.locator(".phrase-item--section")
    assert items.count() >= 2

    items.nth(0).click()
    page.wait_for_selector("#practice-body:not([hidden]), #practice-nofit:not([hidden])")
    first = page.locator("#selection-panel").inner_text()

    items.nth(1).click()
    page.wait_for_selector("#practice-body:not([hidden]), #practice-nofit:not([hidden])")
    second = page.locator("#selection-panel").inner_text()

    assert first != second


def test_keyboard_moves_and_selects_along_the_score(page):
    first = page.locator(".measure").first
    first.click()
    ids = page.eval_on_selector_all(".measure", "els => els.map(e => e.dataset.measureId)")

    page.keyboard.press("ArrowRight")
    assert page.locator(".measure.is-selected").get_attribute("data-measure-id") == ids[1]

    page.keyboard.press("ArrowDown")
    moved = page.locator(".measure.is-selected").get_attribute("data-measure-id")
    assert moved not in (ids[0], ids[1])

    page.keyboard.press("Home")
    assert page.locator(".measure.is-selected").get_attribute("data-measure-id") == ids[0]


def test_selecting_a_phrase_from_the_list_brings_it_into_view(page):
    item = page.locator(".phrase-item").last
    phrase_id = item.get_attribute("data-phrase-id")
    item.click()

    assert page.locator(f'.phrase-outline[data-phrase-id="{phrase_id}"].is-selected').count() >= 1
    selected = page.locator(".measure.is-selected")
    assert selected.get_attribute("data-phrase-id") == phrase_id
    assert selected.is_visible()


def test_unrated_measure_reports_that_it_is_unknown(page):
    """A measure nobody could read must say so, even inside a rated phrase."""
    unrated = page.locator(".measure--unrated").first
    label = unrated.locator(".measure-number").inner_text()
    unrated.click()

    notes = " ".join(
        page.eval_on_selector_all(
            "#sel-unrated, #sel-measure-note",
            "els => els.filter(e => !e.hidden).map(e => e.textContent)",
        )
    )
    assert f"Measure {label}" in notes or "Needs review" in notes
    assert "could not be read" in notes or "never read" in notes or "unrated" in notes


def test_phrase_outlines_can_be_hidden(page):
    page.uncheck("#toggle-phrases")
    assert page.locator(".layer--phrases.is-hidden").count() >= 1
    page.check("#toggle-phrases")
    assert page.locator(".layer--phrases.is-hidden").count() == 0
