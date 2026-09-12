"""Rubric, colour mapping and aggregation invariants.

The boundary cases here are the ones docs/safe-execution.md names explicitly as
quality gates: the six anchor values, the category edges, and missing data.
"""

from __future__ import annotations

import pytest

from src.features.difficulty.colors import (
    ANCHORS,
    CATEGORIES,
    UNRATED_COLOR,
    UNRATED_LABEL,
    category_for,
    color_for,
    format_score,
    legend,
)
from src.features.difficulty.rubric import (
    RUBRIC_VERSION,
    aggregate_phrase,
    rate_measure,
)
from src.schemas.music import NoteEvent


def n(step: str, octave: int, value: str = "eighth", **kw) -> NoteEvent:
    return NoteEvent(is_rest=False, step=step, octave=octave, value=value, **kw)


# --------------------------------------------------------------------------
# Colour anchors and categories
# --------------------------------------------------------------------------


@pytest.mark.parametrize("score,expected_hex", ANCHORS)
def test_anchor_values_reproduce_exactly(score, expected_hex):
    """Every anchor in docs/design.md must come back byte-identical."""
    assert color_for(score).upper() == expected_hex.upper()


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.0, "Beginner-friendly"),
        (1.9, "Beginner-friendly"),
        (2.0, "Advanced Beginner"),
        (3.9, "Advanced Beginner"),
        (4.0, "Competent level"),
        (5.9, "Competent level"),
        (6.0, "Expert level"),
        (7.9, "Expert level"),
        (8.0, "Extremely, extremely hard"),
        (10.0, "Extremely, extremely hard"),
    ],
)
def test_category_boundaries_are_half_open(score, expected):
    """Exactly 2.0 is Advanced Beginner, not Beginner-friendly."""
    assert category_for(score) == expected


def test_interpolation_between_anchors_moves_toward_the_next_anchor():
    mid = color_for(1.0)
    assert mid.upper() not in {ANCHORS[0][1].upper(), ANCHORS[1][1].upper()}
    # Green channel falls and red rises on the way from green to yellow.
    g0 = int(ANCHORS[0][1][3:5], 16)
    g1 = int(ANCHORS[1][1][3:5], 16)
    gm = int(mid[3:5], 16)
    assert min(g0, g1) <= gm <= max(g0, g1)


def test_out_of_range_scores_clamp_rather_than_raise():
    assert color_for(-5).upper() == ANCHORS[0][1].upper()
    assert color_for(99).upper() == ANCHORS[-1][1].upper()


# --------------------------------------------------------------------------
# Missing data is not zero
# --------------------------------------------------------------------------


def test_unrated_is_visually_distinct_from_easy():
    """None must not render as green. This is the whole point of keeping it None."""
    assert color_for(None) == UNRATED_COLOR
    assert color_for(None).upper() != color_for(0.0).upper()
    assert category_for(None) == UNRATED_LABEL
    assert format_score(None) == UNRATED_LABEL


def test_zero_is_a_real_rating_not_a_missing_one():
    assert format_score(0.0) == "0.0"
    assert category_for(0.0) == "Beginner-friendly"


def test_scores_always_show_one_decimal():
    assert format_score(6.0) == "6.0"
    assert format_score(6.75) == "6.8"
    assert format_score(10.0) == "10.0"


def test_legend_shows_every_category_plus_unrated():
    entries = legend()
    assert [e["label"] for e in entries[:-1]] == [c[2] for c in CATEGORIES]
    assert entries[-1]["label"] == UNRATED_LABEL


# --------------------------------------------------------------------------
# Rubric behaviour
# --------------------------------------------------------------------------


def test_rating_is_in_range_and_one_decimal():
    notes = [n("G", 4) for _ in range(8)]
    score, _ = rate_measure(notes, 4, 4)
    assert 0.0 <= score <= 10.0
    assert round(score, 1) == score


def test_rating_is_deterministic():
    notes = [n("G", 4), n("A", 4), n("B", 4), n("C", 5)]
    a, fa = rate_measure(notes, 4, 4)
    b, fb = rate_measure(notes, 4, 4)
    assert a == b
    assert [f.model_dump() for f in fa] == [f.model_dump() for f in fb]


def test_faster_notes_rate_higher_than_slower_ones():
    slow = [n("G", 4, "quarter") for _ in range(4)]
    fast = [n("G", 4, "16th") for _ in range(16)]
    assert rate_measure(fast, 4, 4)[0] > rate_measure(slow, 4, 4)[0]


def test_higher_register_rates_higher():
    low = [n("G", 4) for _ in range(8)]
    high = [n("G", 6) for _ in range(8)]
    assert rate_measure(high, 4, 4)[0] > rate_measure(low, 4, 4)[0]


def test_accidentals_raise_the_rating():
    plain = [n("G", 4) for _ in range(8)]
    chromatic = [n("G", 4, alter=1) for _ in range(8)]
    assert rate_measure(chromatic, 4, 4)[0] > rate_measure(plain, 4, 4)[0]


def test_a_faster_stated_tempo_raises_the_rating():
    notes = [n("G", 4) for _ in range(8)]
    assert rate_measure(notes, 4, 4, tempo_bpm=160)[0] > rate_measure(notes, 4, 4, tempo_bpm=60)[0]


def test_empty_measure_rates_zero_without_raising():
    score, factors = rate_measure([], 4, 4)
    assert score == 0.0
    assert factors == []


def test_factors_are_reported_in_descending_contribution():
    notes = [n("C", 6, "32nd", alter=1) for _ in range(8)]
    _, factors = rate_measure(notes, 4, 4)
    assert factors, "a demanding measure should explain itself"
    contributions = [f.contribution for f in factors]
    assert contributions == sorted(contributions, reverse=True)


def test_rubric_version_is_recorded():
    assert RUBRIC_VERSION == "1.0"


# --------------------------------------------------------------------------
# Phrase aggregation
# --------------------------------------------------------------------------


def test_a_brief_obstacle_is_not_averaged_away():
    """The reason aggregation is peak-biased rather than a plain mean."""
    easy_with_spike = [1.0, 1.0, 1.0, 9.0]
    combined, peak = aggregate_phrase(easy_with_spike)
    plain_mean = sum(easy_with_spike) / len(easy_with_spike)
    assert peak == 9.0
    assert combined > plain_mean


def test_aggregate_skips_unrated_members_rather_than_counting_them_as_zero():
    with_hole = aggregate_phrase([4.0, None, 4.0])
    without = aggregate_phrase([4.0, 4.0])
    assert with_hole == without


def test_phrase_with_no_rated_measure_stays_unrated():
    assert aggregate_phrase([None, None]) == (None, None)
    assert aggregate_phrase([]) == (None, None)


def test_aggregate_stays_in_range_and_one_decimal():
    combined, peak = aggregate_phrase([9.9, 10.0, 8.0])
    assert combined is not None and peak is not None
    assert 0.0 <= combined <= 10.0
    assert round(combined, 1) == combined
