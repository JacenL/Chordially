"""Practice instruction: what it must never do.

The musical invariants in CLAUDE.md and docs/music-pedagogy.md are mostly
prohibitions, so most of these tests assert a refusal. A rhythm variation that
quietly changed a passage's total duration, or that was offered on a passage of
tied notes, would be worse than no exercise at all.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from src.features.practice import rhythm
from src.features.practice.coach import build_guidance
from src.features.practice.library import load_library
from src.schemas.analysis import AnalysisBundle
from src.schemas.music import NoteEvent
from src.server.analysis.example import EXAMPLE_PATH


def n(step: str, octave: int = 4, value: str = "eighth", **kw) -> NoteEvent:
    return NoteEvent(is_rest=False, step=step, octave=octave, value=value, **kw)


def run_of(count: int, value: str = "eighth") -> list[NoteEvent]:
    steps = "CDEFGAB"
    return [n(steps[i % 7], 4, value) for i in range(count)]


# --------------------------------------------------------------------------
# The duration invariant
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["eighth", "16th", "quarter", "32nd"])
def test_variants_preserve_total_duration_exactly(value):
    notes = run_of(8, value)
    written = sum((note.duration for note in notes), Fraction(0))
    for variant in rhythm.variants(notes):
        assert variant.total == written, variant.name


def test_variants_preserve_pitch_order():
    notes = run_of(8)
    expected = [rhythm.pitch_label(note) for note in notes]
    for variant in rhythm.variants(notes):
        assert [vn.pitch for vn in variant.notes] == expected


def test_long_short_and_short_long_are_complementary():
    notes = run_of(4, "16th")
    long_short, short_long = rhythm.variants(notes)[:2]
    for a, b in zip(long_short.notes, short_long.notes):
        assert {a.role, b.role} == {"long", "short"}
        assert a.duration != b.duration


def test_pairing_uses_a_dotted_note_and_its_half():
    """The exact pattern docs/music-pedagogy.md describes for a verified pair."""
    long_short = rhythm.variants(run_of(4, "16th"))[0]
    first, second = long_short.notes[0], long_short.notes[1]
    assert (first.value, first.dots) == ("16th", 1)
    assert first.duration == Fraction(3, 32)
    assert (second.value, second.dots) == ("32nd", 0)
    assert second.duration == Fraction(1, 32)
    assert first.duration + second.duration == Fraction(2, 16)


def test_odd_note_out_keeps_its_written_value():
    variant = rhythm.variants(run_of(5))[0]
    assert variant.notes[-1].role == "unchanged"
    assert variant.total == sum((x.duration for x in run_of(5)), Fraction(0))


def test_displaced_start_joins_a_different_pair():
    notes = run_of(6)
    straight, _, displaced = rhythm.variants(notes)
    assert straight.notes[0].role == "long"
    assert displaced.notes[0].role == "unchanged"
    assert displaced.notes[1].role == "long"


# --------------------------------------------------------------------------
# Refusals. Each one is named in the pedagogy document.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "notes,fragment",
    [
        (run_of(3), "at least"),
        ([n("C"), n("D"), NoteEvent(is_rest=True, value="eighth"), n("E"), n("F")], "rests"),
        ([n("C", tie="start"), n("C", tie="stop"), n("D"), n("E")], "tied"),
        (
            [n("C", tuplet_actual=3, tuplet_normal=2)] * 4,
            "tuplet",
        ),
        ([n("C"), n("D", value="quarter"), n("E"), n("F")], "mixes note values"),
        (run_of(4, "64th"), "no shorter printed value"),
        ([n("C", dots=1), n("D", dots=1), n("E", dots=1), n("F", dots=1)], "already dotted"),
    ],
)
def test_unsafe_runs_are_refused_by_name(notes, fragment):
    with pytest.raises(rhythm.NotTransformable) as excinfo:
        rhythm.variants(notes)
    assert fragment in str(excinfo.value)


def test_longest_even_run_finds_the_printed_run_not_the_whole_phrase():
    notes = [n("C", value="quarter"), NoteEvent(is_rest=True, value="quarter")] + run_of(6)
    start, length = rhythm.longest_even_run(notes)
    assert (start, length) == (2, 6)


def test_longest_even_run_reports_nothing_when_there_is_no_run():
    notes = [n("C", value="quarter"), n("D", value="eighth"), n("E", value="half")]
    _, length = rhythm.longest_even_run(notes)
    assert length < rhythm.MIN_RUN


# --------------------------------------------------------------------------
# The library
# --------------------------------------------------------------------------


def test_every_technique_citation_resolves():
    library = load_library()
    for technique in library.techniques.values():
        for source_id in technique.sourceIds:
            assert source_id in library.sources, technique.id


def test_techniques_claiming_backing_name_a_source():
    library = load_library()
    for technique in library.techniques.values():
        if technique.evidenceCategory in ("teacher pedagogy", "research-informed"):
            assert technique.sourceIds, technique.id


def test_app_heuristics_say_so_in_their_cautions():
    library = load_library()
    for technique in library.techniques.values():
        if technique.evidenceCategory == "app heuristic":
            joined = " ".join(technique.cautions).lower()
            assert "heuristic" in joined or "chordially" in joined, technique.id


def test_every_technique_returns_the_player_to_the_music():
    library = load_library()
    for technique in library.techniques.values():
        assert technique.returnToContext.strip(), technique.id
        assert technique.successCriteria.strip(), technique.id
        assert technique.listeningGoals, technique.id


# --------------------------------------------------------------------------
# Selection against the real score
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bundle() -> AnalysisBundle:
    return AnalysisBundle.load_path(EXAMPLE_PATH)


def test_guidance_is_built_from_the_selected_passage(bundle):
    guidance = build_guidance(bundle, "wohlfahrt-p3:ph000")
    assert guidance.primary is not None
    assert guidance.primary.technique_id == "rhythm-pairs"
    assert "run of" in guidance.primary.trigger_reason
    assert guidance.primary.applies_to.startswith("measure")
    assert guidance.primary.variants


def test_a_contrasting_passage_gets_different_advice(bundle):
    """Not every technique for every passage: the spec's explicit requirement."""
    chosen = {}
    for phrase in bundle.phrases:
        guidance = build_guidance(bundle, phrase.id)
        if guidance.primary:
            chosen[phrase.id] = guidance.primary.technique_id
    assert len(set(chosen.values())) > 1, chosen


def test_advice_never_references_another_score(bundle):
    with pytest.raises(Exception):
        build_guidance(bundle, "some-other-score:ph000")


def test_unreadable_phrase_still_gets_honest_handling(bundle):
    """A phrase whose measures could not be read must not get invented notes."""
    unrated = [
        p for p in bundle.phrases
        if (d := bundle.phrase_rating(p.id)) is not None and d.score is None
    ]
    assert unrated, "the fixture is expected to contain an unrated phrase"
    guidance = build_guidance(bundle, unrated[0].id)
    if guidance.primary:
        # Whatever it offers, it cannot be a rhythm variation built from notes
        # that were never successfully read.
        assert guidance.primary.technique_id != "rhythm-pairs"


def test_rhythm_variants_in_guidance_still_balance(bundle):
    guidance = build_guidance(bundle, "wohlfahrt-p3:ph000")
    for variant in guidance.primary.variants:
        longs = sum(1 for note in variant["notes"] if note["role"] == "long")
        shorts = sum(1 for note in variant["notes"] if note["role"] == "short")
        assert longs == shorts
