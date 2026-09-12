"""Tempo recalculation: the rating scale's dependence on tempo, made usable.

Two of these tests exist because of a specific hazard rather than a feature.
`load_example` is lru_cached, so one request retuning the shared bundle in place
would change every other user's page; and a printed tempo is evidence off the
score that a global setting must not overwrite.
"""

from __future__ import annotations

import pytest

from src.features.difficulty.rubric import DEFAULT_TEMPO_BPM
from src.schemas.analysis import AnalysisBundle
from src.server.analysis.example import EXAMPLE_PATH, load_example
from src.server.analysis.recompute import (
    MAX_TEMPO_BPM,
    MIN_TEMPO_BPM,
    TempoOutOfRange,
    parse_tempo,
    retune,
)


@pytest.fixture(scope="module")
def bundle() -> AnalysisBundle:
    return AnalysisBundle.load_path(EXAMPLE_PATH)


def rated_scores(b: AnalysisBundle) -> dict[str, float]:
    return {k: d.score for k, d in b.measure_difficulty.items() if d.score is not None}


# --------------------------------------------------------------------------
# The rating actually moves, and in the right direction
# --------------------------------------------------------------------------


def test_a_faster_tempo_never_lowers_a_rating(bundle):
    slow = rated_scores(retune(bundle, 60.0))
    fast = rated_scores(retune(bundle, 160.0))
    assert set(slow) == set(fast)
    assert all(fast[k] >= slow[k] for k in slow)
    assert any(fast[k] > slow[k] for k in slow), "tempo must change something"


def test_phrase_ratings_follow_their_measures(bundle):
    """Compared over phrases only: trouble spots legitimately differ by tempo."""
    slow = retune(bundle, 60.0)
    fast = retune(bundle, 160.0)
    phrase_ids = [p.id for p in slow.phrases if p.level == "phrase"]
    assert phrase_ids

    for pid in phrase_ids:
        slow_rating, fast_rating = slow.phrase_difficulty[pid], fast.phrase_difficulty[pid]
        if slow_rating.score is None or fast_rating.score is None:
            assert slow_rating.score is None and fast_rating.score is None
            continue
        assert fast_rating.score >= slow_rating.score


def test_phrase_set_is_stable_across_tempo(bundle):
    """Tempo re-rates the music; it must not re-segment it."""
    slow = {p.id for p in retune(bundle, 60.0).phrases if p.level == "phrase"}
    fast = {p.id for p in retune(bundle, 160.0).phrases if p.level == "phrase"}
    assert slow == fast


def test_retuning_to_none_restores_the_assumed_tempo(bundle):
    assumed = rated_scores(retune(bundle, None))
    explicit = rated_scores(retune(bundle, DEFAULT_TEMPO_BPM))
    assert assumed == explicit


def test_unrated_measures_stay_unrated_at_every_tempo(bundle):
    for tempo in (30.0, 90.0, 240.0):
        retuned = retune(bundle, tempo)
        unrated = [k for k, d in retuned.measure_difficulty.items() if d.score is None]
        original = [k for k, d in bundle.measure_difficulty.items() if d.score is None]
        assert sorted(unrated) == sorted(original)


# --------------------------------------------------------------------------
# The two hazards
# --------------------------------------------------------------------------


def test_the_shared_example_bundle_is_never_mutated():
    """A retune must not leak one request's tempo into the cached fixture."""
    cached = load_example()
    before = {k: d.score for k, d in cached.measure_difficulty.items()}
    before_tempos = [m.tempo_bpm for m in cached.score.measures]
    before_assumptions = list(cached.score.assumptions)

    retune(cached, 200.0)

    assert load_example() is cached
    assert {k: d.score for k, d in cached.measure_difficulty.items()} == before
    assert [m.tempo_bpm for m in cached.score.measures] == before_tempos
    assert cached.score.assumptions == before_assumptions


def test_a_printed_tempo_survives_a_supplied_one(bundle):
    """Evidence read off the page outranks a global setting."""
    seeded = bundle.model_copy(deep=True)
    target = next(m for m in seeded.score.measures if m.is_analyzable)
    target.tempo_bpm = 48.0
    target.tempo_is_assumed = False

    retuned = retune(seeded, 200.0)
    kept = retuned.score.measure(target.id)
    assert kept.tempo_bpm == 48.0
    assert kept.tempo_is_assumed is False

    others = [m for m in retuned.score.measures if m.id != target.id and m.tempo_is_assumed]
    assert others and all(m.tempo_bpm == 200.0 for m in others)


def test_the_notice_says_a_printed_tempo_was_kept(bundle):
    seeded = bundle.model_copy(deep=True)
    target = next(m for m in seeded.score.measures if m.is_analyzable)
    target.tempo_is_assumed = False

    text = " ".join(retune(seeded, 120.0).score.assumptions)
    assert "120 BPM, which you supplied" in text
    assert "print a tempo and keep" in text


def test_the_notice_points_at_a_control_that_exists(bundle):
    text = " ".join(retune(bundle, None).score.assumptions)
    assert "assume 90 BPM" in text
    assert "above" in text, "the disclosure must point at the real toolbar control"


# --------------------------------------------------------------------------
# Input handling
# --------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["72", " 72 ", "72.0"])
def test_valid_tempo_is_parsed(raw):
    assert parse_tempo(raw) == 72.0


@pytest.mark.parametrize("raw", [None, "", "   ", "fast", "90bpm", "0", "-5", "1e9"])
def test_junk_tempo_becomes_none_rather_than_an_error(raw):
    """A malformed URL must not cost the user their analysis."""
    assert parse_tempo(raw) is None


def test_out_of_range_tempo_is_refused_not_clamped(bundle):
    for tempo in (MIN_TEMPO_BPM - 1, MAX_TEMPO_BPM + 1):
        with pytest.raises(TempoOutOfRange):
            retune(bundle, tempo)
