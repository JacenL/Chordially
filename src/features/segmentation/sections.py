"""Practice sections: the unit a player actually selects and works on.

A section is a run of adjacent phrases that ask for the same kind of work. It is
the primary thing the score is coloured by and the primary thing a click
selects, and its rating and colour are single values that hold across its whole
extent -- including the fragments of it that fall on different staff systems.

**Why this level exists at all.** Colouring measure by measure produced a
heatmap: on the fixture page, sixty-one separately coloured slivers whose
boundaries fell wherever a rating happened to tick by a tenth. That is a
picture of the rubric's noise, not of the music. A player does not practise a
measure because it is 0.2 harder than its neighbour; they practise a passage
that asks something particular of them. So the visual unit is now the passage.

**What starts a new section.** In order of authority:

    a printed key or time signature change   structural, and never overridden
    readable music starting or stopping      unknown is not a difficulty
    a step in difficulty                     more than SECTION_RATING_TOLERANCE
    a change in what is being demanded       the dominant demand changes
    a user's own split                       always wins

**What does not.** A tenth of a point. A barline. A phrase ending. Similar
scores alone are also not enough to merge across any of the boundaries above --
two unrelated ideas that happen to rate 2.4 stay apart if the demand behind the
number is different or the signature changed between them.

**Sections never split a phrase**, and phrases never span two sections. A
boundary lands on a phrase start or it does not land. That is what makes the
three levels (section, phrase, trouble spot) nest rather than cut across each
other.

**This supersedes the C15 rule** that a page with no printed signature change
gets no sections at all. That rule was protecting against a real thing -- the
spec forbids inventing formal labels like "exposition" that the notation does
not support -- and the protection is kept: a section is labelled by the measures
it spans and by the demands measured inside it, never by a formal name. But a
practice grouping is not a formal claim, and refusing to group meant refusing to
give the page a primary unit at all.
"""

from __future__ import annotations

import dataclasses

from src.features.difficulty.rubric import WEIGHTS, aggregate_phrase, plain_reason
from src.schemas.score import Anchor, Difficulty, Measure, Phrase, PhraseBoundary

# How far a phrase's rating may sit from the running mean of the section it
# would join. Wide enough that a tenth of a point never splits anything; narrow
# enough that the step from a beginner etude to a sixteenth-note study does.
SECTION_RATING_TOLERANCE = 0.8

# A ceiling on the spread inside one section, so a slow drift cannot carry a
# section from one end of a category to the other while every single step stays
# inside the tolerance above.
SECTION_SPREAD_LIMIT = 1.5

# Normalized share of its own weight at which a feature counts as something the
# passage is actually demanding, rather than a trace.
DEMAND_FLOOR = 0.25


@dataclasses.dataclass(frozen=True)
class PhraseProfile:
    """What one phrase asks for, reduced to what a grouping decision needs."""

    phrase: Phrase
    first_ordinal: int
    rating: float | None
    dominant: str | None
    demands: frozenset[str]

    @property
    def is_rated(self) -> bool:
        return self.rating is not None


def _profile(
    phrase: Phrase,
    measures_by_id: dict[str, Measure],
    ratings: dict[str, Difficulty],
) -> PhraseProfile:
    """Rating and demand signature for one phrase, from its own measures."""
    member_scores = [
        ratings[mid].score for mid in phrase.measure_ids if mid in ratings
    ]
    rating, _ = aggregate_phrase(member_scores)

    # Mean share of each feature's own weight, across the measures that have a
    # rating. Shares rather than raw points, so a 3.2-weight feature and a
    # 1.0-weight one are compared on the same footing.
    totals: dict[str, float] = {}
    counted = 0
    for mid in phrase.measure_ids:
        difficulty = ratings.get(mid)
        if difficulty is None or difficulty.score is None:
            continue
        counted += 1
        for factor in difficulty.factors:
            weight = WEIGHTS.get(factor.key)
            if weight:
                totals[factor.key] = totals.get(factor.key, 0.0) + factor.contribution / weight
    shares = {k: v / counted for k, v in totals.items()} if counted else {}

    demands = frozenset(k for k, v in shares.items() if v >= DEMAND_FLOOR)
    dominant = max(shares, key=lambda k: shares[k]) if shares else None
    if dominant is not None and shares[dominant] < DEMAND_FLOOR:
        dominant = None

    first = min(
        (measures_by_id[mid].ordinal for mid in phrase.measure_ids if mid in measures_by_id),
        default=0,
    )
    return PhraseProfile(
        phrase=phrase,
        first_ordinal=first,
        rating=rating,
        dominant=dominant,
        demands=demands,
    )


def _signature(measure: Measure) -> tuple | None:
    parts = (measure.beats, measure.beat_value, measure.key_fifths)
    return parts if all(p is not None for p in parts) else None


def _key_text(fifths: int | None) -> str:
    """Accidental counts, spelled rather than named.

    A key signature of one sharp is G major or E minor and the notation alone
    does not say which, so the label reports what is printed and lets the reader
    draw the conclusion. The spec is explicit that formal labels must not be
    invented, and "G major" is already an inference this evidence does not
    support.
    """
    if fifths is None:
        return "key not established"
    if fifths == 0:
        return "no sharps or flats"
    count = abs(fifths)
    return f"{count} {'sharp' if fifths > 0 else 'flat'}{'' if count == 1 else 's'}"


def signature_change_ordinals(score) -> list[int]:
    """Measure ordinals where the printed key or time signature actually changes."""
    changes: list[int] = []
    previous = None
    for measure in score.measures_in_order():
        current = _signature(measure)
        if current is None:
            continue
        if previous is not None and current != previous:
            changes.append(measure.ordinal)
        previous = current
    return changes


# Plain-language names for the demands a boundary reason can cite. Kept separate
# from the rubric's own LABELS because a boundary sentence reads as prose, not
# as a table row.
_DEMAND_PHRASE = {
    "note_rate": "note rate",
    "subdivision": "fine subdivision",
    "syncopation": "displaced accents",
    "chromatic": "accidentals outside the key",
    "register": "playing above first position",
    "leaps": "wide leaps",
    "double_stops": "double stops",
    "bow_demand": "bow control",
    "rhythm_complexity": "rhythmic complexity",
}

NO_DOMINANT_TEXT = "nothing here is especially demanding"


def _demand_text(key: str | None) -> str:
    if key is None:
        return NO_DOMINANT_TEXT
    return _DEMAND_PHRASE.get(key, key.replace("_", " "))


def _boundary_reason(
    previous: list[PhraseProfile],
    candidate: PhraseProfile,
    structural: str | None,
) -> str:
    """One sentence saying why this section starts where it does."""
    if structural:
        return structural
    if not previous:
        return "the piece begins here"

    before = [p for p in previous if p.is_rated]
    if candidate.is_rated and not before:
        return "readable music resumes here, so this is where rating starts again"
    if not candidate.is_rated and before:
        return "recognition could not read this stretch, so it is kept separate"

    if candidate.is_rated and before:
        mean = sum(p.rating for p in before) / len(before)  # type: ignore[misc]
        if abs(candidate.rating - mean) > SECTION_RATING_TOLERANCE:  # type: ignore[operator]
            direction = "steps up" if candidate.rating > mean else "eases" # type: ignore[operator]
            return (
                f"the difficulty {direction} from about {mean:.1f} to "
                f"{candidate.rating:.1f}"
            )
        dominant_before = before[-1].dominant
        if dominant_before != candidate.dominant:
            if dominant_before is None:
                return f"the music starts asking for {_demand_text(candidate.dominant)}"
            if candidate.dominant is None:
                return f"the demand for {_demand_text(dominant_before)} stops here"
            return (
                f"what the music asks for changes from {_demand_text(dominant_before)} "
                f"to {_demand_text(candidate.dominant)}"
            )
    return "the technical demands change here"


def _needs_boundary(
    current: list[PhraseProfile], candidate: PhraseProfile, structural: bool
) -> bool:
    """Whether `candidate` starts a new section instead of joining `current`."""
    if structural:
        return True
    if not current:
        return False

    rated_now = [p for p in current if p.is_rated]
    # Unknown is not a difficulty. A stretch nobody could read must not be
    # absorbed into a rated section, where it would inherit that section's
    # colour and be presented as easy or hard when it is neither.
    if candidate.is_rated != bool(rated_now):
        return True
    if not candidate.is_rated:
        return False

    scores = [p.rating for p in rated_now]  # type: ignore[misc]
    mean = sum(scores) / len(scores)
    if abs(candidate.rating - mean) > SECTION_RATING_TOLERANCE:  # type: ignore[operator]
        return True
    widened = scores + [candidate.rating]
    if max(widened) - min(widened) > SECTION_SPREAD_LIMIT:  # type: ignore[type-var]
        return True

    # Similar scores are not a reason to merge unrelated material. If the
    # dominant demand has changed, the work the passage asks for has changed
    # even when the number has not.
    if rated_now[-1].dominant != candidate.dominant:
        return True
    return False


def find_sections(
    score,
    phrases: list[Phrase],
    measure_ratings: dict[str, Difficulty] | None = None,
    starts: set[str] | None = None,
    joins: set[str] | None = None,
) -> list[Phrase]:
    """Group phrases into practice sections covering the whole score.

    `starts` and `joins` are user edits, keyed by the measure id a section would
    begin at: a measure in `starts` must begin one, a measure in `joins` must
    not. They are applied after the derived boundaries so a user's judgement
    always wins over the heuristic, which is the point of offering the controls.
    """
    from src.server.analysis.assemble import region_fragments

    ratings = measure_ratings or {}
    measures_by_id = {m.id: m for m in score.measures}
    ordered_measures = score.measures_in_order()
    if not ordered_measures:
        return []

    profiles = sorted(
        (
            _profile(p, measures_by_id, ratings)
            for p in phrases
            if p.level == "phrase" and p.measure_ids
        ),
        key=lambda p: p.first_ordinal,
    )
    if not profiles:
        return []

    change_ordinals = set(signature_change_ordinals(score))
    forced_starts = starts or set()
    suppressed = joins or set()

    groups: list[list[PhraseProfile]] = [[profiles[0]]]
    reasons: list[str] = [
        "the piece begins here"
    ]
    structural_flags: list[bool] = [False]
    edited_flags: list[bool] = [False]

    for profile in profiles[1:]:
        first_measure_id = profile.phrase.measure_ids[0]
        span = {measures_by_id[mid].ordinal for mid in profile.phrase.measure_ids if mid in measures_by_id}
        structural = bool(span & change_ordinals)
        structural_text = None
        if structural:
            member = measures_by_id.get(first_measure_id)
            signature = _signature(member) if member else None
            descriptor = (
                f"{signature[0]}/{signature[1]}, {_key_text(signature[2])}"
                if signature
                else "a signature that is not established"
            )
            structural_text = f"the printed key or time signature changes to {descriptor}"

        forced = first_measure_id in forced_starts
        blocked = first_measure_id in suppressed and not forced

        if blocked:
            groups[-1].append(profile)
            continue

        if forced or _needs_boundary(groups[-1], profile, structural):
            reasons.append(
                "you split the section here"
                if forced and not structural
                else _boundary_reason(groups[-1], profile, structural_text)
            )
            structural_flags.append(structural)
            edited_flags.append(forced)
            groups.append([profile])
        else:
            groups[-1].append(profile)

    sections: list[Phrase] = []
    for index, group in enumerate(groups):
        members = [
            measures_by_id[mid]
            for profile in group
            for mid in profile.phrase.measure_ids
            if mid in measures_by_id
        ]
        if not members:
            continue
        members.sort(key=lambda m: m.ordinal)
        first, last = members[0], members[-1]

        label = (
            f"Measures {first.label}–{last.label}"
            if first.id != last.id
            else f"Measure {first.label}"
        )
        # Said the way a player would say it. `_DEMAND_PHRASE` names the feature
        # for a boundary sentence, where the noun reads better; this line is the
        # first thing someone sees about a passage, so it uses the rubric's
        # player-facing wording instead.
        demands = sorted({p.dominant for p in group if p.dominant})
        summary = (
            "what this asks for: "
            + " and ".join(plain_reason(d) for d in demands)
            if demands
            else NO_DOMINANT_TEXT
        )
        evidence = ["key_change", "meter_change"] if structural_flags[index] else []
        if index == 0:
            evidence = ["piece_start"]

        section = Phrase(
            id=f"{score.id}:sec{index:02d}",
            label=label,
            level="section",
            structural_start=Anchor(measure_id=first.id, note_index=0),
            structural_end=Anchor(
                measure_id=last.id, note_index=max(0, len(last.note_ids) - 1)
            ),
            practice_start=Anchor(measure_id=first.id, note_index=0),
            practice_end=Anchor(
                measure_id=last.id, note_index=max(0, len(last.note_ids) - 1)
            ),
            has_practice_overlap=False,
            regions=region_fragments(members),
            start_boundary=PhraseBoundary(
                evidence=evidence,  # type: ignore[arg-type]
                reason=reasons[index],
                confidence=0.95 if structural_flags[index] or index == 0 else 0.6,
            ),
            end_boundary=PhraseBoundary(evidence=[], reason=summary, confidence=0.6),
            measure_ids=[m.id for m in members],
            user_edited=edited_flags[index] or any(p.phrase.user_edited for p in group),
        )
        sections.append(section)

        for profile in group:
            profile.phrase.parent_id = section.id

    return sections
