"""Phrase segmentation: one musical idea per group.

The interpretation this implements, stated plainly because the spec asks for it
to be explicit: a top-level group is one musical idea. Measure count is a
heuristic, not the definition. A genuine two-measure phrase is valid; slicing
the piece into uniform two-measure blocks is not.

Boundaries are chosen here, in code, by scoring evidence. A language model may
later describe a phrase in prose, but it does not decide where phrases begin,
and it does not invent formal labels like "exposition" that the notation does
not support.

Evidence, strongest first:

    meter or key change, double bar  structural, and also a phrase boundary
    a rest                           strong: a breath is the clearest boundary
    a long note                      moderate: agogic weight closes a gesture
    end of a slur                    moderate: a bowing unit often ends an idea
    descent to a stable scale degree moderate: cadential shape
    a barline                        weak, and explicitly not sufficient alone

A barline scores low on purpose. The spec is emphatic that an ordinary bar line
does not establish a phrase; counting bars is the failure mode this design is
built to avoid.

Etude caveat: perpetual-motion writing often has no rests and no cadences for
many measures. Where evidence is genuinely thin, the boundary is still placed
(the piece must be covered) but its confidence is reported low rather than
dressed up. That honesty is the point -- a musician reviewing the output can see
which boundaries are inferred and which are merely spaced.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from src.schemas.music import NoteEvent
from src.schemas.score import BoundaryEvidence, Measure, PhraseBoundary

# Target phrase length in measures. A soft preference, not a rule: strong
# evidence overrides it in both directions.
IDEAL_MEASURES = 4
MIN_MEASURES = 2
MAX_MEASURES = 8

WEIGHT = {
    "meter_change": 1.00,
    "key_change": 1.00,
    "double_bar": 1.00,
    "rest": 0.62,
    "long_note": 0.42,
    "slur_end": 0.34,
    "cadential_contour": 0.40,
    "barline": 0.12,
}

# Scale degrees that feel like arrival, as semitone offsets from the tonic.
_STABLE_DEGREES = {0, 7}


@dataclass
class Candidate:
    """A possible boundary after `measure_index`, with why."""

    measure_index: int
    score: float
    evidence: list[BoundaryEvidence]
    reason: str


def _tonic_pc(key_fifths: int | None) -> int:
    """Tonic pitch class implied by a key signature, assuming major."""
    return (7 * (key_fifths or 0)) % 12


def score_boundary_after(
    measure: Measure,
    notes: list[NoteEvent],
    next_measure: Measure | None,
    next_notes: list[NoteEvent],
) -> Candidate:
    """Weigh the evidence for a phrase ending at the end of `measure`."""
    evidence: list[BoundaryEvidence] = []
    total = 0.0
    reasons: list[str] = []

    # A barline is present by construction. It counts, but barely.
    evidence.append("barline")
    total += WEIGHT["barline"]

    if next_measure is not None:
        if (
            measure.beats is not None
            and next_measure.beats is not None
            and (measure.beats, measure.beat_value) != (next_measure.beats, next_measure.beat_value)
        ):
            evidence.append("meter_change")
            total += WEIGHT["meter_change"]
            reasons.append("the time signature changes here")
        if (
            measure.key_fifths is not None
            and next_measure.key_fifths is not None
            and measure.key_fifths != next_measure.key_fifths
        ):
            evidence.append("key_change")
            total += WEIGHT["key_change"]
            reasons.append("the key signature changes here")

    if notes:
        trailing_rest = notes[-1].is_rest
        if trailing_rest:
            evidence.append("rest")
            total += WEIGHT["rest"]
            reasons.append("the phrase ends on a rest")

        last = notes[-1]
        typical = min((n.duration for n in notes), default=Fraction(1, 8))
        if not last.is_rest and typical and last.duration >= typical * 3:
            evidence.append("long_note")
            total += WEIGHT["long_note"]
            reasons.append("it closes on a note noticeably longer than the surrounding movement")

        if last.slur in ("stop", "continue") and next_notes and next_notes[0].slur != "continue":
            evidence.append("slur_end")
            total += WEIGHT["slur_end"]
            reasons.append("a slur ends here")

        sounded = [n for n in notes if not n.is_rest and n.midi is not None]
        if len(sounded) >= 3:
            tonic = _tonic_pc(measure.key_fifths)
            final_pc = (sounded[-1].midi - tonic) % 12  # type: ignore[operator]
            descending = sounded[-1].midi < sounded[-3].midi  # type: ignore[operator]
            if final_pc in _STABLE_DEGREES and descending:
                evidence.append("cadential_contour")
                total += WEIGHT["cadential_contour"]
                degree = "tonic" if final_pc == 0 else "dominant"
                reasons.append(f"the line settles downward onto the {degree}")

    if not reasons:
        reason = "placed to keep phrases a workable length; the notation gives little evidence here"
    else:
        reason = "; ".join(reasons).capitalize()
    return Candidate(measure.ordinal, total, evidence, reason)


def choose_boundaries(candidates: list[Candidate], total_measures: int) -> list[int]:
    """Pick boundary positions greedily, respecting length bounds.

    Walks forward from the current phrase start and takes the best-scoring
    candidate inside the allowed window. Strong evidence early in the window
    wins over a merely-adequate position later, which is what lets a genuine
    two-measure phrase survive instead of being padded to four.
    """
    if total_measures <= MIN_MEASURES:
        return []

    by_index = {c.measure_index: c for c in candidates}
    boundaries: list[int] = []
    start = 0

    while start < total_measures:
        if total_measures - start <= MAX_MEASURES:
            break
        window = range(start + MIN_MEASURES - 1, min(start + MAX_MEASURES, total_measures) - 1)
        best_index, best_value = None, -1.0
        for idx in window:
            cand = by_index.get(idx)
            if cand is None:
                continue
            length = idx - start + 1
            # Prefer evidence, but keep a mild pull toward the ideal length so
            # that in evidence-free stretches phrases stay a usable size.
            shape = 1.0 - min(1.0, abs(length - IDEAL_MEASURES) / (MAX_MEASURES)) * 0.35
            value = cand.score * shape
            if value > best_value:
                best_index, best_value = idx, value
        if best_index is None:
            break
        boundaries.append(best_index)
        start = best_index + 1

    return boundaries


def boundary_from_candidate(cand: Candidate | None, fallback: str) -> PhraseBoundary:
    """Turn a candidate into the reported boundary, with honest confidence."""
    if cand is None:
        return PhraseBoundary(evidence=[], reason=fallback, confidence=0.5)
    # Map accumulated evidence weight onto 0-1. A lone barline lands near 0.1,
    # which is exactly the impression it should give.
    confidence = max(0.05, min(0.98, cand.score / 1.4))
    return PhraseBoundary(
        evidence=cand.evidence, reason=cand.reason, confidence=round(confidence, 2)
    )
