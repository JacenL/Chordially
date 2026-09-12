"""Rubric 2.0: the seven inflation causes, one test each.

Every assertion here failed before C16, when straightforward first-position
eighth-note studies were rating 3.2-5.1 out of 10. Each test is written against
the *notation* that produced the wrong number rather than against the constant
that was changed, so a later rewrite of the weights cannot quietly reintroduce
the same behaviour while keeping the tests green.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from src.features.difficulty.rubric import (
    _saturate,
    beat_unit,
    key_alteration,
    rate_measure,
)
from src.schemas.music import NoteEvent


def n(step: str, octave: int, value: str = "eighth", **kw) -> NoteEvent:
    return NoteEvent(is_rest=False, step=step, octave=octave, value=value, **kw)


def factors_of(*args, **kwargs) -> dict[str, float]:
    return {f.key: f.contribution for f in rate_measure(*args, **kwargs)[1]}


# --------------------------------------------------------------------------
# 1. Ordinary off-beat notes were counted as syncopation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value,count", [("eighth", 8), ("16th", 16)])
def test_ordinary_off_beat_notes_are_not_syncopation(value, count):
    """Straight eighths and sixteenths sit off the beat. That is not syncopation.

    Before this fix, half of every straight-eighth measure and three quarters of
    every straight-sixteenth measure counted as displaced accents -- which is
    most of the note heads in a beginner etude book.
    """
    assert "syncopation" not in factors_of([n("G", 4, value) for _ in range(count)], 4, 4)


def test_a_displaced_accent_still_counts_as_syncopation():
    """The feature must still fire on the thing it is named for."""
    syncopated = [
        n("G", 4, "eighth"),
        n("A", 4, "quarter"),
        n("B", 4, "quarter"),
        n("C", 5, "quarter"),
        n("D", 5, "eighth"),
    ]
    assert factors_of(syncopated, 4, 4).get("syncopation", 0.0) > 0.5


def test_an_off_beat_attack_after_a_silent_beat_counts():
    """A rest on the beat and the note after it is displacement, not subdivision."""
    notes: list[NoteEvent] = []
    for _ in range(4):
        notes.append(NoteEvent(is_rest=True, value="eighth"))
        notes.append(n("G", 4, "eighth"))
    assert factors_of(notes, 4, 4).get("syncopation", 0.0) > 0.0


# --------------------------------------------------------------------------
# 2. Key-signature notes were charged as printed accidentals
# --------------------------------------------------------------------------


def test_key_alteration_reads_the_signature_in_order():
    assert key_alteration("F", 1) == 1
    assert key_alteration("C", 1) == 0
    assert key_alteration("C", 2) == 1
    assert key_alteration("B", -1) == -1
    assert key_alteration("F", 0) == 0
    assert key_alteration(None, 3) == 0


def test_key_signature_notes_are_not_charged_as_accidentals():
    """F# in a one-sharp key is the key, not a chromatic demand."""
    in_key = [n("F", 5, alter=1) for _ in range(8)]
    assert "chromatic" not in factors_of(in_key, 4, 4, key_fifths=1)
    # The same notes in C major are eight printed sharps and must still count.
    assert "chromatic" in factors_of(in_key, 4, 4, key_fifths=0)


def test_a_natural_against_the_key_signature_is_an_accidental():
    """F natural in a one-sharp key is a printed accidental, and costs."""
    against_key = [n("F", 5, alter=0) for _ in range(8)]
    assert factors_of(against_key, 4, 4, key_fifths=1).get("chromatic", 0.0) > 0.0


# --------------------------------------------------------------------------
# 3. Normal first-position pitches were treated as high register
# --------------------------------------------------------------------------


@pytest.mark.parametrize("step,octave", [("G", 3), ("E", 5), ("G", 5), ("A", 5), ("B", 5)])
def test_first_position_pitches_carry_no_register_demand(step, octave):
    """First position reaches B5 with the fourth finger. Nothing below it is high."""
    assert "register" not in factors_of([n(step, octave) for _ in range(8)], 4, 4)


def test_register_still_rises_above_first_position():
    reachable = rate_measure([n("B", 5) for _ in range(8)], 4, 4)[0]
    high = rate_measure([n("E", 6) for _ in range(8)], 4, 4)[0]
    very_high = rate_measure([n("E", 7) for _ in range(8)], 4, 4)[0]
    assert reachable < high < very_high


# --------------------------------------------------------------------------
# 4. Routine slurs and articulation were charged as bow demand
# --------------------------------------------------------------------------


def test_a_routine_two_note_slur_pattern_is_not_a_bow_problem():
    """Slurring pairs is how a violinist plays most of the time.

    The old feature counted every note under any slur, so this measure scored
    1.0 -- the maximum the feature can produce.
    """
    paired = [n("G", 4, slur="start" if i % 2 == 0 else "stop") for i in range(8)]
    assert factors_of(paired, 4, 4).get("bow_demand", 0.0) < 0.3


def test_a_long_slur_is_a_bow_problem():
    """Sixteen notes in one bow is a distribution demand; four is not."""

    def bow(count: int) -> float:
        notes = [
            n(
                "G",
                4,
                "16th",
                slur="start" if i == 0 else ("stop" if i == count - 1 else "continue"),
            )
            for i in range(count)
        ]
        return factors_of(notes, 4, 4).get("bow_demand", 0.0)

    assert bow(16) > bow(4)


# --------------------------------------------------------------------------
# 5. Speed was counted three times over
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value,count", [("eighth", 8), ("16th", 16)])
def test_subdivision_does_not_repeat_the_note_rate(value, count):
    """Sixteenths of the beat are ordinary; only finer divisions add a demand."""
    assert "subdivision" not in factors_of([n("G", 4, value) for _ in range(count)], 4, 4)


def test_subdivision_still_fires_on_genuinely_fine_division():
    assert "subdivision" in factors_of([n("G", 4, "32nd") for _ in range(32)], 4, 4)


def test_mixing_two_note_values_is_not_rhythmic_complexity():
    """Quarters and eighths in one bar describes most music ever written."""
    plain = [
        n("G", 4, "quarter"),
        n("A", 4, "eighth"),
        n("B", 4, "eighth"),
        n("C", 5, "quarter"),
        n("D", 5, "quarter"),
    ]
    assert "rhythm_complexity" not in factors_of(plain, 4, 4)


def test_tuplets_are_rhythmic_complexity():
    triplets = [n("G", 4, "eighth", tuplet_actual=3, tuplet_normal=2) for _ in range(12)]
    assert "rhythm_complexity" in factors_of(triplets, 4, 4)


# --------------------------------------------------------------------------
# 6. The tempo assumption ignored the beat unit
# --------------------------------------------------------------------------


def test_the_beat_unit_follows_the_meter():
    assert beat_unit(4, 4) == Fraction(1, 4)
    assert beat_unit(2, 4) == Fraction(1, 4)
    assert beat_unit(2, 2) == Fraction(1, 2)
    assert beat_unit(6, 8) == Fraction(3, 8)
    assert beat_unit(9, 8) == Fraction(3, 8)
    assert beat_unit(12, 8) == Fraction(3, 8)
    # 3/8 is conducted both ways depending on tempo and the notation does not
    # settle which, so it stays in eighths rather than being asserted to be one.
    assert beat_unit(3, 8) == Fraction(1, 8)


def test_cut_time_is_faster_than_common_time_at_the_same_marking():
    """Eight eighths, same printed notes, same stated BPM. Cut time is the faster."""
    common = [n("G", 4, "eighth") for _ in range(8)]
    assert rate_measure(common, 2, 2, tempo_bpm=90)[0] > rate_measure(common, 4, 4, tempo_bpm=90)[0]


# --------------------------------------------------------------------------
# 7. The curve rose too fast from zero
# --------------------------------------------------------------------------


def test_the_curve_leaves_the_bottom_of_the_scale_usable():
    """A single modest demand must not land in the middle of the scale.

    This is the shape complaint: the old curve was steepest at zero, so a
    first-position eighth-note etude with one modest demand landed at 3.2.
    """
    assert _saturate(0.0) == 0.0
    assert _saturate(0.5) < 1.5
    assert _saturate(1.0) < 2.5


def test_the_curve_still_reserves_the_top():
    assert _saturate(3.0) < 7.0
    assert _saturate(8.0) > 9.0
    assert _saturate(1000.0) <= 10.0


# --------------------------------------------------------------------------
# The span the scale claims to cover
# --------------------------------------------------------------------------


def test_a_beginner_measure_and_a_concerto_measure_are_far_apart():
    """The scale has to separate the two ends of the repertoire it claims to span.

    Both passages are constructed here and neither is attributed to a piece.
    What is checked is that the rubric's own features move a long way between
    first-position detache eighths at a walking tempo and fast, high, chromatic
    writing under one bow in cut time.
    """
    beginner = [n(step, 4) for step in ("G", "A", "B", "C", "D", "E", "F", "G")]
    beginner_score = rate_measure(beginner, 4, 4, tempo_bpm=90)[0]

    descent = [("E", 6), ("D", 6), ("C", 6), ("B", 5), ("A", 5), ("G", 5), ("F", 5), ("E", 5)]
    concerto = [
        n(
            step,
            octave,
            "16th",
            alter=1 if index % 4 == 0 else 0,
            slur="start" if index == 0 else ("stop" if index == 15 else "continue"),
        )
        for index, (step, octave) in enumerate(descent * 2)
    ]
    concerto_score = rate_measure(concerto, 2, 2, tempo_bpm=88, key_fifths=1)[0]

    assert beginner_score < 2.0, beginner_score
    assert concerto_score > 8.0, concerto_score


def test_an_easy_measure_inside_hard_writing_still_rates_low():
    """No piece is normalized to fill the scale, so context cannot raise a rating.

    A sustained open-string note is a sustained open-string note whether it sits
    in an etude or in a concerto, and it must rate the same in both.
    """
    held = [n("E", 5, "half"), n("E", 5, "half")]
    assert rate_measure(held, 2, 2, tempo_bpm=88, key_fifths=1)[0] < 1.0


# --------------------------------------------------------------------------
# B7: a demand costs what the clock lets it cost
#
# The complaint that prompted this: a single sustained high note rated 4.7 while
# sixteen sixteenths in the same register rated 4.3. Rubric 2.0 was purely
# additive, so only `note_rate` knew anything about time and every other demand
# cost the same whether there were two seconds to place it or eighty
# milliseconds.
# --------------------------------------------------------------------------


def test_pressure_is_bounded_and_rises_with_the_note_rate():
    from src.features.difficulty.rubric import (
        PRESSURE_CEILING,
        PRESSURE_FLOOR,
        execution_pressure,
    )

    assert execution_pressure(0.0) == PRESSURE_FLOOR
    assert execution_pressure(10_000.0) == PRESSURE_CEILING
    values = [execution_pressure(r) for r in (0.5, 2, 4, 6, 8, 10)]
    assert values == sorted(values)
    # A demand is never free just because the passage is slow.
    assert PRESSURE_FLOOR > 0.0


def test_a_sustained_high_note_is_not_a_fast_run():
    """The exact inversion that prompted B7, pinned as an ordering."""
    held = rate_measure([n("E", 7, "whole")], 4, 4)[0]
    run = rate_measure([n("E", 6, "16th") for _ in range(16)], 4, 4)[0]
    assert held < run, (held, run)
    assert held < 2.5, held


@pytest.mark.parametrize(
    "label,slow,fast",
    [
        (
            "octave leaps",
            [n("G", 4, "half"), n("G", 5, "half")],
            [n("G", 4 if i % 2 else 5, "16th") for i in range(16)],
        ),
        (
            "accidentals",
            [n("G", 4, "half", alter=1), n("A", 4, "half", alter=1)],
            [n("G", 4, "16th", alter=1) for _ in range(16)],
        ),
    ],
)
def test_the_same_printed_demand_costs_more_when_there_is_less_time(label, slow, fast):
    assert rate_measure(slow, 4, 4)[0] < rate_measure(fast, 4, 4)[0], label


def test_the_speed_term_itself_is_not_scaled_by_speed():
    """Scaling the note rate by a function of the note rate would count speed
    twice, which is the error rubric 2.0 was written to remove."""
    from src.features.difficulty.rubric import RATE_KEY, WEIGHTS

    notes = [n("G", 4, "16th") for _ in range(16)]
    contribution = factors_of(notes, 4, 4)[RATE_KEY]
    assert contribution <= WEIGHTS[RATE_KEY] + 1e-9
    # Unscaled means it matches the raw feature exactly.
    from src.features.difficulty.rubric import measure_features

    expected = measure_features(notes, 4, 4, 90.0) [RATE_KEY] * WEIGHTS[RATE_KEY]
    assert contribution == pytest.approx(expected, abs=0.01)


def test_reported_contributions_still_sum_to_the_rating():
    """The sidebar prints these and a reader can add them up, so they have to be
    the numbers the score was actually computed from -- not pre-scaling ones."""
    from src.features.difficulty.rubric import _saturate

    notes = [n("E", 6, "16th", alter=1) for _ in range(16)]
    score, factors = rate_measure(notes, 4, 4)
    assert round(_saturate(sum(f.contribution for f in factors)), 1) == pytest.approx(
        score, abs=0.15
    )


def test_a_weight_is_still_the_honest_ceiling_for_its_feature():
    """Pressure scales the feature value, not the weight, so "of 2.2" stays a
    reachable maximum rather than becoming unreachable on every slow page."""
    from src.features.difficulty.rubric import WEIGHTS

    # Fast, high and chromatic: pressure is at its ceiling here.
    notes = [n("E", 7, "32nd", alter=1) for _ in range(32)]
    for factor in rate_measure(notes, 4, 4)[1]:
        assert factor.contribution <= WEIGHTS[factor.key] + 1e-9
