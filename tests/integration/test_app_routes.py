"""HTTP contracts for the viewer.

The condition worth guarding hardest is the credential one: example mode must
work with the application's key unset, and must not quietly borrow an ambient
ANTHROPIC_API_KEY to do it.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from src.app.main import app
from src.features.difficulty.colors import UNRATED_LABEL

PAYLOAD = re.compile(
    r'<script id="score-data" type="application/json">(.*?)</script>', re.S
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def payload_of(html: str) -> dict:
    match = PAYLOAD.search(html)
    assert match, "the page must embed its selection data"
    return json.loads(match.group(1))


def test_index_offers_the_example_and_says_upload_is_not_ready(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "/score/example" in response.text
    # The upload control exists but is disabled and labelled, so nothing claims
    # a capability this build does not have.
    assert "disabled" in response.text


def test_example_renders_over_its_original_scan(client):
    response = client.get("/score/example")
    assert response.status_code == 200
    assert 'class="page-image"' in response.text
    assert "/fixtures/pages/wohlfahrt-p3.png" in response.text


def test_example_is_labelled_as_the_example(client):
    response = client.get("/score/example")
    assert "Example score" in response.text


def test_page_image_is_served(client):
    response = client.get("/fixtures/pages/wohlfahrt-p3.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_the_ribbon_accounts_for_every_measure_and_every_measure_is_clickable(client):
    """Bands are passages, so coverage is the invariant, not one band per measure."""
    html = client.get("/score/example").text
    data = payload_of(html)
    bands = re.findall(r'data-measure-ids="([^"]*)"', html)
    covered = [mid for band in bands for mid in band.split() if mid]
    hits = re.findall(r'data-measure-id="([^"]+)"\s+data-system-id=', html)

    assert set(covered) == set(data["measures"])
    assert len(covered) == len(set(covered)), "a measure is covered by two bands"
    assert set(hits) == set(data["measures"])
    assert len(bands) < len(data["measures"]), (
        "there is still roughly one band per measure, which is the heatmap C17 removed"
    )


def test_every_measure_resolves_to_a_passage(client):
    """Clicking anywhere on the score has to land on something selectable."""
    data = payload_of(client.get("/score/example").text)
    for measure_id, measure in data["measures"].items():
        assert measure["sectionId"], f"{measure_id} belongs to no passage"
        assert measure["sectionId"] in data["phrases"]


def test_a_passage_crossing_systems_keeps_one_identity_rating_and_colour(client):
    """Linked fragments, not several regions that happen to look alike."""
    html = client.get("/score/example").text
    fragments = re.findall(
        r'class="section-outline[^"]*"\s+style="([^"]*)"\s+data-section-id="([^"]+)"', html
    )
    by_section: dict[str, list[str]] = {}
    for style, section_id in fragments:
        by_section.setdefault(section_id, []).append(style)

    crossing = {k: v for k, v in by_section.items() if len(v) > 1}
    assert crossing, "the example is expected to contain a passage crossing systems"
    for section_id, styles in crossing.items():
        colours = {re.search(r"--section-color:([^;\"]+)", style).group(1) for style in styles}
        assert len(colours) == 1, (section_id, colours)


def test_unrated_measures_render_as_needing_review(client):
    html = client.get("/score/example").text
    data = payload_of(html)
    unrated = [m for m in data["measures"].values() if not m["isRated"]]
    assert unrated, "the fixture contains measures recognition could not read"
    for measure in unrated:
        assert measure["scoreText"] == UNRATED_LABEL
    assert "ribbon-segment--unrated" in html


def test_recognition_warnings_are_shown_not_hidden(client):
    html = client.get("/score/example").text
    assert "could not be read reliably" in html
    assert "never read" in html


def test_measures_have_one_tab_stop_between_them(client):
    """Roving tabindex: 61 measures must not become 61 tab stops."""
    html = client.get("/score/example").text
    hit_targets = re.findall(r'<button type="button"\s+class="measure[^"]*"', html)
    assert len(hit_targets) > 50
    assert html.count('tabindex="-1"') >= len(hit_targets)


def test_embedded_payload_cannot_close_the_script_tag(client):
    """Provider text is data. It must not be able to become markup."""
    html = client.get("/score/example").text
    body = PAYLOAD.search(html).group(1)
    assert "</script" not in body.lower()
    assert "<" not in body


def test_example_mode_works_without_application_credentials(monkeypatch):
    """The app's own key unset, an unrelated ambient key deliberately present."""
    monkeypatch.delenv("PRACTICEMAP_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-not-this-applications-key")
    with TestClient(app) as unauthenticated:
        assert unauthenticated.get("/health").json()["live_recognition"] is False
        response = unauthenticated.get("/score/example")
        assert response.status_code == 200
        assert 'class="ribbon-segment' in response.text
