"""Trouble spots: the third level, and the restraint that makes it useful.

The interesting assertions here are the negative ones. A trouble spot marked on
every phrase would be noise — it would tell a player to isolate a passage that
is not, locally, the problem. So most of this file checks that nothing is marked
when nothing stands out.
"""

from __future__ import annotations

import pytest

from src.features.segmentation.phrases import (
    LOCAL_PEAK_MARGIN,
    MAX_SPOT_MEASURES,
    MIN_PHRASE_MEASURES_FOR_SPOT,
    find_trouble_spots,
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
from src.server.analysis.recompute import retune


def build(scores: list[float | None], *, systems: int = 1) -> tuple[Score, list[Phrase], dict]:
    """One phrase over N measures with the given ratings."""
    measures: list[Measure] = []
    x = 0.05
    for i, _ in enumerate(scores):
        system_index = i * systems // max(1, len(scores))
        measures.append(
            Measure(
                id=f"t:m{i}",
                label=str(i + 1),
                ordinal=i,
                system_id=f"t:s{system_index}",
                region=Region(x=x, y=0.1 + 0.2 * system_index, w=0.1, h=0.08),
                note_ids=[f"t:m{i}:n0", f"t:m{i}:n1"],
            )
        )
        x += 0.1

    system_ids = sorted({m.system_id for m in measures})
    score = Score(
        id="t",
        fingerprint="f",
        input_kind="example",
        pages=[Page(id="t:p0", index=0, width_px=1000, height_px=1400, render_dpi=200)],
        systems=[
            System(
                id=sid,
                page_index=0,
                index=n,
                region=Region(x=0.05, y=0.1 + 0.2 * n, w=0.9, h=0.08),
                measure_ids=[m.id for m in measures if m.system_id == sid],
            )
            for n, sid in enumerate(system_ids)
        ],
        measures=measures,
    )
    boundary = PhraseBoundary(evidence=[], reason="test", confidence=0.5)
    phrase = Phrase(
        id="t:ph000",
        label="Phrase 1",
        structural_start=Anchor(measure_id=measures[0].id, note_index=0),
        structural_end=Anchor(measure_id=measures[-1].id, note_index=1),
        practice_start=Anchor(measure_id=measures[0].id, note_index=0),
        practice_end=Anchor(measure_id=measures[-1].id, note_index=1),
        start_boundary=boundary,
        end_boundary=boundary,
        measure_ids=[m.id for m in measures],
    )
    ratings = {
        m.id: Difficulty(target_id=m.id, score=s, rubric_version="1.0")
        for m, s in zip(measures, scores)
    }
    return score, [phrase], ratings


# --------------------------------------------------------------------------
# Restraint
# --------------------------------------------------------------------------


def test_a_uniformly_hard_phrase_gets_no_spot():
    """If everything is hard, nothing is locally hard."""
    score, phrases, ratings = build([7.0, 7.0, 7.1, 6.9, 7.0])
    assert find_trouble_spots(score, phrases, ratings) == []


def test_a_uniformly_easy_phrase_gets_no_spot():
    score, phrases, ratings = build([1.0, 1.1, 1.0, 0.9])
    assert find_trouble_spots(score, phrases, ratings) == []


def test_a_rise_below_the_margin_is_not_a_spot():
    score, phrases, ratings = build([4.0, 4.0, 4.0 + LOCAL_PEAK_MARGIN / 2, 4.0])
    assert find_trouble_spots(score, phrases, ratings) == []


@pytest.mark.parametrize("measures", range(1, MIN_PHRASE_MEASURES_FOR_SPOT))
def test_a_phrase_too_short_to_have_an_inside_gets_no_spot(measures):
    """With two measures the 'peak' is half the phrase, which localises nothing."""
    ratings = [3.0] * (measures - 1) + [9.0]
    score, phrases, rated = build(ratings)
    assert find_trouble_spots(score, phrases, rated) == []


def test_the_threshold_length_does_get_a_spot():
    """One measure either side of the peak is the minimum that means anything."""
    score, phrases, ratings = build([3.0] * (MIN_PHRASE_MEASURES_FOR_SPOT - 1) + [9.0])
    assert len(find_trouble_spots(score, phrases, ratings)) == 1


def test_unrated_measures_do_not_create_a_spot():
    """A measure nobody could read is unknown, never a local peak."""
    score, phrases, ratings = build([3.0, None, 3.0, None, 3.1])
    assert find_trouble_spots(score, phrases, ratings) == []


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------


def test_one_clear_peak_yields_exactly_one_spot_covering_it():
    score, phrases, ratings = build([3.0, 3.0, 7.0, 3.0, 3.0])
    spots = find_trouble_spots(score, phrases, ratings)
    assert len(spots) == 1
    spot = spots[0]
    assert spot.measure_ids == ["t:m2"]
    assert spot.level == "trouble_spot"
    assert spot.parent_id == "t:ph000"


def test_a_spot_never_exceeds_the_short_range_it_is_defined_as():
    score, phrases, ratings = build([3.0, 8.0, 8.0, 8.0, 8.0, 3.0])
    spot = find_trouble_spots(score, phrases, ratings)[0]
    assert len(spot.measure_ids) <= MAX_SPOT_MEASURES


def test_at_most_one_spot_per_phrase():
    score, phrases, ratings = build([3.0, 8.0, 3.0, 8.0, 3.0])
    assert len(find_trouble_spots(score, phrases, ratings)) == 1


def test_the_reason_quotes_the_numbers_it_was_derived_from():
    score, phrases, ratings = build([3.0, 3.0, 7.0, 3.0, 3.0])
    reason = find_trouble_spots(score, phrases, ratings)[0].start_boundary.reason
    assert "7.0" in reason and "against" in reason


def test_a_spot_borrows_nothing_from_the_next_phrase():
    """Practice overlap is a phrase-level rule; a spot is a range to isolate."""
    score, phrases, ratings = build([3.0, 3.0, 7.0, 3.0, 3.0])
    spot = find_trouble_spots(score, phrases, ratings)[0]
    assert spot.has_practice_overlap is False
    assert spot.practice_end == spot.structural_end


def test_a_spot_crossing_a_system_gets_one_fragment_per_system():
    score, phrases, ratings = build([3.0, 3.0, 8.0, 8.0, 3.0, 3.0], systems=2)
    spot = find_trouble_spots(score, phrases, ratings)[0]
    system_ids = {score.measure(mid).system_id for mid in spot.measure_ids}
    assert len(spot.regions) == len(system_ids)


# --------------------------------------------------------------------------
# Against the real score, and against tempo
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bundle() -> AnalysisBundle:
    return AnalysisBundle.load_path(EXAMPLE_PATH)


def test_the_example_yields_some_spots_but_not_one_per_phrase(bundle):
    retuned = retune(bundle, None)
    phrases = [p for p in retuned.phrases if p.level == "phrase"]
    spots = [p for p in retuned.phrases if p.level == "trouble_spot"]
    assert spots, "the example should contain at least one local obstacle"
    assert len(spots) < len(phrases), "a spot in every phrase would be noise"


def test_every_spot_sits_inside_its_parent(bundle):
    retuned = retune(bundle, None)
    by_id = {p.id: p for p in retuned.phrases}
    for spot in (p for p in retuned.phrases if p.level == "trouble_spot"):
        parent = by_id[spot.parent_id]
        assert parent.level == "phrase"
        assert set(spot.measure_ids) <= set(parent.measure_ids)


def test_spots_are_rated_like_any_other_target(bundle):
    retuned = retune(bundle, None)
    for spot in (p for p in retuned.phrases if p.level == "trouble_spot"):
        assert retuned.phrase_difficulty[spot.id].score is not None


def test_spots_are_re_derived_when_the_tempo_changes(bundle):
    """A spot saved at one tempo would be wrong at another, so none is saved."""
    slow = {p.id for p in retune(bundle, 60.0).phrases if p.level == "trouble_spot"}
    fast = {p.id for p in retune(bundle, 200.0).phrases if p.level == "trouble_spot"}
    assert slow != fast, "tempo changes which measures stand out locally"


def test_retuning_twice_does_not_accumulate_spots(bundle):
    once = retune(bundle, 120.0)
    twice = retune(once, 120.0)
    count = lambda b: sum(1 for p in b.phrases if p.level == "trouble_spot")  # noqa: E731
    assert count(once) == count(twice)
