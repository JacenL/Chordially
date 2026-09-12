"""Phrase editing: the invariants an edit must never break.

CLAUDE.md names these explicitly, and they are the reason edits rebuild the
phrase list from a partition of measure indices rather than patching two phrases
in place. Patching is how a gap gets introduced, and a gap means some measure of
the piece belongs to no phrase at all — which the user would only discover by
clicking it.
"""

from __future__ import annotations

import pytest

from src.features.difficulty.rubric import aggregate_phrase
from src.features.segmentation.edit import EditRefused, merge_phrase, split_phrase
from src.schemas.analysis import AnalysisBundle
from src.server.analysis.assemble import rate_phrases
from src.server.analysis.example import EXAMPLE_PATH


@pytest.fixture
def bundle() -> AnalysisBundle:
    return AnalysisBundle.load_path(EXAMPLE_PATH).model_copy(deep=True)


def phrases_of(bundle: AnalysisBundle) -> list:
    return [p for p in bundle.phrases if p.level == "phrase"]


def ordinals(bundle: AnalysisBundle, phrase) -> list[int]:
    by_id = {m.id: m for m in bundle.score.measures}
    return sorted(by_id[mid].ordinal for mid in phrase.measure_ids if mid in by_id)


def assert_partitions(bundle: AnalysisBundle, phrases: list) -> None:
    """Structural coverage tiles the measures: no gaps, no double ownership."""
    seen: list[int] = []
    for phrase in phrases:
        seen.extend(ordinals(bundle, phrase))
    assert len(seen) == len(set(seen)), "a measure is owned by two phrases"

    covered = sorted(seen)
    expected = sorted(m.ordinal for m in bundle.score.measures)
    assert covered == expected, "coverage has a gap or claims a measure twice"


def assert_contiguous(bundle: AnalysisBundle, phrases: list) -> None:
    for phrase in phrases:
        got = ordinals(bundle, phrase)
        assert got == list(range(got[0], got[-1] + 1)), f"{phrase.id} is not contiguous"


# --------------------------------------------------------------------------
# Coverage survives every edit
# --------------------------------------------------------------------------


def test_the_original_segmentation_already_partitions(bundle):
    assert_partitions(bundle, phrases_of(bundle))


def test_coverage_survives_a_split(bundle):
    target = phrases_of(bundle)[1]
    at = target.measure_ids[2]
    edited = split_phrase(bundle.score, phrases_of(bundle), target.id, at)

    assert len(edited) == len(phrases_of(bundle)) + 1
    assert_partitions(bundle, edited)
    assert_contiguous(bundle, edited)


def test_coverage_survives_a_merge(bundle):
    target = phrases_of(bundle)[1]
    edited = merge_phrase(bundle.score, phrases_of(bundle), target.id)

    assert len(edited) == len(phrases_of(bundle)) - 1
    assert_partitions(bundle, edited)
    assert_contiguous(bundle, edited)


def test_split_then_merge_restores_the_original_members(bundle):
    original = phrases_of(bundle)
    target = original[1]
    at = target.measure_ids[2]

    after_split = split_phrase(bundle.score, original, target.id, at)
    first_half = next(p for p in after_split if ordinals(bundle, p)[0] == ordinals(bundle, target)[0])
    restored = merge_phrase(bundle.score, after_split, first_half.id)

    assert [ordinals(bundle, p) for p in restored] == [ordinals(bundle, p) for p in original]


def test_a_split_puts_the_boundary_exactly_where_asked(bundle):
    target = phrases_of(bundle)[1]
    at = target.measure_ids[2]
    edited = split_phrase(bundle.score, phrases_of(bundle), target.id, at)

    second = next(p for p in edited if at in p.measure_ids)
    assert second.measure_ids[0] == at, "the chosen measure must begin the new phrase"


# --------------------------------------------------------------------------
# The rules that make a phrase a phrase
# --------------------------------------------------------------------------


def test_practice_overlap_is_recomputed_after_a_split(bundle):
    """Both halves borrow the next *playable* note, not the old phrase's end.

    "Playable" is doing real work here: a measure recognition could not read has
    no notes to carry into, so the overlap reaches past it to the next measure
    that does. Borrowing an empty measure would hand the player a rest and call
    it the join.
    """
    target = phrases_of(bundle)[1]
    at = target.measure_ids[2]
    edited = split_phrase(bundle.score, phrases_of(bundle), target.id, at)

    by_id = {m.id: m for m in bundle.score.measures}
    ordered = bundle.score.measures_in_order()
    by_start = sorted(edited, key=lambda p: ordinals(bundle, p)[0])

    for phrase in by_start[:-1]:
        assert phrase.has_practice_overlap is True
        after = ordinals(bundle, phrase)[-1] + 1
        expected = next(m for m in ordered if m.ordinal >= after and m.note_ids)
        assert phrase.practice_end.measure_id == expected.id
        assert phrase.practice_end.note_index == 0
        assert by_id[phrase.practice_end.measure_id].note_ids, "borrowed an empty measure"


def test_the_final_phrase_still_borrows_nothing(bundle):
    for phrases in (
        split_phrase(bundle.score, phrases_of(bundle), phrases_of(bundle)[0].id,
                     phrases_of(bundle)[0].measure_ids[1]),
        merge_phrase(bundle.score, phrases_of(bundle), phrases_of(bundle)[0].id),
    ):
        last = max(phrases, key=lambda p: ordinals(bundle, p)[-1])
        assert last.has_practice_overlap is False
        assert last.practice_end == last.structural_end


def test_structural_range_is_never_extended_by_the_overlap(bundle):
    target = phrases_of(bundle)[2]
    edited = split_phrase(bundle.score, phrases_of(bundle), target.id, target.measure_ids[1])
    for phrase in edited:
        assert phrase.structural_end.measure_id == phrase.measure_ids[-1]


def test_an_edited_phrase_is_marked_as_edited(bundle):
    target = phrases_of(bundle)[1]
    edited = split_phrase(bundle.score, phrases_of(bundle), target.id, target.measure_ids[2])
    touched = [p for p in edited if p.user_edited]
    assert touched, "an edit must be visible as an edit"
    assert any(p.start_boundary.reason == "you placed this boundary" for p in edited)


def test_an_untouched_phrase_keeps_its_inferred_reason(bundle):
    original = phrases_of(bundle)
    target = original[3]
    edited = split_phrase(bundle.score, original, target.id, target.measure_ids[1])

    first = next(p for p in edited if ordinals(bundle, p)[0] == 0)
    assert first.start_boundary.reason == original[0].start_boundary.reason
    assert first.user_edited is False


def test_a_split_phrase_gets_a_region_fragment_per_system(bundle):
    for phrase in split_phrase(
        bundle.score, phrases_of(bundle), phrases_of(bundle)[1].id,
        phrases_of(bundle)[1].measure_ids[2],
    ):
        by_id = {m.id: m for m in bundle.score.measures}
        systems = {by_id[mid].system_id for mid in phrase.measure_ids}
        assert len(phrase.regions) == len(systems)


# --------------------------------------------------------------------------
# Ratings follow membership
# --------------------------------------------------------------------------


def test_a_merged_phrase_rates_as_a_fresh_aggregation_of_its_union(bundle):
    target = phrases_of(bundle)[4]
    edited = merge_phrase(bundle.score, phrases_of(bundle), target.id)
    ratings = rate_phrases(edited, bundle.measure_difficulty)

    merged = next(p for p in edited if ordinals(bundle, p)[0] == ordinals(bundle, target)[0])
    expected, expected_peak = aggregate_phrase(
        [bundle.measure_difficulty[mid].score for mid in merged.measure_ids]
    )
    assert ratings[merged.id].score == expected
    assert ratings[merged.id].peak == expected_peak


def test_splitting_can_separate_a_hard_half_from_an_easy_one(bundle):
    """The point of splitting: two ideas stop sharing one averaged number."""
    target = phrases_of(bundle)[1]
    before = bundle.phrase_difficulty[target.id].score
    edited = split_phrase(bundle.score, phrases_of(bundle), target.id, target.measure_ids[3])
    ratings = rate_phrases(edited, bundle.measure_difficulty)

    halves = [
        ratings[p.id].score
        for p in edited
        if set(p.measure_ids) <= set(target.measure_ids) and ratings[p.id].score is not None
    ]
    assert len(halves) == 2
    assert before is not None
    assert min(halves) <= before <= max(halves) or halves[0] != halves[1]


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------


def test_splitting_at_a_phrase_start_is_refused_with_a_reason(bundle):
    target = phrases_of(bundle)[1]
    with pytest.raises(EditRefused) as excinfo:
        split_phrase(bundle.score, phrases_of(bundle), target.id, target.measure_ids[0])
    assert "already begins" in str(excinfo.value)


def test_splitting_at_a_measure_outside_the_phrase_is_refused(bundle):
    first, second = phrases_of(bundle)[0], phrases_of(bundle)[1]
    with pytest.raises(EditRefused) as excinfo:
        split_phrase(bundle.score, phrases_of(bundle), first.id, second.measure_ids[1])
    assert "not inside" in str(excinfo.value)


def test_merging_the_last_phrase_is_refused_with_a_reason(bundle):
    last = phrases_of(bundle)[-1]
    with pytest.raises(EditRefused) as excinfo:
        merge_phrase(bundle.score, phrases_of(bundle), last.id)
    assert "last phrase" in str(excinfo.value)


def test_editing_a_phrase_from_another_score_is_refused(bundle):
    with pytest.raises(EditRefused):
        merge_phrase(bundle.score, phrases_of(bundle), "other-score:ph000")
