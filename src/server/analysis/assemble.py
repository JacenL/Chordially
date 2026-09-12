"""Assemble a Score from page geometry plus transcribed content.

This is the join between the two independent halves of recognition: OpenCV knows
*where* every measure is, a vision model knows *what* is in it. Neither is
trusted to do the other's job.

The join is checked, not assumed. A chunk's transcribed measure count must match
the number of measure regions geometry found for that chunk. When it does not,
those measures are marked unreadable rather than being shifted into place --
misaligning notes against regions would produce a confident-looking overlay that
is simply wrong, which is worse than an honest gap.
"""

from __future__ import annotations

import hashlib
from fractions import Fraction

from src.features.difficulty.rubric import (
    DEFAULT_TEMPO_BPM,
    RUBRIC_VERSION,
    aggregate_phrase,
    rate_measure,
)
from src.features.segmentation.phrases import (
    Candidate,
    boundary_from_candidate,
    choose_boundaries,
    score_boundary_after,
)
from src.schemas.geometry import Region
from src.schemas.music import (
    MeasureTranscription,
    repair_uniform_scale,
    validate_measure,
)
from src.schemas.score import (
    Anchor,
    Difficulty,
    Measure,
    Note,
    Page,
    Phrase,
    Score,
    System,
)
from src.server.recognition.cv_geometry import PageGeometry


def fingerprint(data: bytes) -> str:
    """Content hash of the uploaded bytes.

    Progress and settings key on this, so the same file reopened restores its
    state, while a different file with the same name cannot inherit it.
    """
    return hashlib.sha256(data).hexdigest()[:16]


def _mid(score_id: str, ordinal: int) -> str:
    return f"{score_id}:m{ordinal:04d}"


def build_score(
    *,
    score_id: str,
    content_fingerprint: str,
    geometry: PageGeometry,
    transcriptions: dict[tuple[int, int], MeasureTranscription],
    input_kind: str = "pdf_scan",
    title: str = "",
    is_example: bool = False,
    image_url: str = "",
    tempo_bpm: float | None = None,
    page_index: int = 0,
    signatures_by_system: dict[int, dict[str, int | None]] | None = None,
    not_attempted: set[tuple[int, int]] | None = None,
) -> Score:
    """Build a Score. `transcriptions` is keyed by (system_index, measure_index).

    `signatures_by_system` is the authority on clef, key and meter. Those are
    taken from where they are actually printed -- a system start -- rather than
    from each measure's own transcription, because a crop from mid-staff shows
    no signature and anything it reports about one is inference.
    """
    assumed_tempo = tempo_bpm is None
    tempo = tempo_bpm or DEFAULT_TEMPO_BPM

    page = Page(
        id=f"{score_id}:p{page_index}",
        index=page_index,
        width_px=geometry.width_px,
        height_px=geometry.height_px,
        render_dpi=geometry.render_dpi,
        skew_corrected_deg=geometry.skew_deg,
        image_url=image_url,
    )

    systems: list[System] = []
    measures: list[Measure] = []
    notes: list[Note] = []
    warnings: list[str] = []

    # Carried forward across the page: a mid-page crop rarely reprints the clef,
    # key or meter, so what earlier measures established stands until contradicted.
    beats = beat_value = key_fifths = None
    ordinal = 0

    sigs = signatures_by_system or {}

    for sysd in geometry.systems:
        sys_id = f"{score_id}:s{sysd.index:02d}"
        sig = sigs.get(sysd.index)
        if sig:
            beats = sig.get("beats") or beats
            beat_value = sig.get("beat_value") or beat_value
            if sig.get("key_fifths") is not None:
                key_fifths = sig["key_fifths"]
        system = System(
            id=sys_id,
            page_index=page_index,
            index=sysd.index,
            region=Region(page_index=page_index, **vars(sysd.box)),
        )

        for md in sysd.measures:
            mid = _mid(score_id, ordinal)
            t = transcriptions.get((sysd.index, md.index_in_system))

            if (sysd.index, md.index_in_system) in (not_attempted or set()):
                quality = "not_attempted"
                quality_note = "this section was never read; the request did not complete"
            else:
                quality = "unreadable"
                quality_note = "no transcription was produced for this region"
            note_ids: list[str] = []

            if t is not None:
                # Meter comes from the system signature, never from this
                # measure's own guess about one it cannot see.
                verdict = validate_measure(t, beats, beat_value)

                # One narrow, disclosed repair: a uniform beam miscount. Any
                # measure it touches is marked uncertain, never confident.
                repaired_note = ""
                if not verdict.ok and not verdict.non_musical and beats and beat_value:
                    fix = repair_uniform_scale(t, Fraction(beats, beat_value))
                    if fix is not None:
                        t, repaired_note = fix
                        verdict = validate_measure(t, beats, beat_value)
                        if verdict.ok:
                            verdict = verdict.model_copy(
                                update={"low_confidence": True, "reason": repaired_note}
                            )
                if verdict.non_musical:
                    quality = "non_musical"
                    quality_note = "clef, key or time signature only -- no notes here"
                elif verdict.ok:
                    quality = "uncertain" if verdict.low_confidence else "confident"
                    quality_note = verdict.reason
                    for i, ev in enumerate(t.notes):
                        nid = f"{mid}:n{i:02d}"
                        notes.append(
                            Note(id=nid, measure_id=mid, index_in_measure=i, event=ev)
                        )
                        note_ids.append(nid)
                else:
                    quality = "unreadable"
                    quality_note = verdict.reason

            measure = Measure(
                id=mid,
                label=str(ordinal + 1),
                ordinal=ordinal,
                system_id=sys_id,
                region=Region(page_index=page_index, **vars(md.box)),
                note_ids=note_ids,
                beats=beats,
                beat_value=beat_value,
                key_fifths=key_fifths,
                tempo_bpm=tempo,
                tempo_is_assumed=assumed_tempo,
                quality=quality,  # type: ignore[arg-type]
                quality_note=quality_note,
            )
            measures.append(measure)
            system.measure_ids.append(mid)
            ordinal += 1

        systems.append(system)
        page.system_ids.append(sys_id)

    unreadable = sum(1 for m in measures if m.quality == "unreadable")
    if unreadable:
        warnings.append(
            f"{unreadable} of {len(measures)} measures could not be read reliably "
            "and are left unrated."
        )
    skipped = sum(1 for m in measures if m.quality == "not_attempted")
    if skipped:
        warnings.append(
            f"{skipped} of {len(measures)} measures were never read because the "
            "recognition request did not complete. This is not a judgement about "
            "the notation, and re-running may succeed."
        )

    assumptions: list[str] = []
    if assumed_tempo:
        assumptions.append(
            f"No tempo is printed, so ratings assume {DEFAULT_TEMPO_BPM:.0f} BPM. "
            "Set a tempo above to recalculate."
        )

    return Score(
        id=score_id,
        fingerprint=content_fingerprint,
        input_kind=input_kind,  # type: ignore[arg-type]
        title=title,
        is_example=is_example,
        pages=[page],
        systems=systems,
        measures=measures,
        notes=notes,
        assumptions=assumptions,
        warnings=warnings,
    )


def rate_score(score: Score) -> dict[str, Difficulty]:
    """Rate every analyzable measure. Unanalyzable ones get an explicit None."""
    out: dict[str, Difficulty] = {}
    for m in score.measures_in_order():
        if not m.is_analyzable or not m.beats or not m.beat_value:
            out[m.id] = Difficulty(
                target_id=m.id,
                score=None,
                rubric_version=RUBRIC_VERSION,
                assumptions=[m.quality_note] if m.quality_note else [],
            )
            continue
        events = [n.event for n in score.notes_of(m)]
        value, factors = rate_measure(
            events,
            m.beats,
            m.beat_value,
            tempo_bpm=m.tempo_bpm or DEFAULT_TEMPO_BPM,
            key_fifths=m.key_fifths or 0,
        )
        out[m.id] = Difficulty(
            target_id=m.id,
            score=value,
            factors=factors,
            rubric_version=RUBRIC_VERSION,
            assumptions=(
                ["tempo assumed"] if m.tempo_is_assumed else []
            ) + (["recognition uncertain"] if m.quality == "uncertain" else []),
        )
    return out


def segment_score(score: Score) -> list[Phrase]:
    """Divide the score into phrases, then extend each into a practice range."""
    ordered = score.measures_in_order()
    if not ordered:
        return []

    notes_by_measure = {m.id: [n.event for n in score.notes_of(m)] for m in ordered}

    candidates: list[Candidate] = []
    for i, m in enumerate(ordered):
        nxt = ordered[i + 1] if i + 1 < len(ordered) else None
        candidates.append(
            score_boundary_after(
                m,
                notes_by_measure[m.id],
                nxt,
                notes_by_measure.get(nxt.id, []) if nxt else [],
            )
        )

    cut_after = choose_boundaries(candidates, len(ordered))
    by_index = {c.measure_index: c for c in candidates}

    starts = [0] + [c + 1 for c in cut_after]
    ends = cut_after + [len(ordered) - 1]

    phrases: list[Phrase] = []
    for n, (s, e) in enumerate(zip(starts, ends)):
        members = ordered[s : e + 1]
        first, last = members[0], members[-1]

        start_cand = by_index.get(s - 1) if s > 0 else None
        end_cand = by_index.get(e)

        # Practice range: extend through the first playable note of the next
        # phrase, so the join is rehearsed rather than the phrase stopping dead.
        # The final phrase has no next note, and nothing is fabricated for it.
        practice_end = Anchor(
            measure_id=last.id, note_index=max(0, len(last.note_ids) - 1)
        )
        has_overlap = False
        for later in ordered[e + 1 :]:
            if later.note_ids:
                practice_end = Anchor(measure_id=later.id, note_index=0)
                has_overlap = True
                break

        # One region fragment per system, never a single box spanning several.
        regions: list[Region] = []
        for sys_id in dict.fromkeys(m.system_id for m in members):
            in_sys = [m for m in members if m.system_id == sys_id]
            left = min(m.region.x for m in in_sys)
            right = max(m.region.right for m in in_sys)
            top = min(m.region.y for m in in_sys)
            bottom = max(m.region.bottom for m in in_sys)
            regions.append(
                Region(
                    page_index=in_sys[0].region.page_index,
                    x=left,
                    y=top,
                    w=max(1e-6, right - left),
                    h=max(1e-6, bottom - top),
                )
            )

        phrases.append(
            Phrase(
                id=f"{score.id}:ph{n:03d}",
                label=f"Phrase {n + 1}",
                structural_start=Anchor(measure_id=first.id, note_index=0),
                structural_end=Anchor(
                    measure_id=last.id, note_index=max(0, len(last.note_ids) - 1)
                ),
                practice_start=Anchor(measure_id=first.id, note_index=0),
                practice_end=practice_end,
                has_practice_overlap=has_overlap,
                regions=regions,
                start_boundary=boundary_from_candidate(
                    start_cand, "the piece begins here"
                ),
                end_boundary=boundary_from_candidate(
                    end_cand if e < len(ordered) - 1 else None, "the piece ends here"
                ),
                measure_ids=[m.id for m in members],
            )
        )
    return phrases


def rate_phrases(
    phrases: list[Phrase], measure_ratings: dict[str, Difficulty]
) -> dict[str, Difficulty]:
    """Aggregate member measure ratings into phrase ratings, exposing the peak."""
    out: dict[str, Difficulty] = {}
    for p in phrases:
        member_scores = [measure_ratings[mid].score for mid in p.measure_ids if mid in measure_ratings]
        combined, peak = aggregate_phrase(member_scores)
        peak_id = None
        if peak is not None:
            peak_id = max(
                (mid for mid in p.measure_ids if measure_ratings.get(mid, Difficulty(target_id=mid, rubric_version=RUBRIC_VERSION)).score is not None),
                key=lambda mid: measure_ratings[mid].score or -1.0,
                default=None,
            )
        out[p.id] = Difficulty(
            target_id=p.id,
            score=combined,
            peak=peak,
            peak_target_id=peak_id,
            rubric_version=RUBRIC_VERSION,
        )
    return out
