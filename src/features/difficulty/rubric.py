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
"""

from __future__ import annotations

from fractions import Fraction

from src.schemas.music import NoteEvent
from src.schemas.score import DifficultyFactor

RUBRIC_VERSION = "1.0"

# Tempo assumed when the score states none, keyed by beat unit. Conservative
# and disclosed in the UI; the rating recomputes when a real tempo is supplied.
DEFAULT_TEMPO_BPM = 90.0

# Pitch landmarks, as MIDI numbers. Used to describe register demand without
# asserting a position or a string, neither of which notation alone establishes.
_E_STRING_OPEN = 76  # E5
_THIRD_POSITION_ISH = 79  # G5: above this, first position no longer reaches
_HIGH_REGISTER = 84  # C6

# Weights, in points on the 0-10 scale, applied to normalized feature values.
# They sum to more than 10 on purpose: the saturating curve at the end is what
# bounds the result, so several moderate demands can accumulate the way they do
# in reality without any single one being able to max out the scale alone.
WEIGHTS = {
    "note_rate": 3.4,
    "subdivision": 1.8,
    "syncopation": 1.0,
    "chromatic": 1.5,
    "register": 2.2,
    "leaps": 1.6,
    "double_stops": 2.6,
    "bow_demand": 1.2,
    "irregular_rhythm": 1.1,
}

LABELS = {
    "note_rate": "Note rate",
    "subdivision": "Fast subdivision",
    "syncopation": "Off-beat placement",
    "chromatic": "Accidentals",
    "register": "High register",
    "leaps": "Wide leaps",
    "double_stops": "Double stops",
    "bow_demand": "Bow control",
    "irregular_rhythm": "Mixed note values",
}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _saturate(raw: float) -> float:
    """Map accumulated weighted points onto 0-10 with diminishing returns.

    A linear sum would let three moderate demands reach the top of the scale,
    which would make "extremely hard" meaningless. This curve rises quickly
    through the middle where most real music sits and compresses near 10, so the
    top of the scale stays reserved.
    """
    return 10.0 * (1.0 - pow(2.718281828459045, -raw / 4.2))


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

    measure_whole_notes = Fraction(beats, beat_value)
    seconds = float(measure_whole_notes) * (4.0 * 60.0 / max(tempo_bpm, 1.0))
    sounded = [n for n in notes if not n.is_rest]

    # Notes per second. Around 12/s is already virtuosic for a beginner etude.
    rate = (len(sounded) / seconds) if seconds > 0 else 0.0
    f_rate = _clamp01(rate / 12.0)

    # Shortest printed value present, as a power of two below a quarter note.
    shortest = min((n.duration for n in notes), default=Fraction(1, 4))
    f_sub = _clamp01((float(Fraction(1, 4) / shortest) - 1.0) / 7.0) if shortest else 0.0

    # Onsets that do not land on a beat.
    beat_len = Fraction(1, beat_value)
    onset = Fraction(0)
    off_beat = 0
    for n in notes:
        if onset % beat_len != 0:
            off_beat += 1
        onset += n.duration
    f_sync = _clamp01(off_beat / max(1, len(notes)))

    # Printed accidentals, which are chromatic work beyond the key signature.
    accidentals = sum(1 for n in sounded if n.alter != 0)
    f_chrom = _clamp01(accidentals / max(1, len(sounded)) * 2.5)

    midis = [n.midi for n in sounded if n.midi is not None]
    if midis:
        top = max(midis)
        if top <= _E_STRING_OPEN:
            f_reg = 0.0
        elif top <= _THIRD_POSITION_ISH:
            f_reg = 0.35
        elif top <= _HIGH_REGISTER:
            f_reg = 0.7
        else:
            f_reg = 1.0
    else:
        f_reg = 0.0

    # Largest melodic interval. A wide leap is a real demand; it is NOT evidence
    # of a position shift, which notation alone does not establish.
    biggest = 0
    for a, b in zip(midis, midis[1:]):
        biggest = max(biggest, abs(b - a))
    f_leap = _clamp01((biggest - 4) / 14.0)

    # Simultaneities are not represented in this transcription format yet, so
    # this reads 0 rather than guessing. Kept in the rubric because the feature
    # is real and the field is wired for when chords are recognized.
    f_dstop = 0.0

    slurred = sum(1 for n in sounded if n.slur != "none")
    staccato = sum(1 for n in sounded if n.articulation == "staccato")
    f_bow = _clamp01((slurred + staccato) / max(1, len(sounded)))

    # Mixed note values within a measure cost more than a uniform run.
    distinct = len({n.value for n in notes})
    f_irr = _clamp01((distinct - 1) / 3.0)

    return {
        "note_rate": f_rate,
        "subdivision": f_sub,
        "syncopation": f_sync,
        "chromatic": f_chrom,
        "register": f_reg,
        "leaps": f_leap,
        "double_stops": f_dstop,
        "bow_demand": f_bow,
        "irregular_rhythm": f_irr,
    }


def rate_measure(
    notes: list[NoteEvent],
    beats: int,
    beat_value: int,
    tempo_bpm: float = DEFAULT_TEMPO_BPM,
    key_fifths: int = 0,
) -> tuple[float, list[DifficultyFactor]]:
    """Rate one measure and explain the rating. Returns (score, factors)."""
    features = measure_features(notes, beats, beat_value, tempo_bpm, key_fifths)
    raw = sum(WEIGHTS[k] * v for k, v in features.items())
    score = round(_saturate(raw), 1)

    factors = [
        DifficultyFactor(
            key=k,
            label=LABELS[k],
            contribution=round(WEIGHTS[k] * v, 2),
            detail="",
        )
        for k, v in sorted(features.items(), key=lambda kv: -WEIGHTS[kv[0]] * kv[1])
        if v > 0.02
    ]
    return score, factors


# Aggregation weights for a phrase rating. Biased toward the peak so a single
# demanding measure inside an otherwise easy phrase is not averaged into
# invisibility -- docs/product-spec.md requires exactly this.
PHRASE_MEAN_WEIGHT = 0.6
PHRASE_PEAK_WEIGHT = 0.4


def aggregate_phrase(measure_scores: list[float | None]) -> tuple[float | None, float | None]:
    """Combine member measure ratings into (phrase_score, peak).

    Unrated measures are skipped rather than counted as zero. A phrase with no
    rated measure at all stays unrated: (None, None).
    """
    rated = [s for s in measure_scores if s is not None]
    if not rated:
        return None, None
    mean = sum(rated) / len(rated)
    peak = max(rated)
    combined = PHRASE_MEAN_WEIGHT * mean + PHRASE_PEAK_WEIGHT * peak
    return round(combined, 1), round(peak, 1)
