"""The uniform-beam-miscount repair, and everything it must refuse to touch.

This is the only place the pipeline changes what recognition reported, so its
boundaries matter more than its successes. Most of these tests assert that it
does nothing.
"""

from __future__ import annotations

from fractions import Fraction

from src.schemas.music import (
    MeasureTranscription,
    NoteEvent,
    repair_uniform_scale,
    validate_measure,
)

FOUR_FOUR = Fraction(4, 4)


def ev(value="16th", **kw) -> NoteEvent:
    return NoteEvent(is_rest=False, step="G", octave=4, value=value, **kw)


def measure(notes) -> MeasureTranscription:
    return MeasureTranscription(
        contains_music=True, beats_in_measure=4, beat_value=4, notes=notes
    )


# --------------------------------------------------------------------------
# What it repairs
# --------------------------------------------------------------------------


def test_eight_notes_read_as_16ths_are_re_read_as_eighths():
    """The exact failure seen on the fixture: heavy printing doubles a beam."""
    t = measure([ev("16th") for _ in range(8)])
    assert t.total_duration == Fraction(1, 2)

    result = repair_uniform_scale(t, FOUR_FOUR)
    assert result is not None
    repaired, why = result
    assert repaired.total_duration == FOUR_FOUR
    assert all(n.value == "eighth" for n in repaired.notes)
    assert "eighth" in why and "beam" in why.lower()


def test_repair_preserves_the_note_sequence_exactly():
    """Only the printed value changes. Pitches must survive untouched."""
    original = [
        NoteEvent(is_rest=False, step=s, octave=4, value="16th")
        for s in ["G", "A", "B", "C", "D", "E", "F", "G"]
    ]
    repaired, _ = repair_uniform_scale(measure(original), FOUR_FOUR)
    assert [n.step for n in repaired.notes] == [n.step for n in original]
    assert [n.octave for n in repaired.notes] == [n.octave for n in original]


def test_a_four_times_error_is_also_repairable():
    t = measure([ev("32nd") for _ in range(8)])
    repaired, _ = repair_uniform_scale(t, FOUR_FOUR)
    assert repaired.total_duration == FOUR_FOUR


def test_repaired_measures_validate_but_are_flagged_low_confidence():
    t = measure([ev("16th") for _ in range(8)])
    repaired, _ = repair_uniform_scale(t, FOUR_FOUR)
    assert validate_measure(repaired, 4, 4).ok


# --------------------------------------------------------------------------
# What it must refuse
# --------------------------------------------------------------------------


def test_refuses_a_mixed_rhythm_measure():
    """A mixed measure that does not add up is a real error, not a beam count."""
    t = measure([ev("16th"), ev("eighth"), ev("quarter")])
    assert repair_uniform_scale(t, FOUR_FOUR) is None


def test_refuses_when_the_ratio_is_not_a_power_of_two():
    t = measure([ev("16th") for _ in range(5)])
    assert repair_uniform_scale(t, FOUR_FOUR) is None


def test_refuses_tuplets():
    t = measure([ev("16th", tuplet_actual=3, tuplet_normal=2) for _ in range(8)])
    assert repair_uniform_scale(t, FOUR_FOUR) is None


def test_refuses_dotted_notes():
    t = measure([ev("16th", dots=1) for _ in range(8)])
    assert repair_uniform_scale(t, FOUR_FOUR) is None


def test_refuses_tied_notes():
    t = measure([ev("16th", tie="start") for _ in range(8)])
    assert repair_uniform_scale(t, FOUR_FOUR) is None


def test_refuses_an_already_correct_measure():
    t = measure([ev("eighth") for _ in range(8)])
    assert repair_uniform_scale(t, FOUR_FOUR) is None


def test_refuses_an_empty_measure():
    assert repair_uniform_scale(measure([]), FOUR_FOUR) is None


def test_refuses_when_rescaling_would_leave_the_range_of_note_values():
    t = measure([ev("whole") for _ in range(8)])
    assert repair_uniform_scale(t, FOUR_FOUR) is None


def test_a_genuinely_wrong_measure_is_not_massaged_into_correctness():
    """Six uniform eighths in 4/4 is 3/4 -- not a power-of-two error.

    The repair refuses it, and validation accepts it only as an incomplete
    measure flagged low-confidence: from arithmetic alone a pickup and a missed
    note look identical, so it may be rated but may not look verified.
    """
    t = measure([ev("eighth") for _ in range(6)])
    assert repair_uniform_scale(t, FOUR_FOUR) is None

    v = validate_measure(t, 4, 4)
    assert v.ok and v.is_pickup
    assert v.low_confidence, "an unverifiable short measure must not read as confident"
