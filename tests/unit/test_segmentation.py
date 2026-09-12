"""Phrase segmentation invariants.

The two that matter most, because they are the ones the spec calls out and the
ones a naive implementation gets wrong:

* structural ranges tile the piece -- no gaps, no measure owned twice;
* practice ranges may overlap, and the final phrase borrows nothing.
"""

from __future__ import annotations

import pytest

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


# --------------------------------------------------------------------------
# Silence is not a musical idea
# --------------------------------------------------------------------------


def _silence_score(pattern: str) -> "Score":
    """A one-system score where 'x' is a sounded measure and '.' is rests."""
    from src.schemas.geometry import Region
    from src.schemas.music import NoteEvent
    from src.schemas.score import Measure, Note, Page, Score, System

    measures, notes = [], []
    x = 0.05
    for i, mark in enumerate(pattern):
        mid = f"t:m{i}"
        event = (
            NoteEvent(is_rest=True, value="quarter")
            if mark == "."
            else NoteEvent(is_rest=False, step="G", octave=4, value="quarter")
        )
        note_ids = []
        for j in range(4):
            nid = f"{mid}:n{j}"
            notes.append(Note(id=nid, measure_id=mid, index_in_measure=j, event=event))
            note_ids.append(nid)
        measures.append(
            Measure(
                id=mid,
                label=str(i + 1),
                ordinal=i,
                system_id="t:s0",
                region=Region(x=x, y=0.1, w=0.08, h=0.08),
                note_ids=note_ids,
                beats=4,
                beat_value=4,
            )
        )
        x += 0.08

    return Score(
        id="t",
        fingerprint="f",
        input_kind="example",
        pages=[Page(id="t:p0", index=0, width_px=1000, height_px=1400, render_dpi=200)],
        systems=[
            System(
                id="t:s0",
                page_index=0,
                index=0,
                region=Region(x=0.05, y=0.1, w=0.9, h=0.08),
                measure_ids=[m.id for m in measures],
            )
        ],
        measures=measures,
        notes=notes,
    )


def _sounded(score, phrase) -> bool:
    events = [n.event for mid in phrase.measure_ids for n in score.notes_of(score.measure(mid))]
    return any(not e.is_rest for e in events)


@pytest.mark.parametrize(
    "pattern",
    [
        "xxxx....xxxx",   # silence in the middle
        "....xxxxxxxx",   # silence at the start, with nothing before to join
        "xxxxxxxx....",   # silence at the end
        "xx..xx..xx..",   # alternating
    ],
)
def test_no_phrase_is_made_entirely_of_rests(pattern):
    """A phrase is one musical idea, and silence is not one.

    Left alone these became their own phrases, rated 0.0 "Beginner-friendly",
    drawing green ribbon over the silence and offering practice instruction for
    a passage with nothing to play.
    """
    score = _silence_score(pattern)
    phrases = segment_score(score)
    assert phrases
    for phrase in phrases:
        assert _sounded(score, phrase), f"{phrase.label} contains no sounded note"


def test_absorbed_silence_keeps_the_measures_in_the_score():
    """The rest bars stay: they lose their own phrase, not their place."""
    score = _silence_score("xxxx....xxxx")
    phrases = segment_score(score)
    covered = sorted(
        score.measure(mid).ordinal for p in phrases for mid in p.measure_ids
    )
    assert covered == list(range(len(score.measures)))
    assert len(covered) == len(set(covered)), "a measure is owned twice"


def test_silence_joins_the_phrase_before_it_when_there_is_one():
    score = _silence_score("xxxx....xxxx")
    phrases = segment_score(score)
    owner = next(p for p in phrases if "t:m4" in p.measure_ids)
    # The rests follow sounded music, so they belong to what came before.
    assert "t:m3" in owner.measure_ids


def test_leading_silence_joins_the_phrase_after_it():
    """Nothing precedes it, so it attaches forward rather than being dropped."""
    score = _silence_score("....xxxxxxxx")
    phrases = segment_score(score)
    owner = next(p for p in phrases if "t:m0" in p.measure_ids)
    assert _sounded(score, owner)


def test_a_score_of_pure_silence_is_left_as_one_phrase():
    """Nothing to absorb into. It must not loop or return nothing."""
    score = _silence_score("........")
    phrases = segment_score(score)
    assert len(phrases) == 1
    assert len(phrases[0].measure_ids) == len(score.measures)


# --------------------------------------------------------------------------
# Practice sections: the level above a phrase
#
# C17 changed what this level means. It used to be a purely structural reading
# of printed signature changes, and a page showing none got no sections at all.
# It is now the unit the score is coloured by and a click selects, so it has to
# cover the piece: adjacent phrases are grouped while they ask for the same kind
# of work, and split where the demands or the difficulty actually change.
#
# The protection the old rule provided is kept and tested below: a section is
# labelled by the measures it spans and by demands measured inside it, never by
# an invented formal name.
# --------------------------------------------------------------------------


def _sectioned_score(meters, per_state: int = 10):
    """A score whose printed signature changes between the given states."""
    from src.features.segmentation.sections import find_sections
    from src.schemas.geometry import Region
    from src.schemas.music import NoteEvent
    from src.schemas.score import Measure, Note, Page, Score, System
    from src.server.analysis.assemble import rate_score

    measures, notes = [], []
    ordinal = 0
    for beats, beat_value, fifths in meters:
        for _ in range(per_state):
            mid = f"t:m{ordinal}"
            note_ids = []
            for j in range(2):
                nid = f"{mid}:n{j}"
                notes.append(
                    Note(
                        id=nid,
                        measure_id=mid,
                        index_in_measure=j,
                        event=NoteEvent(is_rest=False, step="G", octave=4, value="quarter"),
                    )
                )
                note_ids.append(nid)
            measures.append(
                Measure(
                    id=mid,
                    label=str(ordinal + 1),
                    ordinal=ordinal,
                    system_id="t:s0",
                    region=Region(x=0.05 + 0.02 * ordinal, y=0.1, w=0.02, h=0.08),
                    note_ids=note_ids,
                    beats=beats,
                    beat_value=beat_value,
                    key_fifths=fifths,
                )
            )
            ordinal += 1

    score = Score(
        id="t",
        fingerprint="f",
        input_kind="example",
        pages=[Page(id="t:p0", index=0, width_px=1000, height_px=1400, render_dpi=200)],
        systems=[
            System(
                id="t:s0",
                page_index=0,
                index=0,
                region=Region(x=0.05, y=0.1, w=0.9, h=0.08),
                measure_ids=[m.id for m in measures],
            )
        ],
        measures=measures,
        notes=notes,
    )
    phrases = segment_score(score)
    return score, phrases, find_sections(score, phrases, rate_score(score))


def test_a_uniform_page_is_one_section_not_one_per_measure():
    """The failure this guards: a colour band per measure instead of per passage.

    Twelve identical measures make one thing to practise, and colouring them as
    twelve regions would be a picture of rounding rather than of the music.
    """
    score, _, sections = _sectioned_score([(4, 4, 0)], per_state=12)
    assert len(sections) == 1
    assert len(sections[0].measure_ids) == len(score.measures)


def test_a_meter_change_creates_a_section_boundary():
    _, _, sections = _sectioned_score([(4, 4, 0), (2, 4, 0)])
    assert len(sections) == 2


def test_a_key_change_creates_a_section_boundary():
    _, _, sections = _sectioned_score([(4, 4, 0), (4, 4, 3)])
    assert len(sections) == 2


def test_sections_carry_no_invented_formal_label():
    """Measure ranges and printed accidental counts only -- no formal names."""
    _, _, sections = _sectioned_score([(4, 4, 0), (2, 4, 1)])
    assert "changes to 2/4, 1 sharp" in sections[1].start_boundary.reason
    for section in sections:
        text = " ".join(
            (section.label, section.start_boundary.reason, section.end_boundary.reason)
        ).lower()
        for invented in ("exposition", "chorus", "major", "minor", "theme", "verse"):
            assert invented not in text, (invented, text)


def test_sections_tile_the_measures_without_gaps():
    score, _, sections = _sectioned_score([(4, 4, 0), (2, 4, 1), (3, 4, 1)])
    covered = sorted(score.measure(mid).ordinal for s in sections for mid in s.measure_ids)
    assert covered == list(range(len(score.measures)))
    assert len(covered) == len(set(covered))


def test_sections_never_split_a_phrase():
    """The three levels nest; a section boundary lands on a phrase start."""
    score, phrases, sections = _sectioned_score([(4, 4, 0), (2, 4, 1)], per_state=12)
    starts = {score.measure(s.measure_ids[0]).ordinal for s in sections}
    phrase_starts = {score.measure(p.measure_ids[0]).ordinal for p in phrases}
    assert starts <= phrase_starts


def test_every_phrase_points_at_the_section_containing_it():
    _, phrases, sections = _sectioned_score([(4, 4, 0), (2, 4, 1)])
    by_id = {s.id: s for s in sections}
    for phrase in phrases:
        assert phrase.parent_id in by_id
        assert set(phrase.measure_ids) <= set(by_id[phrase.parent_id].measure_ids)


def test_a_single_phrase_page_is_a_single_section():
    """A section cannot be finer than a phrase, so a one-phrase page is one section.

    A signature change inside that phrase does not cut it in half. The three
    levels nest or they are not levels.
    """
    _, phrases, sections = _sectioned_score([(4, 4, 0), (2, 4, 1)], per_state=4)
    assert len(phrases) == 1
    assert len(sections) == 1


def test_a_step_in_difficulty_splits_a_section_without_any_signature_change():
    """Same meter, same key: the music simply gets faster, and that is a boundary."""
    from src.features.segmentation.sections import find_sections
    from src.schemas.music import NoteEvent
    from src.schemas.score import Note
    from src.server.analysis.assemble import rate_score

    score, phrases, _ = _sectioned_score([(4, 4, 0), (4, 4, 0)], per_state=8)
    ordered = score.measures_in_order()
    by_id = {n.id: n for n in score.notes}

    # Rewrite the second half as sixteenth-note runs: sixteen notes a bar
    # instead of two, which is a real step in what the passage asks for.
    for measure in ordered[len(ordered) // 2:]:
        for note_id in measure.note_ids:
            del by_id[note_id]
        score.notes = [n for n in score.notes if n.id not in measure.note_ids]
        fresh = []
        for index in range(16):
            note_id = f"{measure.id}:f{index:02d}"
            note = Note(
                id=note_id,
                measure_id=measure.id,
                index_in_measure=index,
                event=NoteEvent(is_rest=False, step="G", octave=4, value="16th"),
            )
            score.notes.append(note)
            fresh.append(note_id)
        measure.note_ids = fresh

    ratings = rate_score(score)
    easy = ratings[ordered[0].id].score
    hard = ratings[ordered[-1].id].score
    assert hard is not None and easy is not None and hard - easy > 1.0, (easy, hard)

    sections = find_sections(score, phrases, ratings)
    assert len(sections) >= 2, "a real step in difficulty must start a new section"
    assert any("difficulty" in s.start_boundary.reason for s in sections[1:]), [
        s.start_boundary.reason for s in sections
    ]


def test_a_user_split_overrides_the_heuristic():
    from src.features.segmentation.sections import find_sections
    from src.server.analysis.assemble import rate_score

    score, phrases, sections = _sectioned_score([(4, 4, 0)], per_state=12)
    assert len(sections) == 1

    split_at = phrases[1].measure_ids[0]
    edited = find_sections(score, phrases, rate_score(score), starts={split_at})
    assert len(edited) == 2
    assert edited[1].measure_ids[0] == split_at
    assert edited[1].user_edited
    assert "you split the section here" in edited[1].start_boundary.reason


def test_a_user_merge_removes_a_derived_boundary():
    from src.features.segmentation.sections import find_sections
    from src.server.analysis.assemble import rate_score

    score, phrases, sections = _sectioned_score([(4, 4, 0), (2, 4, 1)])
    assert len(sections) == 2
    joined = find_sections(
        score, phrases, rate_score(score), joins={sections[1].measure_ids[0]}
    )
    assert len(joined) == 1


def test_unreadable_material_is_never_grouped_with_rated_music():
    """Unknown is not a difficulty, and must not inherit a section colour."""
    from src.features.segmentation.sections import find_sections
    from src.server.analysis.assemble import rate_score

    score, phrases, _ = _sectioned_score([(4, 4, 0)], per_state=16)
    for measure in score.measures_in_order()[8:]:
        measure.quality = "unreadable"
        measure.quality_note = "too faint to read"

    ratings = rate_score(score)
    for section in find_sections(score, phrases, ratings):
        rated = {ratings[mid].score is not None for mid in section.measure_ids}
        assert len(rated) == 1, (
            "a section mixes readable and unreadable measures, so one colour "
            "would present unknown material as easy or hard"
        )
