"""Choose techniques for one selected passage and ground them in its notation.

The product requirement this file exists to satisfy is that advice is about the
passage the user clicked, not about violin playing in general. So:

* Triggers are evaluated against features read from that phrase's own notes --
  the longest run of equal values actually printed in it, whether its measures
  mix note values, where its hardest measure is. A rating alone never selects a
  technique, because a number cannot tell you what kind of hard a passage is.
* Nothing is offered to every passage. A technique whose triggers do not fire is
  absent, and when nothing fires the sidebar says the notation does not support
  a specific recommendation rather than falling back to "practise it slowly".
* Every exercise names the measures it applies to, and those measure IDs are
  checked against the score before they are rendered.
"""

from __future__ import annotations

import dataclasses
from fractions import Fraction

from src.features.practice import rhythm
from src.features.practice.library import Library, Source, Technique, load_library
from src.schemas.analysis import AnalysisBundle
from src.schemas.music import NoteEvent
from src.schemas.score import Phrase

# A measure this much above the phrase mean is a local obstacle worth isolating
# rather than a phrase that is simply hard throughout.
LOCAL_PEAK_MARGIN = 0.8

# Rubric factor strength above which a demand is worth naming to the player.
FACTOR_TRIGGER = 0.30


class PassageNotFound(LookupError):
    """The requested phrase does not belong to this score."""


@dataclasses.dataclass(frozen=True)
class ExerciseView:
    technique_id: str
    title: str
    fits: str
    evidence_category: str
    steps: list[str]
    listening_goals: list[str]
    tempo_rule: str
    success_criteria: str
    return_to_context: str
    cautions: list[str]
    sources: list[dict]
    applies_to: str
    trigger_reason: str
    variants: list[dict] = dataclasses.field(default_factory=list)
    variant_note: str = ""


@dataclasses.dataclass(frozen=True)
class Guidance:
    phrase_id: str
    phrase_label: str
    range_text: str
    note_range_text: str
    challenge: str
    observations: list[str]
    primary: ExerciseView | None
    alternatives: list[ExerciseView]
    no_fit_reason: str = ""


def _phrase_notes(bundle: AnalysisBundle, phrase: Phrase) -> list[NoteEvent]:
    """Notes of the phrase's structural range, in playing order."""
    score = bundle.score
    by_id = {n.id: n for n in score.notes}
    start_ord = score.measure(phrase.structural_start.measure_id)
    end_ord = score.measure(phrase.structural_end.measure_id)
    if start_ord is None or end_ord is None:
        return []

    events: list[NoteEvent] = []
    for measure in score.measures_in_order():
        if measure.ordinal < start_ord.ordinal or measure.ordinal > end_ord.ordinal:
            continue
        if not measure.is_analyzable:
            # An unreadable measure interrupts the run rather than being skipped
            # over: pretending the notes on either side are adjacent would
            # invent a continuity the page does not have.
            events.append(NoteEvent(is_rest=True, value="quarter"))
            continue
        ids = measure.note_ids
        if measure.ordinal == start_ord.ordinal:
            ids = ids[phrase.structural_start.note_index :]
        if measure.ordinal == end_ord.ordinal:
            keep = phrase.structural_end.note_index + 1
            offset = phrase.structural_start.note_index if measure.ordinal == start_ord.ordinal else 0
            ids = ids[: max(0, keep - offset)]
        events.extend(by_id[i].event for i in ids if i in by_id)
    return events


def _factor_strength(bundle: AnalysisBundle, measure_id: str | None, key: str) -> float:
    if not measure_id:
        return 0.0
    difficulty = bundle.measure_rating(measure_id)
    if difficulty is None:
        return 0.0
    for factor in difficulty.factors:
        if factor.key == key:
            return factor.contribution
    return 0.0


def _features(bundle: AnalysisBundle, phrase: Phrase) -> dict[str, float]:
    """What this phrase actually contains, as trigger strengths."""
    notes = _phrase_notes(bundle, phrase)
    sounded = [n for n in notes if not n.is_rest]
    difficulty = bundle.phrase_rating(phrase.id)
    peak_id = difficulty.peak_target_id if difficulty else None

    run_start, run_len = rhythm.longest_even_run(notes)
    durations = {n.duration for n in sounded}

    rated = [
        d.score
        for mid in phrase.measure_ids
        if (d := bundle.measure_rating(mid)) is not None and d.score is not None
    ]
    mean = sum(rated) / len(rated) if rated else 0.0
    peak = difficulty.peak if difficulty and difficulty.peak is not None else 0.0

    return {
        "even_run": float(run_len) if run_len >= rhythm.MIN_RUN else 0.0,
        "even_run_start": float(run_start),
        "mixed_values": 1.0 if len(durations) > 1 else 0.0,
        "syncopation": _factor_strength(bundle, peak_id, "syncopation"),
        "dense": _factor_strength(bundle, peak_id, "note_rate"),
        "accidentals": _factor_strength(bundle, peak_id, "chromatic"),
        "wide_intervals": _factor_strength(bundle, peak_id, "leaps"),
        "local_peak": max(0.0, peak - mean),
        "has_next_phrase": 1.0 if phrase.has_practice_overlap else 0.0,
    }


def _fires(technique: Technique, features: dict[str, float]) -> tuple[bool, str]:
    """Whether this technique applies here, and the observation that says so."""
    reasons: list[str] = []
    for trigger in technique.triggerFeatures:
        value = features.get(trigger, 0.0)
        if trigger == "even_run" and value >= rhythm.MIN_RUN:
            reasons.append(f"a run of {int(value)} equal notes is printed here")
        elif trigger == "mixed_values" and value > 0:
            reasons.append("this passage mixes note values")
        elif trigger == "local_peak" and value >= LOCAL_PEAK_MARGIN:
            reasons.append("one measure is clearly harder than the rest of the phrase")
        elif trigger == "has_next_phrase" and value > 0:
            reasons.append("a following phrase exists to carry into")
        elif trigger in ("syncopation", "dense", "accidentals", "wide_intervals") and value >= FACTOR_TRIGGER:
            reasons.append(
                {
                    "syncopation": "notes land off the beat",
                    "dense": "the note rate is high for the assumed tempo",
                    "accidentals": "printed accidentals take the line outside the key",
                    "wide_intervals": "the line moves by wide intervals",
                }[trigger]
            )
    return bool(reasons), "; ".join(reasons)


def _measure_span(bundle: AnalysisBundle, phrase: Phrase) -> str:
    first = bundle.score.measure(phrase.structural_start.measure_id)
    last = bundle.score.measure(phrase.structural_end.measure_id)
    if first is None or last is None:
        return "this passage"
    if first.id == last.id:
        return f"measure {first.label}"
    return f"measures {first.label}–{last.label}"


def _source_payload(sources: list[Source]) -> list[dict]:
    return [
        {
            "id": s.id,
            "title": s.title,
            "author": s.author,
            "publication": s.publication,
            "url": s.url,
            "evidenceCategory": s.evidenceCategory,
            "supports": s.supports,
            "doesNotSupport": s.doesNotSupport,
        }
        for s in sources
    ]


def _rhythm_payload(bundle: AnalysisBundle, phrase: Phrase, features: dict) -> tuple[list[dict], str]:
    """Concrete variants built from this phrase's own notes, or a stated refusal."""
    notes = _phrase_notes(bundle, phrase)
    start = int(features.get("even_run_start", 0))
    length = int(features.get("even_run", 0))
    if length < rhythm.MIN_RUN:
        return [], "No run of equal notes long enough to pair."

    # Keep the exercise short enough to be an exercise: a group, not the phrase.
    run = notes[start : start + min(length, 8)]
    try:
        built = rhythm.variants(run)
    except rhythm.NotTransformable as exc:
        return [], f"Not applied here: {exc}."

    written_total = sum((n.duration for n in run), Fraction(0))
    payload = [
        {
            "name": v.name,
            "description": v.description,
            "notes": [
                {
                    "pitch": n.pitch,
                    "duration": n.duration_text,
                    "role": n.role,
                }
                for n in v.notes
            ],
        }
        for v in built
    ]
    note = (
        f"{len(run)} notes, starting at note {start + 1} of the phrase. "
        f"Each variant lasts exactly as long as the written run "
        f"({written_total} of a whole note), so the beat does not move."
    )
    return payload, note


def build_guidance(bundle: AnalysisBundle, phrase_id: str) -> Guidance:
    """Practice instruction for one phrase of one score."""
    phrase = bundle.phrase(phrase_id)
    if phrase is None:
        raise PassageNotFound(
            f"phrase {phrase_id} is not part of score {bundle.score.id}"
        )

    library: Library = load_library()
    features = _features(bundle, phrase)
    difficulty = bundle.phrase_rating(phrase.id)
    peak_measure = (
        bundle.score.measure(difficulty.peak_target_id)
        if difficulty and difficulty.peak_target_id
        else None
    )

    observations: list[str] = []
    peak_difficulty = bundle.measure_rating(difficulty.peak_target_id) if difficulty and difficulty.peak_target_id else None
    if peak_difficulty:
        for factor in sorted(peak_difficulty.factors, key=lambda f: f.contribution, reverse=True)[:3]:
            observations.append(f"{factor.label} (+{factor.contribution:.1f})")

    if peak_measure and difficulty and difficulty.peak is not None:
        challenge = (
            f"The hardest point is measure {peak_measure.label}, rated "
            f"{difficulty.peak:.1f}. "
        )
    else:
        challenge = ""
    challenge += (
        "What the notation shows: " + ", ".join(observations).lower()
        if observations
        else "The notation here does not show a single dominant demand."
    )

    candidates: list[tuple[float, ExerciseView]] = []
    for technique in library.techniques.values():
        fired, reason = _fires(technique, features)
        if not fired:
            continue

        variants_payload: list[dict] = []
        variant_note = ""
        if technique.id == "rhythm-pairs":
            variants_payload, variant_note = _rhythm_payload(bundle, phrase, features)
            if not variants_payload:
                # The trigger fired but the notation refused the transformation.
                # Dropping the technique is correct; showing steps for an
                # exercise that cannot be built would be worse than silence.
                continue

        view = ExerciseView(
            technique_id=technique.id,
            title=technique.title,
            fits=technique.fits,
            evidence_category=technique.evidenceCategory,
            steps=list(technique.steps),
            listening_goals=list(technique.listeningGoals),
            tempo_rule=technique.tempoRule,
            success_criteria=technique.successCriteria,
            return_to_context=technique.returnToContext,
            cautions=list(technique.cautions),
            sources=_source_payload(library.source_list(technique.sourceIds)),
            applies_to=_measure_span(bundle, phrase),
            trigger_reason=reason,
            variants=variants_payload,
            variant_note=variant_note,
        )
        # Rank by how specifically the passage called for it: a rhythm variation
        # built from printed notes outranks generic advice, and an isolated hard
        # measure outranks a whole-phrase observation.
        weight = {
            "rhythm-pairs": 4.0 + features["even_run"] / 10.0,
            "transition-loop": 3.0 + features["local_peak"],
            "subdivision": 2.0 + features["syncopation"],
            "slow-with-goal": 1.0 + features["dense"],
            "reconnect-overlap": 0.5,
        }.get(technique.id, 0.0)
        candidates.append((weight, view))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    primary = candidates[0][1] if candidates else None
    alternatives = [view for _, view in candidates[1:3]]

    first = bundle.score.measure(phrase.structural_start.measure_id)
    last = bundle.score.measure(phrase.structural_end.measure_id)
    note_range = (
        f"note {phrase.structural_start.note_index + 1} of measure "
        f"{first.label if first else '?'} to note "
        f"{phrase.structural_end.note_index + 1} of measure {last.label if last else '?'}"
    )

    return Guidance(
        phrase_id=phrase.id,
        phrase_label=phrase.label,
        range_text=_measure_span(bundle, phrase),
        note_range_text=note_range,
        challenge=challenge,
        observations=observations,
        primary=primary,
        alternatives=alternatives,
        no_fit_reason=(
            ""
            if primary
            else "The notation read here does not support a specific technique. "
            "Rather than recommending something generic, PracticeMap is saying so."
        ),
    )
