"""Turn an AnalysisBundle into exactly what the page needs to render.

Every number the browser uses is computed here, in Python, and arrives as a
percentage. The browser does no coordinate arithmetic at all. That is a
deliberate division: normalized coordinates multiplied by 100 are the same
overlay at any container width, so zooming or resizing cannot desynchronize an
annotation from its measure -- there is no transform to recompute and therefore
none to get wrong.

Two rules in here are worth stating out loud because they are product decisions,
not implementation details.

**Ribbon continuity, and what a band of colour means.** Within a system the
ribbon is one unbroken run. Segment boundaries are taken from where the next
segment starts, not from where the current one's box ends, so adjoining segments
are flush by construction -- there is no rounding gap to hairline through.
Widths still follow the real engraved measure widths; nothing is distributed
equally.

What changed in C17 is what a band *is*. It used to be one measure, which made
the ribbon a sixty-one-slice heatmap of the rubric's own rounding. A band is now
one practice section, drawn once per staff system it touches, in that section's
single colour. The only thing that interrupts a section's band is a measure
recognition could not read: that keeps its neutral hatching, because unknown
material must never be handed a difficulty colour.

**Measure ownership.** A click selects a *section*. Sections tile the piece, so
every measure belongs to exactly one and clicking anywhere inside one selects
the same passage and loads the same guidance. The phrase that owns a measure's
first note is still recorded and still reachable, and so is any trouble spot
covering it -- both are secondary detail inside the selected section rather than
things a click on the score resolves to.
"""

from __future__ import annotations

import dataclasses

from src.features.difficulty.colors import (
    UNRATED_COLOR,
    UNRATED_LABEL,
    category_for,
    color_for,
    format_score,
    legend,
)
from src.features.difficulty.rubric import (
    DEFAULT_TEMPO_BPM,
    WEIGHTS,
    aggregate_phrase,
    plain_reason,
    rubric_explanation,
)
from src.schemas.analysis import AnalysisBundle
from src.schemas.geometry import Region
from src.schemas.score import Difficulty, Measure, Phrase, Score, System

# Fallback placement, used only when the analysis measured no band for a system:
# the bottom of the system box, inset slightly.
#
# This used to be the only placement, on the reasoning that the box's lowest
# sliver is the whitespace between systems. That reasoning was wrong and the
# ribbon covered notation on every system of the fixture page -- stems, beams,
# fingering digits and the treble clef's descender reach three to four staff
# spaces below the bottom line, while the box reaches only halfway to the next
# staff. `cv_geometry.ribbon_band` now measures the actual gutter and
# `System.ribbon_region` carries it, so these constants apply only where no ink
# was available to measure.
RIBBON_HEIGHT_FRAC = 0.13
RIBBON_INSET_FRAC = 0.02

# How many rating factors a hover card shows. Enough to explain, short enough to
# read in passing; the sidebar shows the rest.
HOVER_FACTOR_LIMIT = 3


def _pct(value: float) -> str:
    """Percentages at four decimals: sub-pixel on any realistic page width."""
    return f"{value * 100:.4f}%"


def _box_style(region: Region) -> str:
    return (
        f"left:{_pct(region.x)};top:{_pct(region.y)};"
        f"width:{_pct(region.w)};height:{_pct(region.h)}"
    )


@dataclasses.dataclass(frozen=True)
class FactorView:
    label: str
    # The same demand in a player's words. What the sidebar leads with; `label`
    # and the numbers below it move into the rubric disclosure.
    plain: str
    contribution: str
    detail: str
    # The weight this contribution was drawn from. "+0.8" alone is a number with
    # no scale; "+0.8 of a possible 3.4" is something a reader can argue with.
    weight: str
    share: str


@dataclasses.dataclass(frozen=True)
class MeasureView:
    id: str
    label: str
    ordinal: int
    system_id: str
    phrase_id: str | None
    section_id: str | None
    spot_id: str | None
    style: str
    score_text: str
    category: str
    color: str
    is_rated: bool
    quality: str
    quality_note: str
    starts_phrase: bool
    ends_phrase: bool
    factors: list[FactorView]
    aria_label: str


@dataclasses.dataclass(frozen=True)
class RibbonSegment:
    """One band of colour: a practice section, or a hole recognition left in one.

    `section_id` is what makes the fragments of a section that fall on different
    staff systems the same object to the reader and to selection -- same
    identity, same rating, same colour.
    """

    section_id: str | None
    measure_id: str
    # Every measure this band covers, so "the ribbon accounts for all the music"
    # stays checkable now that a band is a passage rather than a measure.
    measure_ids: list[str]
    label: str
    style: str
    color: str
    is_rated: bool
    score_text: str
    category: str
    aria_label: str


@dataclasses.dataclass(frozen=True)
class SystemView:
    id: str
    index: int
    style: str
    measures: list[MeasureView]
    segments: list[RibbonSegment]
    has_ribbon: bool
    # Whether the band this system's ribbon occupies was measured clear of ink.
    # The interface decides what to do about "crowded"; this only reports it.
    ribbon_placement: str = "unmeasured"


@dataclasses.dataclass(frozen=True)
class PhraseView:
    id: str
    label: str
    level: str
    parent_id: str | None
    user_edited: bool
    score_text: str
    category: str
    color: str
    is_rated: bool
    peak_text: str
    peak_measure_label: str
    range_text: str
    practice_text: str
    start_reason: str
    start_confidence: str
    end_reason: str
    end_confidence: str
    region_styles: list[str]
    fragment_count: int
    measure_ids: list[str]
    factors: list[FactorView]
    unrated_reason: str
    # Populated for sections only: what is inside this passage, in order. The
    # sidebar shows them as secondary detail under the section's own guidance.
    child_phrase_ids: list[str] = dataclasses.field(default_factory=list)
    child_spot_ids: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class PageView:
    id: str
    index: int
    image_url: str
    width_px: int
    height_px: int
    aspect_ratio: str
    systems: list[SystemView]


@dataclasses.dataclass(frozen=True)
class ScoreView:
    score_id: str
    title: str
    is_example: bool
    pages: list[PageView]
    phrases: list[PhraseView]
    trouble_spots: list[PhraseView]
    sections: list[PhraseView]
    legend: list[dict]
    assumptions: list[str]
    warnings: list[str]
    quality_counts: dict[str, int]
    measure_total: int
    rated_total: int
    unrated_label: str
    unrated_color: str
    # What is selected when the page opens. A section, because a section is what
    # a click selects and what the sidebar is written for.
    default_selection_id: str | None
    rubric: dict


def _anchor_key(score: Score, measure_id: str, note_index: int) -> tuple[int, int]:
    measure = score.measure(measure_id)
    return (measure.ordinal if measure else -1, note_index)


def owning_phrase(score: Score, phrases: list[Phrase], measure: Measure) -> Phrase | None:
    """The phrase that owns a measure's first note.

    Structural ranges tile the analyzable music with no overlap, so at most one
    phrase matches. A measure that recognition could not read belongs to no
    phrase and correctly returns None -- it is shown as needing review, not
    quietly attached to a neighbour.
    """
    target = (measure.ordinal, 0)
    for phrase in phrases:
        start = _anchor_key(score, phrase.structural_start.measure_id, phrase.structural_start.note_index)
        end = _anchor_key(score, phrase.structural_end.measure_id, phrase.structural_end.note_index)
        if start <= target <= end:
            return phrase
    return None


def owning_section(score: Score, sections: list[Phrase], measure: Measure) -> Phrase | None:
    """The practice section a measure belongs to.

    Sections tile the piece with no gaps and no overlaps, so exactly one matches
    -- including for a measure nobody could read, which is grouped with the
    other unreadable measures around it rather than left homeless. That is the
    property that lets a click anywhere on the score land on a passage.
    """
    for section in sections:
        if measure.id in section.measure_ids:
            return section
    return None


def _factors(difficulty: Difficulty | None, limit: int | None = None) -> list[FactorView]:
    if difficulty is None:
        return []
    ordered = sorted(difficulty.factors, key=lambda f: f.contribution, reverse=True)
    if limit is not None:
        ordered = ordered[:limit]
    return [
        FactorView(
            label=f.label,
            plain=plain_reason(f.key),
            contribution=f"+{f.contribution:.1f}",
            detail=f.detail,
            weight=f"{WEIGHTS.get(f.key, 0.0):.1f}",
            share=(
                f"{f.contribution / WEIGHTS[f.key] * 100:.0f}%"
                if WEIGHTS.get(f.key)
                else ""
            ),
        )
        for f in ordered
    ]


_QUALITY_TEXT = {
    "confident": "read and checked against the meter",
    "uncertain": "read, but flagged for review",
    "unreadable": "could not be read reliably",
    "non_musical": "no notes here",
    "not_attempted": "never read — the recognition request did not complete",
}


def _measure_aria(measure: Measure, difficulty: Difficulty | None) -> str:
    score = difficulty.score if difficulty else None
    if score is None:
        return f"Measure {measure.label}: {UNRATED_LABEL} — {_QUALITY_TEXT.get(measure.quality, measure.quality)}"
    return f"Measure {measure.label}: {format_score(score)} out of 10, {category_for(score)}"


def ribbon_band_rows(system: System) -> tuple[float, float]:
    """(top, height) for one system's ribbon, as page fractions.

    Prefers the band the analysis measured from the page's ink. Falls back to the
    bottom of the system box only when nothing was measured, which is an engraved
    page served as SVG rather than a scan.
    """
    if system.ribbon_region is not None:
        return system.ribbon_region.y, system.ribbon_region.h
    region = system.region
    return (
        region.y + region.h * (1.0 - RIBBON_INSET_FRAC - RIBBON_HEIGHT_FRAC),
        region.h * RIBBON_HEIGHT_FRAC,
    )


def _ribbon_segments(
    system_region: Region,
    measures: list[Measure],
    ratings: dict[str, Difficulty],
    section_by_measure: dict[str, str],
    section_ratings: dict[str, Difficulty],
    section_labels: dict[str, str],
    band: tuple[float, float],
) -> list[RibbonSegment]:
    """One flush run of colour across a system, banded by practice section.

    Consecutive measures belonging to the same section become one band in that
    section's single colour, so a section reads as one passage rather than as a
    row of slightly different slices of the same idea. The band is cut in exactly
    one situation: a measure recognition could not read keeps its own neutral
    hatched band, because handing unknown material a difficulty colour would
    present it as easy or hard when it is neither.

    A band starts where its own first measure starts and ends where the *next*
    band's first measure starts, so neighbouring bands share an edge exactly and
    no rounding gap can open between them. The run is stretched to the system's
    own extent at both ends, which absorbs the half-barline difference between a
    system box and its outer measures. Widths still follow the real engraved
    measure widths; nothing is distributed equally.
    """
    if not measures:
        return []

    ordered = sorted(measures, key=lambda m: m.region.x)
    top, height = band

    # Group into runs. The key carries readability as well as identity so a hole
    # inside a section splits the band without merging into the next section.
    runs: list[list[Measure]] = []
    previous_key = None
    for measure in ordered:
        difficulty = ratings.get(measure.id)
        key = (
            section_by_measure.get(measure.id),
            (difficulty.score if difficulty else None) is not None,
        )
        if runs and key == previous_key:
            runs[-1].append(measure)
        else:
            runs.append([measure])
        previous_key = key

    segments: list[RibbonSegment] = []
    for index, run in enumerate(runs):
        first, last = run[0], run[-1]
        left = system_region.x if index == 0 else first.region.x
        if index + 1 < len(runs):
            right = runs[index + 1][0].region.x
        else:
            right = max(system_region.right, last.region.right)
        width = max(0.0, right - left)

        section_id = section_by_measure.get(first.id)
        measure_rating = ratings.get(first.id)
        measure_rated = (measure_rating.score if measure_rating else None) is not None

        if not measure_rated:
            # A hole recognition left. It keeps the neutral hatching whatever
            # the passage around it rates.
            score = None
        elif section_id and section_id in section_ratings:
            # The band shows the section's rating, not the measure's. One
            # section, one number, one colour, everywhere it appears.
            score = section_ratings[section_id].score
        else:
            # No section rating to read -- a bundle that was never retuned, or
            # music outside any section. Aggregate what this band actually
            # covers rather than borrowing one measure's number for all of it.
            score, _ = aggregate_phrase(
                [(ratings[m.id].score if m.id in ratings else None) for m in run]
            )

        label = (
            f"measures {first.label}\u2013{last.label}"
            if first.id != last.id
            else f"measure {first.label}"
        )
        if score is not None:
            aria = (
                f"{section_labels.get(section_id, label)}: {format_score(score)} out of 10, "
                f"{category_for(score)}"
            )
        else:
            aria = f"{label.capitalize()}: {UNRATED_LABEL} \u2014 {_QUALITY_TEXT.get(first.quality, first.quality)}"

        segments.append(
            RibbonSegment(
                section_id=section_id,
                measure_id=first.id,
                measure_ids=[m.id for m in run],
                label=label,
                style=f"left:{_pct(left)};top:{_pct(top)};width:{_pct(width)};height:{_pct(height)}",
                color=color_for(score),
                is_rated=score is not None,
                score_text=format_score(score),
                category=category_for(score),
                aria_label=aria,
            )
        )
    return segments


def _range_text(score: Score, phrase: Phrase) -> str:
    first = score.measure(phrase.structural_start.measure_id)
    last = score.measure(phrase.structural_end.measure_id)
    if first is None or last is None:
        return "range unavailable"
    if first.id == last.id:
        return f"measure {first.label}"
    return f"measures {first.label}–{last.label}"


def _practice_text(score: Score, phrase: Phrase) -> str:
    """What to actually play, which is not always what the phrase is."""
    if not phrase.has_practice_overlap:
        return "Play to the end of the phrase; there is no following note to carry into."
    last = score.measure(phrase.practice_end.measure_id)
    if last is None:
        return "Play through the first note of the next phrase."
    return (
        f"Play through the first note of measure {last.label}, "
        "so the join into the next idea is rehearsed too."
    )


def _confidence_text(confidence: float) -> str:
    if confidence >= 0.66:
        return f"strong evidence ({confidence:.2f})"
    if confidence >= 0.33:
        return f"moderate evidence ({confidence:.2f})"
    return f"weak evidence ({confidence:.2f})"


def build_view(bundle: AnalysisBundle, supplied_tempo: float | None = None) -> ScoreView:
    score = bundle.score
    phrases = [p for p in bundle.phrases if p.level == "phrase"]
    spots = [p for p in bundle.phrases if p.level == "trouble_spot"]
    sections = [p for p in bundle.phrases if p.level == "section"]
    owner_by_measure: dict[str, str] = {}
    for measure in score.measures:
        owner = owning_phrase(score, phrases, measure)
        if owner is not None:
            owner_by_measure[measure.id] = owner.id

    # A click resolves to a section, so this is the map that matters most.
    section_by_measure: dict[str, str] = {
        mid: section.id for section in sections for mid in section.measure_ids
    }
    section_labels = {section.id: section.label for section in sections}
    section_ratings = {
        section.id: bundle.phrase_rating(section.id)
        for section in sections
        if bundle.phrase_rating(section.id) is not None
    }
    spot_by_measure: dict[str, str] = {
        mid: spot.id for spot in spots for mid in spot.measure_ids
    }

    boundary_starts = {p.structural_start.measure_id for p in phrases}
    boundary_ends = {p.structural_end.measure_id for p in phrases}

    measures_by_id = {m.id: m for m in score.measures}
    pages: list[PageView] = []
    for page in sorted(score.pages, key=lambda p: p.index):
        systems: list[SystemView] = []
        page_systems = [s for s in score.systems if s.page_index == page.index]
        for system in sorted(page_systems, key=lambda s: s.index):
            members = [measures_by_id[i] for i in system.measure_ids if i in measures_by_id]
            members.sort(key=lambda m: m.region.x)

            measure_views = []
            for measure in members:
                difficulty = bundle.measure_rating(measure.id)
                rating = difficulty.score if difficulty else None
                measure_views.append(
                    MeasureView(
                        id=measure.id,
                        label=measure.label,
                        ordinal=measure.ordinal,
                        system_id=system.id,
                        phrase_id=owner_by_measure.get(measure.id),
                        section_id=section_by_measure.get(measure.id),
                        spot_id=spot_by_measure.get(measure.id),
                        style=_box_style(measure.region),
                        score_text=format_score(rating),
                        category=category_for(rating),
                        color=color_for(rating),
                        is_rated=rating is not None,
                        quality=measure.quality,
                        quality_note=measure.quality_note
                        or _QUALITY_TEXT.get(measure.quality, ""),
                        starts_phrase=measure.id in boundary_starts,
                        ends_phrase=measure.id in boundary_ends,
                        factors=_factors(difficulty, HOVER_FACTOR_LIMIT),
                        aria_label=_measure_aria(measure, difficulty),
                    )
                )

            systems.append(
                SystemView(
                    id=system.id,
                    index=system.index,
                    style=_box_style(system.region),
                    measures=measure_views,
                    segments=_ribbon_segments(
                        system.region,
                        members,
                        bundle.measure_difficulty,
                        section_by_measure,
                        section_ratings,  # type: ignore[arg-type]
                        section_labels,
                        ribbon_band_rows(system),
                    ),
                    has_ribbon=bool(members),
                    ribbon_placement=system.ribbon_placement,
                )
            )

        pages.append(
            PageView(
                id=page.id,
                index=page.index,
                image_url=page.image_url,
                width_px=page.width_px,
                height_px=page.height_px,
                aspect_ratio=f"{page.width_px} / {page.height_px}",
                systems=systems,
            )
        )

    def view_for(phrase: Phrase) -> PhraseView:
        difficulty = bundle.phrase_rating(phrase.id)
        rating = difficulty.score if difficulty else None
        peak = difficulty.peak if difficulty else None
        peak_measure = (
            measures_by_id.get(difficulty.peak_target_id)
            if difficulty and difficulty.peak_target_id
            else None
        )
        # A phrase rating explains itself through its hardest measure. The
        # phrase-level record carries no factors of its own by design: the
        # demands are local, and averaging them into a phrase-wide list would
        # blur exactly the obstacle a player needs to find.
        peak_factors = _factors(
            bundle.measure_rating(difficulty.peak_target_id)
            if difficulty and difficulty.peak_target_id
            else None
        )

        unrated_reason = ""
        if rating is None:
            noun = {"section": "passage", "trouble_spot": "spot"}.get(phrase.level, "phrase")
            unreadable = [
                m
                for m in (measures_by_id.get(i) for i in phrase.measure_ids)
                if m is not None and not m.is_analyzable
            ]
            unrated_reason = (
                f"{len(unreadable)} of {len(phrase.measure_ids)} measures here could not be "
                f"read, so this {noun} is left unrated rather than given a number it has "
                "not earned. Unknown is not the same as easy."
                if unreadable
                else f"No measure in this {noun} could be rated."
            )

        return PhraseView(
                id=phrase.id,
                label=phrase.label,
                level=phrase.level,
                parent_id=phrase.parent_id,
                user_edited=phrase.user_edited,
                score_text=format_score(rating),
                category=category_for(rating),
                color=color_for(rating),
                is_rated=rating is not None,
                peak_text=format_score(peak),
                peak_measure_label=peak_measure.label if peak_measure else "",
                range_text=_range_text(score, phrase),
                practice_text=_practice_text(score, phrase),
                start_reason=phrase.start_boundary.reason,
                start_confidence=_confidence_text(phrase.start_boundary.confidence),
                end_reason=phrase.end_boundary.reason,
                end_confidence=_confidence_text(phrase.end_boundary.confidence),
                region_styles=[_box_style(r) for r in phrase.regions],
                fragment_count=len(phrase.regions),
                measure_ids=list(phrase.measure_ids),
                factors=peak_factors,
                unrated_reason=unrated_reason,
            )

    phrase_views = [view_for(p) for p in phrases]
    # A trouble spot whose parent vanished is dropped rather than orphaned: the
    # sidebar nests them, and a nested row with nothing to nest under is a bug
    # the reader would have to interpret.
    known = {p.id for p in phrases}
    spot_views = [view_for(s) for s in spots if s.parent_id in known]

    phrases_by_section: dict[str, list[str]] = {}
    for phrase in phrases:
        if phrase.parent_id:
            phrases_by_section.setdefault(phrase.parent_id, []).append(phrase.id)
    spots_by_section: dict[str, list[str]] = {}
    for spot in spot_views:
        parent = next((p for p in phrases if p.id == spot.parent_id), None)
        if parent is not None and parent.parent_id:
            spots_by_section.setdefault(parent.parent_id, []).append(spot.id)

    section_views = [
        dataclasses.replace(
            view_for(section),
            child_phrase_ids=phrases_by_section.get(section.id, []),
            child_spot_ids=spots_by_section.get(section.id, []),
        )
        for section in sections
    ]

    quality_counts: dict[str, int] = {}
    for measure in score.measures:
        quality_counts[measure.quality] = quality_counts.get(measure.quality, 0) + 1

    rated_total = sum(
        1 for d in bundle.measure_difficulty.values() if d.score is not None
    )

    # The tempo the ratings on screen were actually computed from, read off the
    # measures rather than guessed. `supplied_tempo` is a separate fact from
    # `tempo_is_assumed`: the latter means "the page prints no tempo", which
    # stays true even after the user supplies one, and conflating them would
    # report a user's own 160 BPM back to them as an assumption.
    analyzable = [m for m in score.measures if m.is_analyzable]
    rating_tempo = supplied_tempo or next(
        (m.tempo_bpm for m in analyzable if m.tempo_bpm), DEFAULT_TEMPO_BPM
    )
    tempo_is_assumed = supplied_tempo is None

    return ScoreView(
        score_id=score.id,
        title=score.title or "Untitled score",
        is_example=score.is_example,
        pages=pages,
        phrases=phrase_views,
        trouble_spots=spot_views,
        sections=section_views,
        legend=legend(),
        assumptions=list(score.assumptions),
        warnings=list(score.warnings),
        quality_counts=quality_counts,
        measure_total=len(score.measures),
        rated_total=rated_total,
        unrated_label=UNRATED_LABEL,
        unrated_color=UNRATED_COLOR,
        rubric=rubric_explanation(rating_tempo, tempo_is_assumed),
        default_selection_id=(
            section_views[0].id
            if section_views
            else (phrase_views[0].id if phrase_views else None)
        ),
    )


def _factor_payload(factors: list[FactorView]) -> list[dict]:
    return [
        {
            "label": f.label,
            "plain": f.plain,
            "contribution": f.contribution,
            "detail": f.detail,
            "weight": f.weight,
            "share": f.share,
        }
        for f in factors
    ]


def client_payload(view: ScoreView) -> dict:
    """Everything the sidebar and hover card display, already formatted.

    Geometry is in the DOM as percentages and stays there; this carries the
    text. Nothing here is computed in the browser -- the one-decimal rendering,
    the category boundaries and the unrated wording are decided once, in Python,
    where they are tested.
    """
    measures = [m for page in view.pages for system in page.systems for m in system.measures]
    # Phrases and trouble spots share one map: selection, the sidebar and the
    # practice lookup treat them identically, and `level` is what distinguishes
    # them where it matters.
    selectable = list(view.sections) + list(view.phrases) + list(view.trouble_spots)
    # Which trouble spot, if any, covers each measure. Selection resolves to the
    # most specific thing that owns a measure: clicking the measure a hard spot
    # is marked on should select the hard spot, not the whole phrase around it.
    spot_by_measure = {
        mid: spot.id for spot in view.trouble_spots for mid in spot.measure_ids
    }
    return {
        "scoreId": view.score_id,
        "rubric": view.rubric,
        "defaultSelectionId": view.default_selection_id,
        "unratedLabel": view.unrated_label,
        "measures": {
            m.id: {
                "label": m.label,
                "sectionId": m.section_id,
                "phraseId": m.phrase_id,
                "spotId": spot_by_measure.get(m.id),
                "scoreText": m.score_text,
                "category": m.category,
                "color": m.color,
                "isRated": m.is_rated,
                "quality": m.quality,
                "qualityNote": m.quality_note,
                "factors": _factor_payload(m.factors),
                "ariaLabel": m.aria_label,
            }
            for m in measures
        },
        "measureOrder": [m.id for m in sorted(measures, key=lambda m: m.ordinal)],
        "measureLabels": {m.id: m.label for m in measures},
        "phrases": {
            p.id: {
                "id": p.id,
                "label": p.label,
                "level": p.level,
                "parentId": p.parent_id,
                "userEdited": p.user_edited,
                "scoreText": p.score_text,
                "category": p.category,
                "color": p.color,
                "isRated": p.is_rated,
                "peakText": p.peak_text,
                "peakMeasureLabel": p.peak_measure_label,
                "rangeText": p.range_text,
                "practiceText": p.practice_text,
                "startReason": p.start_reason,
                "startConfidence": p.start_confidence,
                "endReason": p.end_reason,
                "endConfidence": p.end_confidence,
                "factors": _factor_payload(p.factors),
                "unratedReason": p.unrated_reason,
                "measureIds": p.measure_ids,
                "fragmentCount": p.fragment_count,
                "childPhraseIds": p.child_phrase_ids,
                "childSpotIds": p.child_spot_ids,
            }
            for p in selectable
        },
    }
