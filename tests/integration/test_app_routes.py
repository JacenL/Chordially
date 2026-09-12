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


def test_every_measure_has_a_ribbon_segment_and_a_hit_target(client):
    html = client.get("/score/example").text
    data = payload_of(html)
    segments = re.findall(r'class="ribbon-segment[^"]*"\s+style="[^"]*"\s+data-measure-id="([^"]+)"', html)
    hits = re.findall(r'data-measure-id="([^"]+)"\s+data-system-id=', html)
    assert set(segments) == set(data["measures"])
    assert set(hits) == set(data["measures"])


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
