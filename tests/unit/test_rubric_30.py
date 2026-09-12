"""Rubric 3.0: left-hand estimates, double stops, key remoteness, tempo words.

Each test is written against notation, not against the constants, so the
weights can be retuned without these quietly passing for the wrong reason.
The anchor tests pin the scale to graded-syllabus descriptions (see
docs/music-pedagogy.md, "Difficulty rubric anchors").
"""

from __future__ import annotations

import pytest

from src.features.difficulty import lefthand
from src.features.difficulty.rubric import RUBRIC_VERSION, rate_measure, rubric_explanation
from src.features.difficulty.tempo import tempo_from_words
from src.schemas.music import NoteEvent


def n(step: str, octave: int, value: str = "eighth", **kw) -> NoteEvent:
    return NoteEvent(is_rest=False, step=step, octave=octave, value=value, **kw)


def factors_of(*args, **kwargs) -> dict[str, float]:
    return {f.key: f.contribution for f in rate_measure(*args, **kwargs)[1]}


# --------------------------------------------------------------------------
# Left-hand estimate
# --------------------------------------------------------------------------


def test_likely_string_is_the_highest_open_string_at_or_below_the_pitch():
    assert lefthand.likely_string(55) == 0  # G3 open
    assert lefthand.likely_string(60) == 0  # C4 on G
    assert lefthand.likely_string(62) == 1  # D4 open
    assert lefthand.likely_string(76) == 3  # E5 open
    assert lefthand.likely_string(88) == 3  # E6 on E


def test_first_position_needs_no_relocation():
    # G major scale, two octaves' worth of first position: G3 to B5.
    midis = [55, 57, 59, 60, 62, 64, 66, 67, 69, 71, 72, 74, 76, 78, 79, 81, 83]
    changes, _ = lefthand.position_changes(midis)
    assert changes == 0


def test_a_single_excursion_counts_once_not_once_per_rung():
    # One climb to a high note is one relocation, not a ladder of intermediate
    # positions; the lazy-hand model stays up while the low notes remain
    # reachable on a lower string.
    midis = [67, 69, 71, 91, 93, 91, 71, 69, 67]
    changes, _ = lefthand.position_changes(midis)
    assert changes == 1


def test_double_stop_hardness_orders_intervals_the_way_teachers_do():
    open_fifth = NoteEvent(is_rest=False, step="A", octave=4, value="quarter", chord_midis=[62])
    third = NoteEvent(is_rest=False, step="B", octave=4, value="quarter", chord_midis=[67])
    tenth = NoteEvent(is_rest=False, step="B", octave=5, value="quarter", chord_midis=[67])
    assert lefthand.double_stop_hardness(open_fifth) < lefthand.double_stop_hardness(third)
    assert lefthand.double_stop_hardness(third) <= lefthand.double_stop_hardness(tenth)


# --------------------------------------------------------------------------
# Rubric features
# --------------------------------------------------------------------------


def test_double_stops_are_no_longer_scored_zero():
    single = [n("B", 4, "quarter") for _ in range(4)]
    thirds = [n("B", 4, "quarter", chord_midis=[67]) for _ in range(4)]
    assert factors_of(single, 4, 4).get("double_stops", 0.0) == 0.0
    assert factors_of(thirds, 4, 4)["double_stops"] > 0.5
    assert rate_measure(thirds, 4, 4)[0] > rate_measure(single, 4, 4)[0] + 1.0


def test_constant_string_crossing_costs_more_than_a_scale():
    scale = [n(s, 4) for s in "GABCDEF"] + [n("G", 5)]
    # Alternating G string and A string: every transition skips the D string.
    bariolage = [n("A", 3), n("A", 4)] * 4
    assert factors_of(bariolage, 4, 4)["string_crossings"] > factors_of(scale, 4, 4).get("string_crossings", 0.0)


def test_position_changes_are_labelled_as_estimates():
    expl = rubric_explanation(120.0, True)
    by_key = {w["key"]: w for w in expl["weights"]}
    assert by_key["position_changes"]["estimated"] is True
    assert by_key["note_rate"]["estimated"] is False
    assert RUBRIC_VERSION == "3.0"


def test_remote_key_costs_more_than_open_string_key():
    line = [n(s, 4) for s in "GABCDEFG"]
    assert factors_of(line, 4, 4, key_fifths=1).get("key_remoteness", 0.0) == 0.0
    assert factors_of(line, 4, 4, key_fifths=-5)["key_remoteness"] > 0.0


# --------------------------------------------------------------------------
# Syllabus anchors
# --------------------------------------------------------------------------


def test_first_position_eighths_stay_beginner_friendly():
    line = [n(s, 4) for s in "GABCDEFG"]
    assert rate_measure(line, 4, 4, tempo_bpm=80)[0] < 2.0


def test_concerto_texture_reaches_the_top_band():
    # Sixteenth thirds high on the E string at a fast tempo.
    fast = [n("E", 6, "16th", chord_midis=[85]) for _ in range(16)]
    assert rate_measure(fast, 4, 4, tempo_bpm=140)[0] > 8.0


def test_held_notes_stay_low_whatever_the_register():
    held = [n("E", 6, "whole")]
    assert rate_measure(held, 4, 4, tempo_bpm=120)[0] < 3.0


# --------------------------------------------------------------------------
# Tempo words
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,low,high",
    [("Presto", 160, 190), ("Andante", 70, 100), ("Allegro moderato", 100, 130)],
)
def test_tempo_words_give_a_plausible_bpm(text, low, high):
    reading = tempo_from_words(text)
    assert reading is not None
    bpm, evidence = reading
    assert low <= bpm <= high
    assert text.split()[0].lower() in evidence.lower()


def test_unrelated_text_is_not_a_tempo():
    assert tempo_from_words("Violino I") is None
