"""The validation gate, which is what keeps recognition honest.

These tests pin the behaviour that lets partial recognition stay visible instead
of being rendered as though it were fine.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from src.schemas.music import (
    MeasureTranscription,
    NoteEvent,
    WireNote,
    WireSystem,
    validate_measure,
)


def note(value="eighth", *, rest=False, step="G", octave=4, **kw) -> NoteEvent:
    if rest:
        return NoteEvent(is_rest=True, value=value, **kw)
    return NoteEvent(is_rest=False, step=step, octave=octave, value=value, **kw)


def transcription(notes, *, legible=True, beats=4, beat_value=4) -> MeasureTranscription:
    return MeasureTranscription(
        contains_music=bool(notes),
        beats_in_measure=beats,
        beat_value=beat_value,
        notes=notes,
        legible=legible,
    )


# --------------------------------------------------------------------------
# Exact duration arithmetic
# --------------------------------------------------------------------------


def test_durations_are_exact_rationals_not_floats():
    assert note("quarter").duration == Fraction(1, 4)
    assert note("16th").duration == Fraction(1, 16)


def test_dots_add_half_of_what_precedes_them():
    assert note("quarter", dots=1).duration == Fraction(3, 8)
    assert note("quarter", dots=2).duration == Fraction(7, 16)


def test_triplet_compresses_three_notes_into_two():
    trip = note("eighth", tuplet_actual=3, tuplet_normal=2)
    assert trip.duration == Fraction(1, 12)
    assert trip.duration * 3 == Fraction(1, 4)


def test_ties_and_tuplets_are_preserved_not_flattened():
    trip = note("eighth", tuplet_actual=3, tuplet_normal=2, tie="start")
    assert trip.tie == "start"
    assert trip.tuplet_actual == 3


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


def test_a_measure_that_adds_up_is_accepted():
    v = validate_measure(transcription([note() for _ in range(8)]), 4, 4)
    assert v.ok and not v.low_confidence


def test_a_measure_that_overflows_is_rejected():
    v = validate_measure(transcription([note("quarter") for _ in range(5)]), 4, 4)
    assert not v.ok
    assert "do not sum" in v.reason


def test_arithmetic_outranks_self_reported_doubt():
    """The C1 finding: doubt is about beam counts, which change the sum.

    A measure that lands exactly on the meter has therefore already been checked
    on the very point the model was unsure about, so it is accepted -- but
    flagged, never silently promoted to confident.
    """
    v = validate_measure(transcription([note() for _ in range(8)], legible=False), 4, 4)
    assert v.ok
    assert v.low_confidence


def test_doubt_still_loses_the_benefit_of_the_doubt_when_short():
    """A short measure the model already doubted is a dropped note, not a pickup."""
    short = [note() for _ in range(4)]
    confident = validate_measure(transcription(short), 4, 4)
    doubted = validate_measure(transcription(short, legible=False), 4, 4)
    assert confident.ok and confident.is_pickup
    assert not doubted.ok


def test_a_short_measure_is_allowed_as_a_pickup():
    v = validate_measure(transcription([note("quarter")]), 4, 4)
    assert v.ok and v.is_pickup


def test_a_region_with_no_notes_is_non_musical_not_a_failure():
    """Clef and time-signature regions exist on a real page; they are not errors."""
    v = validate_measure(transcription([]), 4, 4)
    assert not v.ok
    assert v.non_musical


def test_notes_outside_the_violin_range_are_rejected():
    v = validate_measure(transcription([note(octave=0) for _ in range(8)]), 4, 4)
    assert not v.ok
    assert "range" in v.reason


def test_missing_time_signature_is_reported_not_assumed():
    v = validate_measure(transcription([note() for _ in range(8)], beats=None), None, None)
    assert not v.ok
    assert "time signature" in v.reason


# --------------------------------------------------------------------------
# The lean wire format
# --------------------------------------------------------------------------


def test_wire_pitch_tokens_parse():
    assert WireNote(m=0, p="G4", v="8").to_event().midi == 67
    assert WireNote(m=0, p="F#5", v="16").to_event().alter == 1
    assert WireNote(m=0, p="Bb3", v="4").to_event().alter == -1
    assert WireNote(m=0, p="r", v="4").to_event().is_rest


def test_unparseable_pitch_is_reported_not_silently_dropped():
    """A lost note would make a measure look shorter than it is and fail the gate
    for the wrong reason, so conversion problems must surface."""
    sysm = WireSystem(
        beats=4,
        beat_value=4,
        measure_count=1,
        notes=[WireNote(m=0, p="G4", v="8"), WireNote(m=0, p="H9", v="8")],
    )
    measures, problems = sysm.to_measures()
    assert len(problems) == 1
    assert len(measures[0].notes) == 1


def test_wire_groups_notes_into_their_measures():
    sysm = WireSystem(
        beats=4,
        beat_value=4,
        measure_count=2,
        notes=[WireNote(m=0, p="G4", v="4"), WireNote(m=1, p="A4", v="4")],
    )
    measures, problems = sysm.to_measures()
    assert not problems
    assert len(measures) == 2
    assert measures[0].notes[0].step == "G"
    assert measures[1].notes[0].step == "A"


def test_illegible_measures_are_marked_from_the_wire_list():
    sysm = WireSystem(
        beats=4,
        beat_value=4,
        measure_count=2,
        notes=[WireNote(m=0, p="G4", v="4"), WireNote(m=1, p="A4", v="4")],
        illegible_measures=[1],
    )
    measures, _ = sysm.to_measures()
    assert measures[0].legible
    assert not measures[1].legible


@pytest.mark.parametrize("wire_value,expected", [("1", 1), ("4", 4), ("16", 16), ("32", 32)])
def test_wire_note_values_map_to_real_durations(wire_value, expected):
    ev = WireNote(m=0, p="G4", v=wire_value).to_event()
    assert ev.duration == Fraction(1, expected)
