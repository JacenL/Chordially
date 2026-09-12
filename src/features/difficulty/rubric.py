"""The 0.0-10.0 difficulty rubric. Deterministic, explainable, and heuristic.

What this is: a transparent product heuristic that estimates how demanding a
passage is to play, under a stated tempo, from features that are actually
visible in the notation.

What it is not: a measurement of anyone's proficiency, and not a validated
examination grade. docs/music-pedagogy.md is explicit that no source here
establishes a numeric scale; the sources support individual practice techniques,
not this number. The one decimal place is for ordering and comparison, not a
claim of precision.

Design rules that the tests enforce:

* Identical validated input and settings produce an identical rating.
* A measure that could not be analyzed is unrated (None), never 0.0. Zero means
  genuinely easy; None means unknown, and the two must look different.
* Recognition confidence never multiplies difficulty. A blurry easy measure is
  easy, not hard.
* Nothing asserts a shift, a string choice, or a fingering that the notation
  does not establish. Features are named for what is printed.
* The scale is absolute and shared across pieces. No piece is normalized to
  fill it; a beginner etude is supposed to sit near the bottom of a scale whose
  top belongs to concerto writing.

Version 2.0 rewrote the features after measuring version 1.0 against the
Wohlfahrt fixture, where straightforward first-position eighth-note studies were
coming out at 3.2-5.1 -- "Advanced Beginner" to "Competent level" for music
printed as the second study in a beginner's book. Seven separate causes were
found and each is fixed at its source rather than by subtracting a constant:

1.  **Ordinary off-beat notes were counted as syncopation.** Every second
    eighth note in 4/4 sits off the quarter-note beat, so straight eighths
    scored 0.50 and straight sixteenths 0.75 on a feature meant to detect
    displaced accents. Syncopation now requires an accent actually displaced:
    an off-beat attack that sustains through the next beat, is tied across it,
    or replaces a beat the composer left silent.
2.  **Key-signature notes were charged as accidentals.** The MusicXML path
    reports sounding alteration, so every F# in a G-major piece read as a
    printed accidental. Accidentals are now what differs from the key
    signature, which is the definition a musician would use.
3.  **First position was treated as high register.** The old ceiling for "no
    register demand" was E5, the open E string. First position reaches B5 with
    the fourth finger, so normal first-position writing was charged up to 1.54
    points. The threshold is now B5 and the ramp above it is continuous.
4.  **Routine slurs were charged as bow demand.** Any note under any slur
    counted, so an ordinary two-note slur pattern scored 1.0 -- the maximum.
    Bow demand is now long slurs (bow distribution), frequent changes between
    slurred and separate, and wall-to-wall articulation marks.
5.  **Speed was counted three times.** `note_rate`, `subdivision` and
    `irregular_rhythm` all rose together with tempo and note value. Note rate
    is now the single speed term; subdivision only registers divisions finer
    than sixteenths of the beat; and the third feature was redefined as
    rhythmic *complexity* (tuplets, dots, ties across beats) rather than "more
    than one note value present", which described most music ever written.
6.  **The tempo assumption ignored the beat unit.** Tempo was read as a
    quarter-note pulse in every meter, so cut time was rated as if it were half
    as fast and 6/8 as if its pulse were the eighth. BPM now refers to the
    notated beat.
7.  **The curve rose too fast from zero.** The old exponential had a slope of
    2.4 points per raw point at the origin, so any single modest demand already
    landed in the middle of the scale. The curve now starts flat and steepens.
"""

from __future__ import annotations

import math
from fractions import Fraction

from src.schemas.music import NoteEvent
from src.schemas.score import DifficultyFactor

RUBRIC_VERSION = "2.0"

# Tempo assumed when the score states none, in **notated beats** per minute --
# see `beat_unit` below. Conservative and disclosed in the UI; the rating
# recomputes when a real tempo is supplied.
DEFAULT_TEMPO_BPM = 90.0

# Pitch landmarks, as MIDI numbers. Used to describe register demand without
# asserting a position or a string, neither of which notation alone establishes.
#
# B5 is where first position stops: fourth finger on the E string. Everything at
# or below it is reachable without leaving the position a beginner learns first,
# so it carries no register demand at all. That is the correction that matters
# here -- the previous ceiling was the *open* E string, which charged ordinary
# first-position writing as though it were high playing.
FIRST_POSITION_TOP = 83  # B5
VIOLIN_TOP = 100  # E7, about as high as standard repertoire goes

# Note rate, in sounded notes per second, that the scale is stretched between.
# The floor is not zero: one note a second is a slow melody, and calling that
# "some difficulty" would put every piece of music above the bottom of the
# scale. The ceiling is where a passage is fast for anyone.
RATE_FLOOR = 1.0
RATE_CEILING = 13.0

# How much the clock amplifies every demand other than the note rate itself.
#
# This is the answer to a complaint that was obviously right: a single sustained
# high note rated 4.7 while sixteen sixteenth notes in the same register rated
# 4.3. The rubric was purely additive, so only `note_rate` knew anything about
# time -- an octave leap, a high position or a printed accidental cost exactly
# the same whether there were two seconds to place it or eighty milliseconds.
#
# That is not how any of those demands work. What makes a leap hard is arriving
# in tune *in the time available*; given a half note you can hear the note, feel
# the frame and adjust, and given a sixteenth you cannot. So every execution
# demand is scaled by the rate at which notes are arriving.
#
# The scale crosses 1.0 at around six notes a second -- a sixteenth-note run at
# a walking tempo, which is where the old weights were implicitly calibrated --
# so this redistributes rather than merely deflating: slow demands fall a long
# way, and demands under real time pressure rise.
#
# The floor is not zero. A high position played slowly is still a high position;
# time makes it easier, never free.
PRESSURE_FLOOR = 0.35
PRESSURE_CEILING = 1.5
PRESSURE_PER_NOTE_PER_SECOND = 0.11

# The one feature the pressure is computed *from*, and so the one it must not be
# applied to. Scaling the speed term by a function of speed would count speed
# twice -- the exact error rubric 2.0 was written to remove.
RATE_KEY = "note_rate"

# Weights, in points on the 0-10 scale, applied to normalized feature values.
# They sum to more than 10 on purpose: the saturating curve at the end is what
# bounds the result, so several moderate demands can accumulate the way they do
# in reality without any single one being able to max out the scale alone.
WEIGHTS = {
    "note_rate": 3.2,
    "subdivision": 0.8,
    "syncopation": 1.0,
    "chromatic": 1.4,
    "register": 2.2,
    "leaps": 1.6,
    "double_stops": 2.6,
    "bow_demand": 1.4,
    "rhythm_complexity": 1.0,
}

LABELS = {
    "note_rate": "Note rate",
    "subdivision": "Fine subdivision",
    "syncopation": "Displaced accents",
    "chromatic": "Accidentals outside the key",
    "register": "Register above first position",
    "leaps": "Wide leaps",
    "double_stops": "Double stops",
    "bow_demand": "Bow demand",
    "rhythm_complexity": "Rhythmic complexity",
}

# The same nine demands said the way a player would say them.
#
# LABELS above name the feature; these say what it means for the person holding
# the instrument. Both exist because they answer different questions: a reader
# comparing two passages wants the noun, and a beginner opening a passage for
# the first time wants to be told what to look out for. The numbers are not
# replaced by this -- they move one disclosure deeper, where someone who wants
# to argue with the rubric can still reach them.
PLAIN = {
    "note_rate": "the notes come quickly",
    "subdivision": "the beat is split very finely",
    "syncopation": "the accents land off the beat",
    "chromatic": "there are accidentals to watch for",
    "register": "it climbs above first position",
    "leaps": "the line jumps a long way",
    "double_stops": "two strings sound at once",
    "bow_demand": "the bowing asks for care",
    "rhythm_complexity": "the rhythm needs counting out",
}


def plain_reason(key: str) -> str:
    """The player-facing phrase for a rubric feature, or the raw key if unknown."""
    return PLAIN.get(key, key.replace("_", " "))

# The curve. `raw` is the weighted sum of normalized features; KNEE and SHAPE
# turn it into a 0-10 rating.
#
# SHAPE > 1 is the whole point of the rewrite. With SHAPE = 1 (the old curve)
# the slope at the origin is maximal, so the very first fraction of a point of
# demand moved the rating furthest -- which is why a beginner etude with one
# modest demand landed at 3.2. Above 1 the curve leaves zero flat, rises through
# the middle where most real music sits, and compresses near 10 so the top of
# the scale stays reserved. These two values were set by measuring the Wohlfahrt
# fixture, not chosen in the abstract: they put its first-position eighth-note
# study at 1.1 and its sixteenth-note study at 2.9.
KNEE = 3.2
SHAPE = 1.22


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _saturate(raw: float) -> float:
    """Map accumulated weighted points onto 0-10 with a flat start and a ceiling."""
    if raw <= 0.0:
        return 0.0
    return 10.0 * (1.0 - math.exp(-((raw / KNEE) ** SHAPE)))


# --------------------------------------------------------------------------
# Meter, key and pitch helpers -- exact arithmetic, no guessing
# --------------------------------------------------------------------------


def beat_unit(beats: int, beat_value: int) -> Fraction:
    """Length of one notated beat, as a fraction of a whole note.

    This is what a tempo marking counts, and reading it wrong distorts every
    rating in the piece. Cut time is felt in half notes, not quarters; 6/8 is
    felt in two dotted beats, not six eighths. The previous implementation
    assumed a quarter-note pulse in every meter, which rated alla breve music at
    half its real speed.

    3/8 is deliberately left in eighths. It is conducted both ways depending on
    tempo, and the notation alone does not settle which.
    """
    unit = Fraction(1, beat_value)
    if beat_value >= 8 and beats > 3 and beats % 3 == 0:
        return unit * 3
    return unit


_SHARP_ORDER = ("F", "C", "G", "D", "A", "E", "B")
_FLAT_ORDER = ("B", "E", "A", "D", "G", "C", "F")


def key_alteration(step: str | None, key_fifths: int | None) -> int:
    """What the key signature alone does to this letter name.

    F in a one-sharp key is F#, and playing it is not a chromatic demand -- it
    is the key. Counting it as an accidental was inflating every rating in every
    piece that was not in C major.
    """
    if not step or not key_fifths:
        return 0
    letter = step.upper()
    if key_fifths > 0:
        return 1 if letter in _SHARP_ORDER[: min(7, key_fifths)] else 0
    return -1 if letter in _FLAT_ORDER[: min(7, -key_fifths)] else 0


def is_printed_accidental(note: NoteEvent, key_fifths: int | None) -> bool:
    """Whether this note carries an accidental the key signature does not supply.

    `alter` is the sounding alteration by the time a note reaches here --
    adapters normalize to that convention at the boundary, in
    `src/server/analysis/assemble.py`, where the authoritative key signature for
    the measure is known.
    """
    if note.is_rest or note.step is None:
        return False
    return note.alter != key_alteration(note.step, key_fifths)


def _slur_runs(notes: list[NoteEvent]) -> list[int]:
    """Lengths of individual slur groups, in note counts.

    A new group opens at every "start", which is what separates four two-note
    slurs from one eight-note slur -- the difference between ordinary detache
    bowing and a bow-distribution problem. Where the source marks slurred notes
    only as "continue" and never says where a slur begins, a run of them reads
    as one group, which is the most the notation available actually establishes.
    """
    runs: list[int] = []
    current = 0
    for note in notes:
        if note.slur == "none":
            if current:
                runs.append(current)
                current = 0
        elif note.slur == "start":
            if current:
                runs.append(current)
            current = 1
        else:
            current += 1
    if current:
        runs.append(current)
    return runs


# --------------------------------------------------------------------------
# Features
# --------------------------------------------------------------------------


def measure_features(
    notes: list[NoteEvent],
    beats: int,
    beat_value: int,
    tempo_bpm: float,
    key_fifths: int = 0,
) -> dict[str, float]:
    """Normalized 0-1 feature values for one measure. Pure and deterministic."""
    if not notes:
        return {k: 0.0 for k in WEIGHTS}

    unit = beat_unit(beats, beat_value)
    measure_whole_notes = Fraction(beats, beat_value)
    beats_in_measure = float(measure_whole_notes / unit)
    seconds = beats_in_measure * (60.0 / max(tempo_bpm, 1.0))
    sounded = [n for n in notes if not n.is_rest]

    # ---------------------------------------------------------------- speed
    # The one place speed is counted. `subdivision` used to count it a second
    # time and `irregular_rhythm` a third, because at a fixed tempo all three
    # rose together.
    rate = (len(sounded) / seconds) if seconds > 0 else 0.0
    f_rate = _clamp01((rate - RATE_FLOOR) / (RATE_CEILING - RATE_FLOOR))

    # ---------------------------------------------------------- subdivision
    # How finely the beat is divided, counted only past the point where it stops
    # being ordinary. Eighths and sixteenths of the beat are how most music is
    # written and cost nothing here; 32nds and beyond are a reading demand over
    # and above the raw speed already counted above.
    shortest = min((n.duration for n in notes), default=unit)
    divisions = float(unit / shortest) if shortest > 0 else 1.0
    f_sub = _clamp01((divisions - 4.0) / 8.0)

    # --------------------------------------------------------- syncopation
    # An accent actually displaced, not merely a note that starts between
    # beats. Straight eighths and straight sixteenths score zero here, which is
    # the single largest correction in this version of the rubric.
    displaced = 0
    onset = Fraction(0)
    for index, note in enumerate(notes):
        end = onset + note.duration
        on_beat = (onset % unit) == 0
        if not note.is_rest and not on_beat:
            next_beat = (onset // unit + 1) * unit
            previous = notes[index - 1] if index else None
            crosses = end > next_beat
            tied_onward = note.tie in ("start", "continue")
            after_silent_beat = (
                previous is not None
                and previous.is_rest
                and ((onset - previous.duration) % unit) == 0
            )
            if crosses or tied_onward or after_silent_beat:
                displaced += 1
        onset = end
    f_sync = _clamp01(displaced / max(1, len(sounded)) * 2.5)

    # ------------------------------------------------------------ chromatic
    printed = sum(1 for n in sounded if is_printed_accidental(n, key_fifths))
    f_chrom = _clamp01(printed / max(1, len(sounded)) * 2.5)

    # ------------------------------------------------------------- register
    midis = [n.midi for n in sounded if n.midi is not None]
    if midis:
        top = max(midis)
        f_reg = _clamp01((top - FIRST_POSITION_TOP) / (VIOLIN_TOP - FIRST_POSITION_TOP))
    else:
        f_reg = 0.0

    # ---------------------------------------------------------------- leaps
    # Two separate things, because one of them alone is noise. The widest
    # interval says how far the hand has to travel at its worst; how *often* the
    # line leaps says whether the passage is built out of leaps or merely
    # contains one. A wide interval is NOT evidence of a position shift, which
    # notation alone does not establish.
    #
    # Nothing up to a perfect fifth counts. A fifth is one finger across two
    # strings and a fourth sits inside the first-position hand frame; charging
    # those made ordinary broken-chord writing look like leaping.
    intervals = [abs(b - a) for a, b in zip(midis, midis[1:])]
    biggest = max(intervals, default=0)
    f_widest = _clamp01((biggest - 7) / 12.0)
    leapy = sum(1 for i in intervals if i >= 5) / max(1, len(intervals))
    f_often = _clamp01((leapy - 0.2) / 0.6)
    f_leap = _clamp01(0.6 * f_widest + 0.4 * f_often)

    # --------------------------------------------------------- double stops
    # Simultaneities are not represented in this transcription format yet, so
    # this reads 0 rather than guessing. Kept in the rubric because the feature
    # is real and the field is wired for when chords are recognized.
    f_dstop = 0.0

    # ----------------------------------------------------------- bow demand
    # Three separate demands, none of which is "a slur exists". A two-note slur
    # pattern is how a violinist plays most of the time.
    runs = _slur_runs(sounded)
    longest_slur = max(runs, default=0)
    f_long_slur = _clamp01((longest_slur - 4) / 8.0)

    changes = 0
    previous_slurred: bool | None = None
    for note in sounded:
        slurred = note.slur != "none"
        if previous_slurred is not None and slurred != previous_slurred:
            changes += 1
        previous_slurred = slurred
    f_pattern = _clamp01((changes - 1) / 6.0)

    marked = sum(1 for n in sounded if n.articulation in ("staccato", "accent"))
    f_marked = _clamp01((marked / max(1, len(sounded)) - 0.5) * 2.0)

    f_bow = _clamp01(0.55 * f_long_slur + 0.30 * f_pattern + 0.15 * f_marked)

    # --------------------------------------------------- rhythmic complexity
    # What makes a rhythm hard to *read and place*, as distinct from fast. The
    # previous version charged any measure containing more than one note value,
    # which is most music; three or more distinct values is where a rhythm
    # starts needing to be counted out.
    distinct = len({n.duration for n in notes})
    f_distinct = _clamp01((distinct - 2) / 2.0)
    has_tuplet = 1.0 if any(n.tuplet_actual for n in notes) else 0.0
    has_dots = 1.0 if any(n.dots for n in notes) else 0.0

    tied_across = 0
    onset = Fraction(0)
    for note in notes:
        if note.tie in ("start", "continue"):
            next_beat = (onset // unit + 1) * unit
            if onset + note.duration > next_beat:
                tied_across += 1
        onset += note.duration
    f_tied = _clamp01(tied_across / max(1, len(notes)) * 3.0)

    f_irr = _clamp01(
        0.35 * f_distinct + 0.30 * has_tuplet + 0.15 * has_dots + 0.30 * f_tied
    )

    return {
        "note_rate": f_rate,
        "subdivision": f_sub,
        "syncopation": f_sync,
        "chromatic": f_chrom,
        "register": f_reg,
        "leaps": f_leap,
        "double_stops": f_dstop,
        "bow_demand": f_bow,
        "rhythm_complexity": f_irr,
    }


# Feature detail lines, written from the measured value so the sidebar can say
# what was actually seen rather than repeating the feature's name.
def _detail(key: str, value: float, notes: list[NoteEvent], key_fifths: int) -> str:
    sounded = [n for n in notes if not n.is_rest]
    if key == "register" and value > 0:
        top = max((n.midi for n in sounded if n.midi is not None), default=None)
        if top is not None:
            return f"reaches {_pitch_name(top)}, above first position"
    if key == "leaps" and value > 0:
        midis = [n.midi for n in sounded if n.midi is not None]
        biggest = max((abs(b - a) for a, b in zip(midis, midis[1:])), default=0)
        return f"largest interval {biggest} semitones"
    if key == "chromatic" and value > 0:
        printed = sum(1 for n in sounded if is_printed_accidental(n, key_fifths))
        return f"{printed} printed accidental{'' if printed == 1 else 's'}"
    if key == "syncopation" and value > 0:
        return "an attack lands off the beat and carries through it"
    return ""


_PITCH_LETTERS = ("C", "C#", "D", "E-flat", "E", "F", "F#", "G", "A-flat", "A", "B-flat", "B")


def _pitch_name(midi: int) -> str:
    return f"{_PITCH_LETTERS[midi % 12]}{midi // 12 - 1}"


def notes_per_second(
    notes: list[NoteEvent], beats: int, beat_value: int, tempo_bpm: float
) -> float:
    """Sounded notes per second, the measure's one speed fact.

    Shared by the note-rate feature and by `execution_pressure` so the two can
    never disagree about how fast the music is going.
    """
    unit = beat_unit(beats, beat_value)
    beats_in_measure = float(Fraction(beats, beat_value) / unit)
    seconds = beats_in_measure * (60.0 / max(tempo_bpm, 1.0))
    sounded = sum(1 for n in notes if not n.is_rest)
    return (sounded / seconds) if seconds > 0 else 0.0


def execution_pressure(rate: float) -> float:
    """How much the clock amplifies an execution demand, given the note rate.

    Below 1.0 the passage gives you time to place things; above it, it does not.
    See the constants above for why this exists and where it is anchored.
    """
    raw = PRESSURE_FLOOR + rate * PRESSURE_PER_NOTE_PER_SECOND
    return max(PRESSURE_FLOOR, min(PRESSURE_CEILING, raw))


def rate_measure(
    notes: list[NoteEvent],
    beats: int,
    beat_value: int,
    tempo_bpm: float = DEFAULT_TEMPO_BPM,
    key_fifths: int = 0,
) -> tuple[float, list[DifficultyFactor]]:
    """Rate one measure and explain the rating. Returns (score, factors).

    The pressure scaling is applied to the *feature values*, not to the weights,
    which keeps two things true that the sidebar depends on: the reported
    contributions still sum to the number they explain, and each weight is still
    the honest ceiling for its feature -- approached only when the music is going
    fast enough for that demand to cost everything it can, and never exceeded.
    """
    features = measure_features(notes, beats, beat_value, tempo_bpm, key_fifths)
    pressure = execution_pressure(
        notes_per_second(notes, beats, beat_value, tempo_bpm)
    )
    # Clamped back to 1.0 on the way out. Pressure can carry a feature *toward*
    # its weight and never past it, so "+1.4 of 1.4" in the sidebar stays a true
    # statement about a ceiling rather than a number a reader can catch
    # exceeding its own maximum.
    scaled = {
        key: value if key == RATE_KEY else _clamp01(value * pressure)
        for key, value in features.items()
    }

    raw = sum(WEIGHTS[k] * v for k, v in scaled.items())
    score = round(_saturate(raw), 1)

    factors = [
        DifficultyFactor(
            key=k,
            label=LABELS[k],
            contribution=round(WEIGHTS[k] * v, 2),
            detail=_detail(k, features[k], notes, key_fifths),
        )
        for k, v in sorted(scaled.items(), key=lambda kv: -WEIGHTS[kv[0]] * kv[1])
        if v > 0.02
    ]
    return score, factors


# Aggregation weights for a phrase or section rating. Biased toward the peak so
# a single demanding measure inside an otherwise easy span is not averaged into
# invisibility -- docs/product-spec.md requires exactly this.
PHRASE_MEAN_WEIGHT = 0.6
PHRASE_PEAK_WEIGHT = 0.4


def aggregate_phrase(measure_scores: list[float | None]) -> tuple[float | None, float | None]:
    """Combine member measure ratings into (score, peak).

    Unrated measures are skipped rather than counted as zero. A span with no
    rated measure at all stays unrated: (None, None). Used for both phrases and
    practice sections, so the two levels cannot drift apart.
    """
    rated = [s for s in measure_scores if s is not None]
    if not rated:
        return None, None
    mean = sum(rated) / len(rated)
    peak = max(rated)
    combined = PHRASE_MEAN_WEIGHT * mean + PHRASE_PEAK_WEIGHT * peak
    return round(combined, 1), round(peak, 1)


# What the rubric demonstrably cannot see. Kept next to the weights because it
# is the other half of the same claim: a rating built from these features is
# silent about everything below, and a number presented without that context
# invites the reader to assume it covers more than it does.
#
# Each entry names a thing a violinist would reasonably expect to affect
# difficulty, and why this rubric has nothing to say about it.
BLIND_SPOTS: list[str] = [
    "Bowing beyond what is printed — slurs are read, but bow distribution, "
    "retakes and the plan for the whole phrase are not.",
    "Fingering. Printed digits are read where they appear; nothing is inferred, "
    "because the notation does not establish a fingering.",
    "String choice and string crossings, which follow from fingering rather "
    "than from pitch alone.",
    "Shifts. A wide interval is counted as a wide interval, never asserted to "
    "be a position change.",
    "Double stops and chords, which this transcription format does not yet "
    "represent. The feature is wired and always reads zero.",
    "Your hand, your instrument and your setup.",
    "Your level. The rating describes what the passage demands, not whether it "
    "is hard for you.",
    "How the passage sounds. PracticeMap never hears you play.",
]


def rubric_explanation(tempo_bpm: float, tempo_is_assumed: bool) -> dict:
    """The rubric, described from the constants that implement it.

    Built here rather than written into a template on purpose: a hand-written
    explanation of a rubric is a second implementation of it, and it would
    eventually disagree with the first. Everything below is read from WEIGHTS,
    LABELS and the curve actually used.
    """
    return {
        "version": RUBRIC_VERSION,
        "tempo": f"{tempo_bpm:.0f} BPM"
        + (" (assumed — none is printed)" if tempo_is_assumed else " (you supplied this)")
        + ", counted in the notated beat",
        "scale": (
            "Each feature below is measured from the printed notation, scaled to "
            "0–1, and multiplied by its weight. The weights sum to "
            f"{sum(WEIGHTS.values()):.1f}, more than 10, because the total is then "
            "put through a curve that starts flat and compresses near the top. "
            "That is what lets several moderate demands accumulate the way they "
            "do in reality, while a single modest one stays near the bottom of "
            "the scale where it belongs. The scale is the same for every piece: "
            "nothing is stretched to fill it."
        ),
        "pressure": (
            "Every demand except the note rate is scaled by how fast the notes "
            "are arriving. A wide leap, a high position or an accidental is hard "
            "because it has to be executed in the time available — given a half "
            "note you can hear it, feel the frame and adjust; given a sixteenth "
            "you cannot. So the same printed interval costs more in a fast "
            "passage than in a slow one, and a sustained note is never rated as "
            "though it were a run."
        ),
        "weights": [
            {"key": key, "label": LABELS[key], "weight": f"{weight:.1f}"}
            for key, weight in sorted(WEIGHTS.items(), key=lambda kv: -kv[1])
        ],
        "blindSpots": list(BLIND_SPOTS),
        "review": (
            "No violinist has reviewed this scale. The category labels and cut "
            "points are PracticeMap's own choices, not a validated grading "
            "system. fixtures/expected/review-phrases.md is the packet a teacher "
            "would mark up."
        ),
    }
