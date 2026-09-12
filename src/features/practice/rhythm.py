"""Complementary rhythm variation, computed exactly and refused when unsafe.

The transformation is the one described in S01 and spelled out in
docs/music-pedagogy.md: take a run of equal notes and alternately lengthen and
shorten consecutive pairs, then reverse the pattern. The point is that each pair
still occupies exactly the time it occupies on the page, so the beat does not
move and the exercise can be played against the rest of the phrase.

Two rules keep this from becoming a blind pairwise rewrite, which the pedagogy
document explicitly forbids:

* Every refusal is by name. Ties, rests, tuplets, mixed values, an unreadable
  measure or a value too short to halve all mean "not this technique here",
  never "transform it anyway and hope".
* Duration is arithmetic on Fractions, never floats, and the total is asserted
  unchanged. A variation that quietly stole a 64th from the bar would push
  everything after it off the beat.
"""

from __future__ import annotations

import dataclasses
from fractions import Fraction

from src.schemas.music import NOTE_VALUE_FRACTIONS, NoteEvent

# Ordered small-to-large so "the next value down" is a lookup, not arithmetic on
# strings. A note whose half has no printed name cannot be transformed.
VALUE_ORDER = ["64th", "32nd", "16th", "eighth", "quarter", "half", "whole"]

# A run shorter than this is not a run; pairing two notes teaches nothing about
# a line. Four is the smallest group that contains two different pair boundaries.
MIN_RUN = 4

ACCIDENTAL_GLYPH = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "x"}


@dataclasses.dataclass(frozen=True)
class VariantNote:
    """One note of a practice variant. Display only; never written to a score."""

    pitch: str
    value: str
    dots: int
    duration: Fraction
    role: str  # "long", "short", or "unchanged"

    @property
    def duration_text(self) -> str:
        name = self.value if self.dots == 0 else f"dotted {self.value}"
        return name


@dataclasses.dataclass(frozen=True)
class Variant:
    name: str
    description: str
    notes: list[VariantNote]

    @property
    def total(self) -> Fraction:
        return sum((n.duration for n in self.notes), Fraction(0))


class NotTransformable(ValueError):
    """Why this passage does not get a rhythm variation."""


def pitch_label(note: NoteEvent) -> str:
    if note.is_rest:
        return "rest"
    step = note.step or "?"
    return f"{step}{ACCIDENTAL_GLYPH.get(note.alter, '')}{note.octave if note.octave is not None else ''}"


def check_run(notes: list[NoteEvent]) -> None:
    """Raise NotTransformable with a reason a musician would accept."""
    if len(notes) < MIN_RUN:
        raise NotTransformable(
            f"a rhythm variation needs a run of at least {MIN_RUN} equal notes; "
            f"this passage has {len(notes)}"
        )
    if any(n.is_rest for n in notes):
        raise NotTransformable("this run contains rests, which the pairing would move")
    if any(n.tie != "none" for n in notes):
        raise NotTransformable(
            "this run contains tied notes, whose written durations cannot be "
            "reassigned pairwise"
        )
    if any(n.tuplet_actual for n in notes):
        raise NotTransformable(
            "this run contains tuplets; lengthening one note of a triplet changes "
            "what the triplet means"
        )
    if any(n.is_chord for n in notes):
        raise NotTransformable(
            "this run contains double stops, whose two voices a pairwise rhythm "
            "would have to redistribute together"
        )
    durations = {n.duration for n in notes}
    if len(durations) > 1:
        raise NotTransformable(
            "this run mixes note values, so there are no equal pairs to exchange"
        )
    value = notes[0].value
    if notes[0].dots:
        raise NotTransformable("this run is already dotted")
    if value not in VALUE_ORDER or VALUE_ORDER.index(value) == 0:
        raise NotTransformable(
            f"a {value} note has no shorter printed value to borrow from"
        )


def _halved(value: str) -> str:
    return VALUE_ORDER[VALUE_ORDER.index(value) - 1]


def _variant(notes: list[NoteEvent], *, long_first: bool, offset: int, name: str, description: str) -> Variant:
    """Pair notes from `offset` and alternate long and short within each pair.

    Notes before the offset, and a final unpaired note, keep their written
    value. That is what makes "start the pattern one note later" a different
    exercise rather than the same one shifted: a different pair of notes is
    joined by the long-short boundary.
    """
    out: list[VariantNote] = []
    i = 0
    while i < len(notes):
        note = notes[i]
        in_pair = i >= offset and (i - offset) % 2 == 0 and i + 1 < len(notes)
        if not in_pair:
            out.append(
                VariantNote(
                    pitch=pitch_label(note),
                    value=note.value,
                    dots=0,
                    duration=note.duration,
                    role="unchanged",
                )
            )
            i += 1
            continue

        partner = notes[i + 1]
        long_dur = note.duration * Fraction(3, 2)
        short_dur = note.duration * Fraction(1, 2)
        short_value = _halved(note.value)

        first = VariantNote(
            pitch=pitch_label(note),
            value=note.value if long_first else short_value,
            dots=1 if long_first else 0,
            duration=long_dur if long_first else short_dur,
            role="long" if long_first else "short",
        )
        second = VariantNote(
            pitch=pitch_label(partner),
            value=short_value if long_first else partner.value,
            dots=0 if long_first else 1,
            duration=short_dur if long_first else long_dur,
            role="short" if long_first else "long",
        )
        out.extend([first, second])
        i += 2

    variant = Variant(name=name, description=description, notes=out)

    # The invariant the whole technique rests on. A pair is redistributed, never
    # resized, so the run still occupies exactly its written time.
    written = sum((n.duration for n in notes), Fraction(0))
    if variant.total != written:
        raise NotTransformable(
            f"internal error: variant totals {variant.total} against a written "
            f"{written}; refusing to show a rhythm that would shift the beat"
        )
    return variant


def variants(notes: list[NoteEvent]) -> list[Variant]:
    """The complementary pair, plus the displaced start S01 describes."""
    check_run(notes)
    out = [
        _variant(
            notes,
            long_first=True,
            offset=0,
            name="Long–short",
            description="Hold the first note of each pair, hurry the second.",
        ),
        _variant(
            notes,
            long_first=False,
            offset=0,
            name="Short–long",
            description="The complement: every transition that was easy one way is exposed the other.",
        ),
    ]
    if len(notes) >= MIN_RUN + 1:
        out.append(
            _variant(
                notes,
                long_first=True,
                offset=1,
                name="Long–short, starting one note later",
                description="The same pattern displaced, so a different pair of notes is joined.",
            )
        )
    return out


def longest_even_run(notes: list[NoteEvent]) -> tuple[int, int]:
    """Start index and length of the longest transformable run, or (0, 0).

    Scanned rather than assumed: a phrase is rarely uniform, and the run that
    deserves the exercise is the one actually printed, not the whole phrase.
    """
    best_start, best_len = 0, 0
    start = 0
    while start < len(notes):
        if (
            notes[start].is_rest
            or notes[start].tuplet_actual
            or notes[start].dots
            or notes[start].is_chord
        ):
            start += 1
            continue
        end = start + 1
        while (
            end < len(notes)
            and not notes[end].is_rest
            and not notes[end].tuplet_actual
            and not notes[end].dots
            and not notes[end].is_chord
            and notes[end].duration == notes[start].duration
            and notes[end - 1].tie == "none"
            and notes[end].tie == "none"
        ):
            end += 1
        if end - start > best_len:
            best_start, best_len = start, end - start
        start = max(end, start + 1)
    return best_start, best_len


def _fraction_ok(value: str) -> bool:
    return value in NOTE_VALUE_FRACTIONS
