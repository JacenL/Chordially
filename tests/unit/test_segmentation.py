"""Phrase segmentation invariants.

The two that matter most, because they are the ones the spec calls out and the
ones a naive implementation gets wrong:

* structural ranges tile the piece -- no gaps, no measure owned twice;
* practice ranges may overlap, and the final phrase borrows nothing.
"""

from __future__ import annotations

from src.features.segmentation.phrases import (
    MAX_MEASURES,
    MIN_MEASURES,
    score_boundary_after,
)
from src.schemas.geometry import Region
from src.schemas.music import NoteEvent
from src.schemas.score import Measure, Note, Score, System
from src.server.analysis.assemble import rate_score, segment_score


def _region(i: int) -> Region:
    return Region(page_index=0, x=0.05 + (i % 5) * 0.18, y=0.1, w=0.17, h=0.08)


def build(measure_specs: list[list[NoteEvent]], per_system: int = 5) -> Score:
    """A score with the given measures, laid out across systems."""
    systems, measures, notes = [], [], []
    for i, events in enumerate(measure_specs):
        sys_index = i // per_system
        sys_id = f"t:s{sys_index}"
        if not any(s.id == sys_id for s in systems):
            systems.append(
                System(id=sys_id, page_index=0, index=sys_index, region=_region(0))
            )
        mid = f"t:m{i:04d}"
        note_ids = []
        for j, ev in enumerate(events):
            nid = f"{mid}:n{j}"
            notes.append(Note(id=nid, measure_id=mid, index_in_measure=j, event=ev))
            note_ids.append(nid)
        measures.append(
            Measure(
                id=mid,
                label=str(i + 1),
                ordinal=i,
                system_id=sys_id,
                region=_region(i),
                note_ids=note_ids,
                beats=4,
                beat_value=4,
                key_fifths=0,
            )
        )
        next(s for s in systems if s.id == sys_id).measure_ids.append(mid)
    return Score(id="t", fingerprint="f", input_kind="example", systems=systems, measures=measures, notes=notes)


def plain(n: int = 8) -> list[NoteEvent]:
    return [NoteEvent(is_rest=False, step="G", octave=4, value="eighth") for _ in range(n)]


def with_trailing_rest() -> list[NoteEvent]:
    return plain(7) + [NoteEvent(is_rest=True, value="eighth")]


# --------------------------------------------------------------------------
# Coverage invariants
# --------------------------------------------------------------------------


def test_structural_ranges_cover_every_measure_exactly_once():
    score = build([plain() for _ in range(16)])
    phrases = segment_score(score)
    owned = [mid for p in phrases for mid in p.measure_ids]
    assert owned == [m.id for m in score.measures_in_order()], "no gaps, no duplicates"


def test_phrases_respect_length_bounds():
    score = build([plain() for _ in range(20)])
    for p in segment_score(score):
        assert MIN_MEASURES <= len(p.measure_ids) <= MAX_MEASURES


def test_a_single_short_piece_is_one_phrase():
    score = build([plain() for _ in range(2)])
    phrases = segment_score(score)
    assert len(phrases) == 1
    assert len(phrases[0].measure_ids) == 2


# --------------------------------------------------------------------------
# Practice overlap
# --------------------------------------------------------------------------


def test_practice_range_borrows_the_next_phrase_first_note():
    score = build([plain() for _ in range(16)])
    phrases = segment_score(score)
    assert len(phrases) >= 2
    first = phrases[0]
    assert first.has_practice_overlap
    assert first.practice_end.measure_id != first.structural_end.measure_id
    assert first.practice_end.note_index == 0


def test_final_phrase_borrows_nothing_and_fabricates_nothing():
    score = build([plain() for _ in range(16)])
    last = segment_score(score)[-1]
    assert not last.has_practice_overlap
    assert last.practice_end.measure_id == last.structural_end.measure_id


def test_structural_end_is_never_moved_by_the_overlap():
    """The borrowed note must not change what the phrase *is*, or its rating."""
    score = build([plain() for _ in range(16)])
    for p in segment_score(score):
        assert p.structural_end.measure_id == p.measure_ids[-1]


def test_practice_overlap_skips_a_silent_measure_to_find_a_playable_note():
    specs = [plain() for _ in range(16)]
    specs[8] = []  # a measure with nothing recognized in it
    score = build(specs)
    phrases = segment_score(score)
    for p in phrases:
        if p.has_practice_overlap:
            target = score.measure(p.practice_end.measure_id)
            assert target is not None and target.note_ids, "borrowed note must be playable"


# --------------------------------------------------------------------------
# Evidence and honesty
# --------------------------------------------------------------------------


def test_a_rest_scores_higher_than_a_bare_barline():
    score = build([with_trailing_rest(), plain()])
    ordered = score.measures_in_order()
    with_rest = score_boundary_after(
        ordered[0], [n.event for n in score.notes_of(ordered[0])], ordered[1], []
    )
    bare = score_boundary_after(ordered[1], [n.event for n in score.notes_of(ordered[1])], None, [])
    assert with_rest.score > bare.score
    assert "rest" in with_rest.evidence


def test_a_bare_barline_yields_low_confidence_not_false_certainty():
    score = build([plain() for _ in range(16)])
    phrases = segment_score(score)
    interior = [p for p in phrases[:-1]]
    assert interior, "expected interior boundaries"
    assert all(p.end_boundary.confidence < 0.5 for p in interior), (
        "evidence-free boundaries must report low confidence"
    )
    assert all(p.end_boundary.reason for p in phrases), "every boundary states a reason"


def test_regions_are_fragmented_per_system_not_one_spanning_box():
    score = build([plain() for _ in range(16)], per_system=4)
    for p in segment_score(score):
        systems = {score.measure(mid).system_id for mid in p.measure_ids}
        assert len(p.regions) == len(systems)


# --------------------------------------------------------------------------
# Rating integration
# --------------------------------------------------------------------------


def test_unreadable_measures_are_unrated_not_zero():
    score = build([plain() for _ in range(4)])
    score.measures[1].quality = "unreadable"
    score.measures[1].note_ids = []
    ratings = rate_score(score)
    assert ratings[score.measures[1].id].score is None
    assert ratings[score.measures[0].id].score is not None
