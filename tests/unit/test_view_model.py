"""View-model invariants: ribbon continuity, ownership, and unit discipline.

Three properties are load-bearing for the interface and are pinned here rather
than checked by eye:

* the ribbon is one unbroken run per system, with widths taken from the real
  engraved measures;
* every coordinate leaves Python as a percentage, which is what makes zoom and
  resize free;
* an unrated measure is rendered as unknown, never as easy.
"""

from __future__ import annotations

import re

import pytest

from src.features.difficulty.colors import UNRATED_COLOR, UNRATED_LABEL, color_for
from src.features.score_viewer.view_model import (
    RIBBON_HEIGHT_FRAC,
    RIBBON_INSET_FRAC,
    build_view,
    client_payload,
    owning_phrase,
)
from src.schemas.analysis import AnalysisBundle
from src.schemas.geometry import Region
from src.schemas.score import (
    Anchor,
    Difficulty,
    Measure,
    Page,
    Phrase,
    PhraseBoundary,
    Score,
    System,
)
from src.server.analysis.example import EXAMPLE_PATH

STYLE = re.compile(r"([a-z]+):([-0-9.]+)%")


def parse_style(style: str) -> dict[str, float]:
    """Style strings must be pure percentages; anything else fails here."""
    parts = [p for p in style.split(";") if p]
    parsed: dict[str, float] = {}
    for part in parts:
        match = STYLE.fullmatch(part.strip())
        assert match, f"non-percentage unit in style: {part!r}"
        parsed[match.group(1)] = float(match.group(2))
    return parsed


# --------------------------------------------------------------------------
# Synthetic fixtures: geometry chosen so the assertions cannot pass by luck
# --------------------------------------------------------------------------


def make_bundle(
    widths: list[float],
    scores: list[float | None],
    *,
    qualities: list[str] | None = None,
) -> AnalysisBundle:
    """One system of deliberately unequal measures, laid end to end."""
    qualities = qualities or ["confident"] * len(widths)
    x = 0.05
    measures: list[Measure] = []
    for i, width in enumerate(widths):
        measures.append(
            Measure(
                id=f"t:m{i}",
                label=str(i + 1),
                ordinal=i,
                system_id="t:s0",
                region=Region(x=x, y=0.10, w=width, h=0.08),
                note_ids=[f"t:m{i}:n0"],
                quality=qualities[i],
            )
        )
        x += width

    system = System(
        id="t:s0",
        page_index=0,
        index=0,
        region=Region(x=0.05, y=0.10, w=x - 0.05, h=0.08),
        measure_ids=[m.id for m in measures],
    )
    page = Page(
        id="t:p0",
        index=0,
        width_px=1000,
        height_px=1400,
        render_dpi=200,
        image_url="/fixtures/pages/none.png",
        system_ids=[system.id],
    )
    score = Score(
        id="t",
        fingerprint="deadbeef",
        input_kind="example",
        title="Test",
        is_example=True,
        pages=[page],
        systems=[system],
        measures=measures,
    )
    ratings = {
        m.id: Difficulty(target_id=m.id, score=s, rubric_version="1.0")
        for m, s in zip(measures, scores)
    }
    return AnalysisBundle(score=score, measure_difficulty=ratings)


def test_ribbon_segments_are_flush_within_a_system():
    """Each segment ends exactly where the next begins: no hairline gaps."""
    view = build_view(make_bundle([0.30, 0.12, 0.25, 0.18], [1.0, 5.0, 8.0, 3.0]))
    segments = view.pages[0].systems[0].segments
    boxes = [parse_style(s.style) for s in segments]

    for left_box, right_box in zip(boxes, boxes[1:]):
        # Tolerance is the 4-decimal formatting bound. On a 1200px page that is
        # about a millionth of a pixel -- a gap that cannot be rendered.
        assert left_box["left"] + left_box["width"] == pytest.approx(
            right_box["left"], abs=2e-4
        )


def test_ribbon_spans_the_whole_system_and_nothing_more():
    view = build_view(make_bundle([0.30, 0.12, 0.25], [1.0, 5.0, 8.0]))
    system = view.pages[0].systems[0]
    system_box = parse_style(system.style)
    boxes = [parse_style(s.style) for s in system.segments]

    assert boxes[0]["left"] == pytest.approx(system_box["left"], abs=2e-4)
    assert boxes[-1]["left"] + boxes[-1]["width"] == pytest.approx(
        system_box["left"] + system_box["width"], abs=2e-4
    )


def test_segment_widths_follow_real_measure_widths():
    """Equal distribution is explicitly forbidden by the architecture notes."""
    view = build_view(make_bundle([0.30, 0.12, 0.25, 0.18], [1.0, 5.0, 8.0, 3.0]))
    widths = [parse_style(s.style)["width"] for s in view.pages[0].systems[0].segments]
    assert len(set(round(w, 3) for w in widths)) > 1
    assert widths[0] > widths[1]


def test_ribbon_sits_in_the_lower_band_of_its_system():
    """Below the staff, inside the system's own box, never over the next one."""
    view = build_view(make_bundle([0.30, 0.20], [2.0, 4.0]))
    system = view.pages[0].systems[0]
    system_box = parse_style(system.style)
    segment_box = parse_style(system.segments[0].style)

    expected_height = system_box["height"] * RIBBON_HEIGHT_FRAC
    expected_top = system_box["top"] + system_box["height"] * (
        1.0 - RIBBON_INSET_FRAC - RIBBON_HEIGHT_FRAC
    )
    assert segment_box["height"] == pytest.approx(expected_height, abs=2e-4)
    assert segment_box["top"] == pytest.approx(expected_top, abs=2e-4)
    assert segment_box["top"] + segment_box["height"] <= system_box["top"] + system_box["height"]


def test_unrated_measure_is_unknown_not_easy():
    """The distinction the spec insists on: None is not 0.0 and not green."""
    bundle = make_bundle(
        [0.25, 0.25], [None, 0.0], qualities=["unreadable", "confident"]
    )
    view = build_view(bundle)
    unrated, easy = view.pages[0].systems[0].measures

    assert unrated.is_rated is False
    assert unrated.score_text == UNRATED_LABEL
    assert unrated.color == UNRATED_COLOR
    assert easy.is_rated is True
    assert easy.score_text == "0.0"
    assert easy.color == color_for(0.0)
    assert unrated.color != easy.color

    segments = view.pages[0].systems[0].segments
    assert segments[0].is_rated is False and segments[1].is_rated is True


def test_every_measure_style_is_a_percentage():
    """The zoom guarantee in one assertion: no absolute unit ever leaves here."""
    view = build_view(make_bundle([0.3, 0.2, 0.2], [1.0, None, 6.0]))
    for system in view.pages[0].systems:
        parse_style(system.style)
        for measure in system.measures:
            parse_style(measure.style)
        for segment in system.segments:
            parse_style(segment.style)


def test_empty_system_produces_no_ribbon():
    bundle = make_bundle([0.3], [1.0])
    bundle.score.systems[0].measure_ids = []
    view = build_view(bundle)
    assert view.pages[0].systems[0].segments == []
    assert view.pages[0].systems[0].has_ribbon is False


# --------------------------------------------------------------------------
# Ownership: which phrase a measure click selects
# --------------------------------------------------------------------------


def phrase_over(pid: str, start: tuple[str, int], end: tuple[str, int], measures: list[str]) -> Phrase:
    boundary = PhraseBoundary(evidence=[], reason="test", confidence=0.5)
    return Phrase(
        id=pid,
        label=pid,
        structural_start=Anchor(measure_id=start[0], note_index=start[1]),
        structural_end=Anchor(measure_id=end[0], note_index=end[1]),
        practice_start=Anchor(measure_id=start[0], note_index=start[1]),
        practice_end=Anchor(measure_id=end[0], note_index=end[1]),
        start_boundary=boundary,
        end_boundary=boundary,
        measure_ids=measures,
    )


def test_measure_click_selects_the_phrase_owning_its_first_note():
    """A boundary inside a measure: the measure belongs to the earlier phrase."""
    bundle = make_bundle([0.25, 0.25, 0.25], [3.0, 4.0, 5.0])
    # Phrase A ends partway through measure 2; phrase B starts in the same
    # measure. Measure 2's first note is inside A, so a click on it selects A.
    bundle.phrases = [
        phrase_over("A", ("t:m0", 0), ("t:m1", 3), ["t:m0", "t:m1"]),
        phrase_over("B", ("t:m1", 4), ("t:m2", 7), ["t:m1", "t:m2"]),
    ]
    score = bundle.score
    assert owning_phrase(score, bundle.phrases, score.measures[1]).id == "A"

    view = build_view(bundle)
    by_id = {m.id: m for s in view.pages[0].systems for m in s.measures}
    assert by_id["t:m1"].phrase_id == "A"
    # The split is shown rather than resolved away: this measure both ends one
    # phrase and starts the next, and is marked on both counts so the boundary
    # is visible. Phrase B stays reachable from its outline and the phrase list.
    assert by_id["t:m1"].ends_phrase is True
    assert by_id["t:m1"].starts_phrase is True
    assert by_id["t:m0"].starts_phrase is True and by_id["t:m0"].ends_phrase is False


def test_unreadable_measure_belongs_to_no_phrase():
    bundle = make_bundle([0.25, 0.25], [None, 4.0], qualities=["unreadable", "confident"])
    bundle.phrases = [phrase_over("A", ("t:m1", 0), ("t:m1", 7), ["t:m1"])]
    view = build_view(bundle)
    by_id = {m.id: m for s in view.pages[0].systems for m in s.measures}
    assert by_id["t:m0"].phrase_id is None
    assert by_id["t:m1"].phrase_id == "A"


# --------------------------------------------------------------------------
# The real fixture
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def example_view():
    return build_view(AnalysisBundle.load_path(EXAMPLE_PATH))


def test_example_ribbon_is_continuous_on_every_system(example_view):
    for system in example_view.pages[0].systems:
        boxes = [parse_style(s.style) for s in system.segments]
        for left_box, right_box in zip(boxes, boxes[1:]):
            assert left_box["left"] + left_box["width"] == pytest.approx(
                right_box["left"], abs=2e-4
            )


def test_example_ribbon_covers_every_measure(example_view):
    segment_ids = {
        s.measure_id for system in example_view.pages[0].systems for s in system.segments
    }
    measure_ids = {
        m.id for system in example_view.pages[0].systems for m in system.measures
    }
    assert segment_ids == measure_ids
    assert len(segment_ids) == example_view.measure_total


def test_example_phrase_crossing_systems_has_one_fragment_per_system(example_view):
    crossing = [p for p in example_view.phrases if p.fragment_count > 1]
    assert crossing, "the fixture is expected to contain phrases that cross systems"
    for phrase in crossing:
        boxes = [parse_style(style) for style in phrase.region_styles]
        tops = sorted(box["top"] for box in boxes)
        # Distinct vertical bands, not one box swallowing the notation between.
        for upper, lower in zip(tops, tops[1:]):
            assert lower > upper


def test_example_unrated_measures_stay_unrated(example_view):
    unrated = [
        m
        for system in example_view.pages[0].systems
        for m in system.measures
        if not m.is_rated
    ]
    assert unrated, "the fixture is expected to contain measures recognition could not read"
    for measure in unrated:
        assert measure.score_text == UNRATED_LABEL
        assert measure.color == UNRATED_COLOR
        assert measure.quality in ("unreadable", "not_attempted", "non_musical")


def test_example_ratings_render_to_one_decimal(example_view):
    for phrase in example_view.phrases:
        if phrase.is_rated:
            assert re.fullmatch(r"\d+\.\d", phrase.score_text), phrase.score_text
    for system in example_view.pages[0].systems:
        for measure in system.measures:
            if measure.is_rated:
                assert re.fullmatch(r"\d+\.\d", measure.score_text), measure.score_text


def test_example_client_payload_covers_the_rendered_score(example_view):
    payload = client_payload(example_view)
    rendered_measures = {
        m.id for system in example_view.pages[0].systems for m in system.measures
    }
    assert set(payload["measures"]) == rendered_measures
    assert set(payload["phrases"]) == {p.id for p in example_view.phrases}
    assert payload["measureOrder"] == sorted(
        payload["measureOrder"],
        key=lambda mid: [m.ordinal for s in example_view.pages[0].systems for m in s.measures if m.id == mid][0],
    )
    assert payload["defaultPhraseId"] in payload["phrases"]


def test_example_legend_shows_every_category_including_unrated(example_view):
    labels = [entry["label"] for entry in example_view.legend]
    assert labels[-1] == UNRATED_LABEL
    assert len(labels) == 6


# --------------------------------------------------------------------------
# The rubric disclosure
# --------------------------------------------------------------------------


def test_rubric_disclosure_is_built_from_the_weights_that_rate(example_view):
    """The explanation cannot drift from the code, because it reads from it."""
    from src.features.difficulty.rubric import LABELS, WEIGHTS

    rubric = example_view.rubric
    assert {w["label"] for w in rubric["weights"]} == set(LABELS.values())
    for entry in rubric["weights"]:
        key = next(k for k, v in LABELS.items() if v == entry["label"])
        assert entry["weight"] == f"{WEIGHTS[key]:.1f}"
    assert f"{sum(WEIGHTS.values()):.1f}" in rubric["scale"]


def test_rubric_names_what_it_cannot_see(example_view):
    """A rating shown without its blind spots invites over-reading."""
    blind = " ".join(example_view.rubric["blindSpots"]).lower()
    for absent in ("fingering", "string", "shift", "bow", "hand"):
        assert absent in blind


def test_rubric_states_that_no_violinist_has_reviewed_it(example_view):
    assert "no violinist has reviewed" in example_view.rubric["review"].lower()


def test_every_factor_reports_the_weight_it_came_from(example_view):
    from src.features.difficulty.rubric import WEIGHTS

    seen = 0
    for phrase in example_view.phrases:
        for factor in phrase.factors:
            assert factor.weight, factor.label
            assert float(factor.weight) in WEIGHTS.values()
            assert factor.share.endswith("%")
            seen += 1
    assert seen, "the example should expose some rating factors"


def test_a_supplied_tempo_is_not_reported_back_as_an_assumption():
    """`tempo_is_assumed` means the page prints none; it is not about the user."""
    from src.server.analysis.recompute import retune

    bundle = AnalysisBundle.load_path(EXAMPLE_PATH)
    assumed = build_view(retune(bundle, None), supplied_tempo=None)
    supplied = build_view(retune(bundle, 160.0), supplied_tempo=160.0)

    assert "assumed" in assumed.rubric["tempo"]
    assert "90" in assumed.rubric["tempo"]
    assert "you supplied" in supplied.rubric["tempo"]
    assert "160" in supplied.rubric["tempo"]
    assert "assumed" not in supplied.rubric["tempo"]
