"""Editing practice-section boundaries through the real endpoints.

The controls act on the passage, which is what the score is coloured by and what
a click selects. What is stored is not a section -- sections are re-derived on
every request, because they group phrases by difficulty and by demand and both
move with tempo -- but the decision behind it, keyed by a measure id.

These tests go through the HTTP surface rather than calling the edit functions,
because the thing that has to hold is that the *page* changes: a split that is
recorded but not rendered would pass a unit test and fail the user.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from src.app.main import app
from src.server.analysis import store


@pytest.fixture()
def client():
    store.clear("example")
    with TestClient(app) as c:
        yield c
    store.clear("example")


def payload_of(html: str) -> dict:
    match = re.search(
        r'<script id="score-data" type="application/json">(.*?)</script>', html, re.S
    )
    assert match
    return json.loads(
        match.group(1)
        .replace("\\u003c", "<")
        .replace("\\u003e", ">")
        .replace("\\u0026", "&")
    )


def sections_of(client: TestClient) -> list[dict]:
    data = payload_of(client.get("/score/example").text)
    return [p for p in data["phrases"].values() if p["level"] == "section"]


def test_splitting_a_passage_shows_a_new_passage_on_the_page(client):
    before = sections_of(client)
    assert before, "the example should already group into passages"
    target = before[0]
    at = target["measureIds"][len(target["measureIds"]) // 2]

    response = client.post("/api/sections/example/split", params={"at_measure_id": at})
    assert response.status_code == 200, response.text

    after = sections_of(client)
    assert len(after) == len(before) + 1
    new = next(s for s in after if s["measureIds"][0] == at)
    assert new["userEdited"] is True
    assert "you split the section here" in new["startReason"]


def test_a_split_passage_covers_the_same_music_between_the_two_halves(client):
    before = sections_of(client)
    target = before[0]
    original = list(target["measureIds"])
    at = original[len(original) // 2]

    client.post("/api/sections/example/split", params={"at_measure_id": at})
    after = sections_of(client)

    halves = [s for s in after if set(s["measureIds"]) <= set(original)]
    covered = [mid for s in halves for mid in s["measureIds"]]
    assert sorted(covered) == sorted(original)
    assert len(covered) == len(set(covered)), "a measure now belongs to two passages"


def test_splitting_mid_phrase_splits_the_phrase_too(client):
    """A section groups whole phrases, so the phrase has to give way first."""
    data = payload_of(client.get("/score/example").text)
    phrases = [p for p in data["phrases"].values() if p["level"] == "phrase"]
    mid_phrase = next(p for p in phrases if len(p["measureIds"]) > 1)
    at = mid_phrase["measureIds"][1]

    assert client.post(
        "/api/sections/example/split", params={"at_measure_id": at}
    ).status_code == 200

    after = payload_of(client.get("/score/example").text)
    starts = {p["measureIds"][0] for p in after["phrases"].values() if p["level"] == "phrase"}
    assert at in starts, "the phrase was not split, so the section boundary cannot land"


def test_merging_removes_a_boundary_including_a_printed_one(client):
    """The evidence is still reported; the user is allowed to disagree with it."""
    before = sections_of(client)
    assert len(before) >= 2
    first = before[0]

    response = client.post(
        "/api/sections/example/merge", params={"section_id": first["id"]}
    )
    assert response.status_code == 200, response.text

    after = sections_of(client)
    assert len(after) == len(before) - 1
    assert set(before[0]["measureIds"]) | set(before[1]["measureIds"]) == set(
        after[0]["measureIds"]
    )


def test_merging_the_last_passage_is_refused_with_a_reason(client):
    sections = sections_of(client)
    response = client.post(
        "/api/sections/example/merge", params={"section_id": sections[-1]["id"]}
    )
    assert response.status_code == 409
    assert "last passage" in response.json()["detail"]


def test_splitting_at_the_first_measure_is_refused_with_a_reason(client):
    data = payload_of(client.get("/score/example").text)
    first_measure = data["measureOrder"][0]
    response = client.post(
        "/api/sections/example/split", params={"at_measure_id": first_measure}
    )
    assert response.status_code == 409
    assert "already begins" in response.json()["detail"]


def test_reset_returns_to_the_derived_grouping(client):
    before = sections_of(client)
    at = before[0]["measureIds"][1]
    client.post("/api/sections/example/split", params={"at_measure_id": at})
    assert len(sections_of(client)) == len(before) + 1

    assert client.post("/api/sections/example/reset").status_code == 200
    after = sections_of(client)
    assert [s["measureIds"] for s in after] == [s["measureIds"] for s in before]


def test_an_edit_survives_a_tempo_change(client):
    """Sections are re-derived at the new tempo; the user's decision is not."""
    before = sections_of(client)
    at = before[0]["measureIds"][1]
    client.post("/api/sections/example/split", params={"at_measure_id": at})

    retuned = payload_of(client.get("/score/example?tempo=160").text)
    starts = {
        s["measureIds"][0] for s in retuned["phrases"].values() if s["level"] == "section"
    }
    assert at in starts


def bands_of(html: str) -> list[tuple[str, list[str]]]:
    """(section id, covered measure ids) for each rendered ribbon band."""
    found = re.findall(
        r'data-measure-ids="([^"]*)"\s*(?:data-section-id="([^"]+)")?', html
    )
    return [(section or "", ids.split()) for ids, section in found]


def test_an_edit_keeps_the_ribbon_and_the_selection_in_step(client):
    """A split has to change the colouring, not just the list.

    Band *count* is not the thing to assert: bands are cut at every staff
    system anyway, so a split that happens to land on a line break adds none.
    What must change is which passage the bands belong to.
    """
    sections = sections_of(client)
    original = list(sections[0]["measureIds"])
    at = original[len(original) // 2]

    before = bands_of(client.get("/score/example").text)
    before_owners = {
        section for section, ids in before if set(ids) & set(original)
    }
    assert len(before_owners) == 1

    client.post("/api/sections/example/split", params={"at_measure_id": at})

    after_html = client.get("/score/example").text
    after = bands_of(after_html)
    after_owners = {section for section, ids in after if set(ids) & set(original)}
    assert len(after_owners) == 2, "the split did not reach the ribbon"

    covered = [mid for _, ids in after for mid in ids]
    data = payload_of(after_html)
    assert set(covered) == set(data["measures"])
    assert len(covered) == len(set(covered))
    for measure in data["measures"].values():
        assert measure["sectionId"] in data["phrases"]
