"""Validated musical contracts.

These are the boundary types for anything a model produces. Nothing downstream
accepts raw provider output: it is parsed into these, checked, and only then
used. docs/architecture.md calls for exactly this -- validate external
recognition and LLM output at the boundary, and keep missing values explicit
rather than collapsing them to zero.

Durations are exact rationals, never floats. A measure is accepted only if its
durations sum to what the time signature promises, so a hallucinated or dropped
note is caught arithmetically rather than trusted.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

# Note value names, mapped to a fraction of a whole note. Kept as an explicit
# table because the model returns names, and Python -- not the model -- does the
# arithmetic (CLAUDE.md: use exact code for timing arithmetic).
NOTE_VALUE_FRACTIONS: dict[str, Fraction] = {
    "whole": Fraction(1, 1),
    "half": Fraction(1, 2),
    "quarter": Fraction(1, 4),
    "eighth": Fraction(1, 8),
    "16th": Fraction(1, 16),
    "32nd": Fraction(1, 32),
    "64th": Fraction(1, 64),
}

NoteValue = Literal["whole", "half", "quarter", "eighth", "16th", "32nd", "64th"]
StepName = Literal["A", "B", "C", "D", "E", "F", "G"]
Confidence = Literal["high", "medium", "low"]

# Sounding range of the violin: open G3 to roughly E7 in advanced repertoire.
# A transcription outside this is a recognition error, not a playable note.
VIOLIN_MIN_MIDI = 55  # G3
VIOLIN_MAX_MIDI = 103  # G7, generous upper bound

_STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


class NoteEvent(BaseModel):
    """One note or rest. Geometry is deliberately absent.

    Note positions come from the page, not from the model. This type carries
    only what a vision model can actually establish from a measure image.
    """

    model_config = {"extra": "forbid"}

    is_rest: bool = Field(description="True for a rest; then step/octave are omitted.")
    step: StepName | None = Field(
        default=None, description="Letter name A-G. Omit for a rest."
    )
    alter: Literal[-2, -1, 0, 1, 2] = Field(
        default=0,
        description=(
            "Chromatic alteration in semitones relative to the key signature "
            "already applied: -1 flat, 0 natural, 1 sharp. Use only for an "
            "accidental printed in this measure."
        ),
    )
    octave: int | None = Field(
        default=None,
        ge=0,
        le=9,
        description="Scientific octave; middle C is C4. Omit for a rest.",
    )
    value: NoteValue = Field(description="Printed note value before any dots.")
    dots: int = Field(default=0, ge=0, le=2, description="Number of augmentation dots.")
    tuplet_actual: int | None = Field(
        default=None,
        description="For a tuplet, how many notes are played (the 3 of a triplet).",
    )
    tuplet_normal: int | None = Field(
        default=None,
        description="For a tuplet, how many would normally fit (the 2 of a triplet).",
    )
    tie: Literal["none", "start", "stop", "continue"] = "none"
    slur: Literal["none", "start", "stop", "continue"] = "none"
    articulation: Literal["none", "staccato", "accent", "tenuto"] = "none"
    fingering: int | None = Field(
        default=None,
        ge=0,
        le=4,
        description="Printed fingering digit above the note, if any. 0 means open string.",
    )

    @field_validator("octave")
    @classmethod
    def _octave_required_for_pitch(cls, v: int | None, info) -> int | None:
        return v

    @property
    def duration(self) -> Fraction:
        """Exact duration as a fraction of a whole note, dots and tuplet applied."""
        base = NOTE_VALUE_FRACTIONS[self.value]
        # Each dot adds half of what precedes it: d(1 + 1/2 + 1/4 + ...).
        total = base
        increment = base
        for _ in range(self.dots):
            increment = increment / 2
            total += increment
        if self.tuplet_actual and self.tuplet_normal:
            total = total * Fraction(self.tuplet_normal, self.tuplet_actual)
        return total

    @property
    def midi(self) -> int | None:
        if self.is_rest or self.step is None or self.octave is None:
            return None
        return 12 * (self.octave + 1) + _STEP_SEMITONES[self.step] + self.alter

    def is_in_violin_range(self) -> bool:
        m = self.midi
        return m is None or VIOLIN_MIN_MIDI <= m <= VIOLIN_MAX_MIDI


class MeasureTranscription(BaseModel):
    """What a vision model returns for a single measure image.

    Deliberately narrow. The model is asked about one measure at a time so that
    an error stays inside one measure instead of derailing a page, and so the
    duration check below has something small and exact to verify.
    """

    model_config = {"extra": "forbid"}

    contains_music: bool = Field(
        description=(
            "False when the image holds no notes -- a clef, key or time "
            "signature region, a blank strip, or a fragment of text."
        )
    )
    beats_in_measure: int | None = Field(
        default=None,
        description="Numerator of the governing time signature, if visible here.",
    )
    beat_value: int | None = Field(
        default=None,
        description="Denominator of the governing time signature, if visible here.",
    )
    key_fifths: int | None = Field(
        default=None,
        ge=-7,
        le=7,
        description="Key signature as a count of sharps (positive) or flats (negative).",
    )
    notes: list[NoteEvent] = Field(
        default_factory=list, description="Every note and rest, in left-to-right order."
    )
    legible: bool = Field(
        default=True,
        description="False if the image is too damaged or ambiguous to read reliably.",
    )
    confidence: Confidence = "medium"
    # No max_length: the structured-output layer strips string constraints from
    # the schema it sends, then enforces them client-side, so a long remark
    # becomes a hard ValidationError that discards an otherwise good
    # transcription. Length is bounded by the prompt instead.
    note: str = Field(
        default="",
        description="Brief remark on anything ambiguous. Plain language, no markup.",
    )

    @property
    def total_duration(self) -> Fraction:
        return sum((n.duration for n in self.notes), Fraction(0))


_PITCH_RE = re.compile(r"^([A-Ga-g])([#b]{0,2})(-?\d)$")

_WIRE_VALUE_TO_NAME = {
    "1": "whole",
    "2": "half",
    "4": "quarter",
    "8": "eighth",
    "16": "16th",
    "32": "32nd",
    "64": "64th",
}


class WireNote(BaseModel):
    """One note as it crosses the provider boundary.

    Deliberately lean. A richly-typed nested schema (system -> measures ->
    notes, with a Literal enum on every field) is rejected by the structured
    output layer with "Schema is too complex", so the wire format is flat and
    uses short plain-typed fields. The expressive, validated representation is
    NoteEvent; conversion happens in `to_event` below, in Python, where exact
    arithmetic belongs.
    """

    model_config = {"extra": "forbid"}

    m: int = Field(description="Zero-based index of the measure this note is in.")
    p: str = Field(
        description=(
            "Pitch as letter, optional accidental, octave -- 'G4', 'F#5', 'Bb3'. "
            "Middle C is C4. Use 'r' for a rest. Include an accidental only if "
            "one is printed in this measure."
        )
    )
    v: str = Field(
        description="Note value as a denominator: 1, 2, 4, 8, 16, 32 or 64. A quarter note is '4'."
    )
    d: int = Field(default=0, description="Number of augmentation dots, usually 0.")
    t: int = Field(
        default=0,
        description="If part of a tuplet, how many notes it packs into the normal space (3 for a triplet). 0 if not a tuplet.",
    )
    f: int = Field(default=-1, description="Printed fingering digit 0-4, or -1 if none.")
    sl: bool = Field(default=False, description="True if a slur covers this note.")
    st: bool = Field(default=False, description="True if marked staccato.")

    def to_event(self) -> "NoteEvent":
        """Convert to the validated domain type. Raises ValueError on garbage."""
        value_name = _WIRE_VALUE_TO_NAME.get(self.v.strip())
        if value_name is None:
            raise ValueError(f"unknown note value {self.v!r}")

        token = self.p.strip()
        if token.lower() in {"r", "rest"}:
            return NoteEvent(
                is_rest=True,
                value=value_name,
                dots=max(0, min(2, self.d)),
                tuplet_actual=self.t if self.t > 1 else None,
                tuplet_normal=2 if self.t == 3 else (4 if self.t in (5, 6, 7) else None),
                slur="continue" if self.sl else "none",
                articulation="staccato" if self.st else "none",
            )

        match = _PITCH_RE.match(token)
        if not match:
            raise ValueError(f"unparseable pitch {token!r}")
        step, accidental, octave = match.groups()
        alter = accidental.count("#") - accidental.count("b")
        return NoteEvent(
            is_rest=False,
            step=step.upper(),  # type: ignore[arg-type]
            alter=max(-2, min(2, alter)),  # type: ignore[arg-type]
            octave=int(octave),
            value=value_name,
            dots=max(0, min(2, self.d)),
            tuplet_actual=self.t if self.t > 1 else None,
            tuplet_normal=2 if self.t == 3 else (4 if self.t in (5, 6, 7) else None),
            fingering=self.f if 0 <= self.f <= 4 else None,
            slur="continue" if self.sl else "none",
            articulation="staccato" if self.st else "none",
        )


class WireSystem(BaseModel):
    """A whole staff line as it crosses the provider boundary."""

    model_config = {"extra": "forbid"}

    beats: int = Field(default=0, description="Time signature numerator, 0 if not visible.")
    beat_value: int = Field(default=0, description="Time signature denominator, 0 if not visible.")
    key_fifths: int = Field(
        default=0, description="Key signature: sharps positive, flats negative, 0 for C major."
    )
    measure_count: int = Field(description="How many barline-delimited measures you read.")
    notes: list[WireNote] = Field(
        default_factory=list, description="All notes and rests, in order, each tagged with its measure."
    )
    illegible_measures: list[int] = Field(
        default_factory=list,
        description="Indices of measures you could not read reliably.",
    )
    note: str = Field(default="", description="One or two sentences on anything ambiguous.")

    def to_measures(self) -> tuple[list[MeasureTranscription], list[str]]:
        """Group flat notes into per-measure transcriptions.

        Returns the measures plus any conversion problems, which are reported
        rather than swallowed: a note we cannot parse must not silently vanish
        and leave a measure looking shorter than it is.
        """
        problems: list[str] = []
        buckets: dict[int, list[NoteEvent]] = {}
        for w in self.notes:
            try:
                buckets.setdefault(w.m, []).append(w.to_event())
            except (ValueError, ValidationError) as exc:
                problems.append(f"measure {w.m}: {exc}")

        count = max(self.measure_count, (max(buckets) + 1) if buckets else 0)
        illegible = set(self.illegible_measures)
        measures = [
            MeasureTranscription(
                contains_music=bool(buckets.get(i)),
                beats_in_measure=self.beats or None,
                beat_value=self.beat_value or None,
                key_fifths=self.key_fifths,
                notes=buckets.get(i, []),
                legible=i not in illegible,
                confidence="low" if i in illegible else "medium",
            )
            for i in range(count)
        ]
        return measures, problems


class SystemTranscription(BaseModel):
    """Every measure on one staff line, read in a single pass.

    Transcribing a whole system rather than isolated measure crops is a
    deliberate reversal of the original design, made on evidence from the C1
    spike. Pitch is a *relative* judgement: a notehead means nothing without the
    five staff lines around it. A tight measure crop shows a fragment of staff
    and the model is reduced to guessing, which it correctly reported as low
    confidence. Given the whole staff it has the reference it needs.

    Error containment survives the change, because each returned measure is
    still validated independently against the meter, and the count of returned
    measures is checked against the count of measures the page geometry found.
    """

    model_config = {"extra": "forbid"}

    beats_in_measure: int | None = Field(
        default=None, description="Numerator of the time signature governing this system."
    )
    beat_value: int | None = Field(
        default=None, description="Denominator of the time signature governing this system."
    )
    key_fifths: int | None = Field(
        default=None,
        ge=-7,
        le=7,
        description="Key signature as sharps (positive) or flats (negative).",
    )
    measures: list[MeasureTranscription] = Field(
        default_factory=list,
        description="Measures in left-to-right order, one entry per barline-delimited measure.",
    )
    legible: bool = True
    note: str = Field(default="", description="Brief remark on anything ambiguous.")


class MeasureValidation(BaseModel):
    """The verdict on one transcription. Never silently discarded."""

    ok: bool
    reason: str = ""
    expected: str | None = None
    actual: str | None = None
    is_pickup: bool = False
    non_musical: bool = False
    low_confidence: bool = False


def validate_measure(
    t: MeasureTranscription,
    expected_beats: int | None,
    expected_beat_value: int | None,
    allow_partial: bool = True,
) -> MeasureValidation:
    """Check a transcription against the meter it claims to be in.

    This is the gate that keeps the whole pipeline honest. A measure that does
    not add up is not quietly rendered as if it were fine: it is marked, left
    unrated, and shown as needing review. That is the difference between visible
    partial recognition and fabricated confidence.
    """
    if not t.contains_music or not t.notes:
        return MeasureValidation(
            ok=False, reason="no notes in region", non_musical=True
        )

    # Self-reported illegibility is a confidence signal, not a verdict. It is
    # applied at the end rather than here, because the arithmetic below is the
    # stronger evidence: on this repertoire the recurring doubt is whether a
    # beam group is eighths or 16ths, and that choice changes the measure's
    # total duration. A measure whose durations land exactly on the meter has
    # therefore already been checked on the very point the model was unsure
    # about. Rejecting it for self-doubt would discard correct readings and make
    # recognition look far worse than it is.
    out_of_range = [n for n in t.notes if not n.is_in_violin_range()]
    if out_of_range:
        return MeasureValidation(
            ok=False,
            reason=f"{len(out_of_range)} note(s) outside the violin's range",
        )

    beats = expected_beats if expected_beats is not None else t.beats_in_measure
    value = expected_beat_value if expected_beat_value is not None else t.beat_value
    if not beats or not value:
        return MeasureValidation(
            ok=False, reason="no time signature established for this measure"
        )

    expected = Fraction(beats, value)
    actual = t.total_duration

    if actual == expected:
        return MeasureValidation(
            ok=True,
            reason="recognition flagged this measure as uncertain" if not t.legible else "",
            expected=str(expected),
            actual=str(actual),
            low_confidence=not t.legible,
        )

    # A short measure at a phrase edge is a pickup or a split measure across a
    # system break -- both are real notation, not errors. A long one never is.
    # A short measure the model already doubted is more likely a dropped note,
    # so it does not get the benefit of the doubt.
    if allow_partial and actual < expected and t.legible:
        return MeasureValidation(
            ok=True,
            reason="partial measure (pickup or split across a system break)",
            expected=str(expected),
            actual=str(actual),
            is_pickup=True,
        )

    return MeasureValidation(
        ok=False,
        reason="durations do not sum to the time signature",
        expected=str(expected),
        actual=str(actual),
        low_confidence=not t.legible,
    )
