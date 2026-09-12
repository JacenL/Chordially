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


# --------------------------------------------------------------------------
# Trouble spots: the third level, inside a phrase
# --------------------------------------------------------------------------

# How far above its phrase's mean a measure must sit to count as a local
# obstacle rather than part of a uniformly demanding phrase. Shared with the
# practice coach so one number governs both what is marked and what is taught.
LOCAL_PEAK_MARGIN = 0.8

# A phrase needs an inside before something can be inside it. With two measures
# there is no "local" -- the peak is simply half the phrase.
MIN_PHRASE_MEASURES_FOR_SPOT = 3

# A trouble spot is a short technical range, per the spec. Two measures is the
# ceiling; beyond that it is the phrase that is hard, not a spot within it.
MAX_SPOT_MEASURES = 2


def find_trouble_spots(
    score,
    phrases: list,
    measure_ratings: dict,
) -> list:
    """One trouble spot per phrase that genuinely has a local obstacle.

    Not every phrase gets one, and that is the point. Marking a spot inside a
    phrase whose measures are all equally demanding would be noise: it would
    tell a player to isolate a passage that is not, locally, the problem.

    Ratings drive this rather than notation features, deliberately. The question
    "is this measure harder than its neighbours" is exactly what the rating
    answers, and a spot must move when the tempo changes -- which it does,
    because these are re-derived whenever ratings are.
    """
    from src.schemas.score import Anchor, Phrase, PhraseBoundary
    from src.server.analysis.assemble import region_fragments

    by_id = {m.id: m for m in score.measures}
    spots: list = []

    for phrase in phrases:
        if phrase.level != "phrase":
            continue

        members = [by_id[mid] for mid in phrase.measure_ids if mid in by_id]
        rated = [
            (m, measure_ratings[m.id].score)
            for m in members
            if m.id in measure_ratings and measure_ratings[m.id].score is not None
        ]
        if len(rated) < MIN_PHRASE_MEASURES_FOR_SPOT:
            continue

        mean = sum(score_value for _, score_value in rated) / len(rated)
        over = [m for m, value in rated if value - mean >= LOCAL_PEAK_MARGIN]
        if not over:
            continue

        # Adjacent measures over the threshold belong to one spot; the rule is
        # a short range, so take the strongest run and cap its length.
        over_ordinals = {m.ordinal for m in over}
        runs: list[list] = []
        for measure in sorted(over, key=lambda m: m.ordinal):
            if runs and measure.ordinal - runs[-1][-1].ordinal == 1:
                runs[-1].append(measure)
            else:
                runs.append([measure])

        def strength(run: list) -> float:
            return max(measure_ratings[m.id].score or 0.0 for m in run)

        best = max(runs, key=strength)[:MAX_SPOT_MEASURES]
        del over_ordinals

        first, last = best[0], best[-1]
        reason = (
            f"rated {strength(best):.1f} against {mean:.1f} across the phrase"
        )
        spots.append(
            Phrase(
                id=f"{phrase.id}:ts0",
                label=f"Hard spot in {phrase.label}",
                level="trouble_spot",
                parent_id=phrase.id,
                structural_start=Anchor(measure_id=first.id, note_index=0),
                structural_end=Anchor(
                    measure_id=last.id, note_index=max(0, len(last.note_ids) - 1)
                ),
                practice_start=Anchor(measure_id=first.id, note_index=0),
                practice_end=Anchor(
                    measure_id=last.id, note_index=max(0, len(last.note_ids) - 1)
                ),
                has_practice_overlap=False,
                regions=region_fragments(best),
                start_boundary=PhraseBoundary(
                    evidence=[], reason=reason, confidence=0.5
                ),
                end_boundary=PhraseBoundary(
                    evidence=[], reason=reason, confidence=0.5
                ),
                measure_ids=[m.id for m in best],
            )
        )
    return spots


# --------------------------------------------------------------------------
# Structural sections: the level above a phrase
# --------------------------------------------------------------------------

# Accidental counts, spelled rather than named. A key signature of one sharp is
# G major or E minor and the notation alone does not say which, so the label
# reports what is printed and lets the reader draw the conclusion. The spec is
# explicit that formal labels must not be invented, and "G major" is already an
# inference this evidence does not support.
def _key_text(fifths: int | None) -> str:
    if fifths is None:
        return "key not established"
    if fifths == 0:
        return "no sharps or flats"
    count = abs(fifths)
    return f"{count} {'sharp' if fifths > 0 else 'flat'}{'' if count == 1 else 's'}"


def _signature(measure: Measure) -> tuple | None:
    parts = (measure.beats, measure.beat_value, measure.key_fifths)
    return parts if all(p is not None for p in parts) else None


def find_sections(score, phrases: list) -> list:
    """Structural sections, from printed evidence only.

    The spec names what may establish one: a key change, a meter change, a
    double bar, a repeat. Only the first two are legible from what recognition
    currently records, so only those are used.

    **A page showing no such evidence gets no sections at all.** Wrapping the
    whole piece in a single span called "Section 1" would be a formal claim the
    notation does not support, and docs/product-spec.md forbids inventing one.
    The Mozart fixture, one meter and one key throughout, correctly yields none.

    Sections never split a phrase. A signature change lands on a measure, and
    the section boundary snaps to the start of the phrase owning that measure,
    so the three levels nest rather than cut across each other.
    """
    from src.schemas.score import Anchor, Phrase, PhraseBoundary
    from src.server.analysis.assemble import region_fragments

    ordered = [m for m in score.measures_in_order()]
    if not ordered or not phrases:
        return []

    # Where the printed signature actually changes.
    change_ordinals: list[int] = []
    previous = None
    for measure in ordered:
        current = _signature(measure)
        if current is None:
            continue
        if previous is not None and current != previous:
            change_ordinals.append(measure.ordinal)
        previous = current

    if not change_ordinals:
        return []

    by_id = {m.id: m for m in score.measures}
    phrase_starts = sorted(
        (min(by_id[mid].ordinal for mid in p.measure_ids if mid in by_id), p)
        for p in phrases
        if p.level == "phrase" and p.measure_ids
    )
    if not phrase_starts:
        return []

    # Snap each change to the phrase that owns it, so sections nest.
    starts = {phrase_starts[0][0]}
    for ordinal in change_ordinals:
        owning = max((s for s, _ in phrase_starts if s <= ordinal), default=None)
        if owning is not None:
            starts.add(owning)
    boundaries = sorted(starts)
    if len(boundaries) < 2:
        return []

    sections: list = []
    for index, start in enumerate(boundaries):
        end = (
            boundaries[index + 1] - 1 if index + 1 < len(boundaries) else ordered[-1].ordinal
        )
        members = [m for m in ordered if start <= m.ordinal <= end]
        if not members:
            continue

        signature = next((_signature(m) for m in members if _signature(m)), None)
        descriptor = (
            f"{signature[0]}/{signature[1]}, {_key_text(signature[2])}"
            if signature
            else "signature not established"
        )
        label = f"Measures {members[0].label}–{members[-1].label}"
        reason = (
            "the piece begins here"
            if index == 0
            else f"the printed key or time signature changes to {descriptor}"
        )

        section = Phrase(
            id=f"{score.id}:sec{index:02d}",
            label=label,
            level="section",
            structural_start=Anchor(measure_id=members[0].id, note_index=0),
            structural_end=Anchor(
                measure_id=members[-1].id,
                note_index=max(0, len(members[-1].note_ids) - 1),
            ),
            practice_start=Anchor(measure_id=members[0].id, note_index=0),
            practice_end=Anchor(
                measure_id=members[-1].id,
                note_index=max(0, len(members[-1].note_ids) - 1),
            ),
            has_practice_overlap=False,
            regions=region_fragments(members),
            start_boundary=PhraseBoundary(
                evidence=["piece_start"] if index == 0 else ["key_change", "meter_change"],
                reason=reason,
                confidence=0.5 if index == 0 else 0.95,
            ),
            end_boundary=PhraseBoundary(
                evidence=[], reason=descriptor, confidence=0.95
            ),
            measure_ids=[m.id for m in members],
        )
        sections.append(section)

        # Phrases point up at the section containing them, making the chain
        # section <- phrase <- trouble spot.
        for phrase_start, phrase in phrase_starts:
            if start <= phrase_start <= end:
                phrase.parent_id = section.id

    return sections
