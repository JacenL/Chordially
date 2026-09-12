"""Turn an AnalysisBundle into exactly what the page needs to render.

Every number the browser uses is computed here, in Python, and arrives as a
percentage. The browser does no coordinate arithmetic at all. That is a
deliberate division: normalized coordinates multiplied by 100 are the same
overlay at any container width, so zooming or resizing cannot desynchronize an
annotation from its measure -- there is no transform to recompute and therefore
none to get wrong.

Two rules in here are worth stating out loud because they are product decisions,
not implementation details.

**Ribbon continuity.** Within a system the ribbon is one unbroken run. Segment
boundaries are taken from where the next measure starts, not from where the
current measure's box ends, so adjoining segments are flush by construction --
there is no rounding gap to hairline through. Widths still follow the real
engraved measure widths; nothing is distributed equally.

**Measure ownership.** Structural phrase ranges tile the piece, and a boundary
may fall inside a measure, so one measure can show two phrases. Clicking a
measure selects the phrase that owns that measure's *first note*. The other
phrase remains reachable from its outline and from the phrase list, and the
measure is marked as carrying a boundary so the split is visible rather than
silently resolved.
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
from src.schemas.analysis import AnalysisBundle
from src.schemas.geometry import Region
from src.schemas.score import Difficulty, Measure, Phrase, Score

# The ribbon lives inside the bottom of the system band. That band is the staff
# plus margin, clamped by cv_geometry to halfway toward the neighbouring staff,
# so its lowest sliver is the whitespace between systems: "directly below each
# system" without covering any notation. Bands tile vertically with no gap
# between them, so there is nowhere else to put it that is still attached to the
# system it describes.
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
    contribution: str
    detail: str


@dataclasses.dataclass(frozen=True)
class MeasureView:
    id: str
    label: str
    ordinal: int
    system_id: str
    phrase_id: str | None
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
    measure_id: str
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


@dataclasses.dataclass(frozen=True)
class PhraseView:
    id: str
    label: str
    level: str
    parent_id: str | None
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
    legend: list[dict]
    assumptions: list[str]
    warnings: list[str]
    quality_counts: dict[str, int]
    measure_total: int
    rated_total: int
    unrated_label: str
    unrated_color: str
    default_phrase_id: str | None


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


def _factors(difficulty: Difficulty | None, limit: int | None = None) -> list[FactorView]:
    if difficulty is None:
        return []
    ordered = sorted(difficulty.factors, key=lambda f: f.contribution, reverse=True)
    if limit is not None:
        ordered = ordered[:limit]
    return [
        FactorView(label=f.label, contribution=f"+{f.contribution:.1f}", detail=f.detail)
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


def _ribbon_segments(
    system_region: Region, measures: list[Measure], ratings: dict[str, Difficulty]
) -> list[RibbonSegment]:
    """One flush run of colour across a system.

    A segment starts where its own measure starts and ends where the *next*
    measure starts, so neighbouring segments share an edge exactly. The run is
    stretched to the system's own extent at both ends, which absorbs the
    half-barline difference between a system box and its outer measures.
    """
    if not measures:
        return []

    ordered = sorted(measures, key=lambda m: m.region.x)
    top = system_region.y + system_region.h * (1.0 - RIBBON_INSET_FRAC - RIBBON_HEIGHT_FRAC)
    height = system_region.h * RIBBON_HEIGHT_FRAC

    segments: list[RibbonSegment] = []
    for i, measure in enumerate(ordered):
        left = system_region.x if i == 0 else measure.region.x
        if i + 1 < len(ordered):
            right = ordered[i + 1].region.x
        else:
            right = max(system_region.right, measure.region.right)
        width = max(0.0, right - left)

        difficulty = ratings.get(measure.id)
        score = difficulty.score if difficulty else None
        segments.append(
            RibbonSegment(
                measure_id=measure.id,
                label=measure.label,
                style=f"left:{_pct(left)};top:{_pct(top)};width:{_pct(width)};height:{_pct(height)}",
                color=color_for(score),
                is_rated=score is not None,
                score_text=format_score(score),
                category=category_for(score),
                aria_label=_measure_aria(measure, difficulty),
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


def build_view(bundle: AnalysisBundle) -> ScoreView:
    score = bundle.score
    phrases = [p for p in bundle.phrases if p.level == "phrase"]
    spots = [p for p in bundle.phrases if p.level == "trouble_spot"]
    owner_by_measure: dict[str, str] = {}
    for measure in score.measures:
        owner = owning_phrase(score, phrases, measure)
        if owner is not None:
            owner_by_measure[measure.id] = owner.id

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
                    segments=_ribbon_segments(system.region, members, bundle.measure_difficulty),
                    has_ribbon=bool(members),
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
            unreadable = [
                m
                for m in (measures_by_id.get(i) for i in phrase.measure_ids)
                if m is not None and not m.is_analyzable
            ]
            unrated_reason = (
                f"{len(unreadable)} of {len(phrase.measure_ids)} measures here could not be "
                "read, so this phrase is left unrated rather than given a number it has not earned."
                if unreadable
                else "No measure in this phrase could be rated."
            )

        return PhraseView(
                id=phrase.id,
                label=phrase.label,
                level=phrase.level,
                parent_id=phrase.parent_id,
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

    quality_counts: dict[str, int] = {}
    for measure in score.measures:
        quality_counts[measure.quality] = quality_counts.get(measure.quality, 0) + 1

    rated_total = sum(
        1 for d in bundle.measure_difficulty.values() if d.score is not None
    )

    return ScoreView(
        score_id=score.id,
        title=score.title or "Untitled score",
        is_example=score.is_example,
        pages=pages,
        phrases=phrase_views,
        trouble_spots=spot_views,
        legend=legend(),
        assumptions=list(score.assumptions),
        warnings=list(score.warnings),
        quality_counts=quality_counts,
        measure_total=len(score.measures),
        rated_total=rated_total,
        unrated_label=UNRATED_LABEL,
        unrated_color=UNRATED_COLOR,
        default_phrase_id=phrase_views[0].id if phrase_views else None,
    )


def _factor_payload(factors: list[FactorView]) -> list[dict]:
    return [{"label": f.label, "contribution": f.contribution, "detail": f.detail} for f in factors]


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
    selectable = list(view.phrases) + list(view.trouble_spots)
    # Which trouble spot, if any, covers each measure. Selection resolves to the
    # most specific thing that owns a measure: clicking the measure a hard spot
    # is marked on should select the hard spot, not the whole phrase around it.
    spot_by_measure = {
        mid: spot.id for spot in view.trouble_spots for mid in spot.measure_ids
    }
    return {
        "scoreId": view.score_id,
        "defaultPhraseId": view.default_phrase_id,
        "unratedLabel": view.unrated_label,
        "measures": {
            m.id: {
                "label": m.label,
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
        "phrases": {
            p.id: {
                "label": p.label,
                "level": p.level,
                "parentId": p.parent_id,
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
            }
            for p in selectable
        },
    }
