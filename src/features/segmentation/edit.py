"""User corrections to inferred phrase boundaries.

Segmentation is inference, and it reports its own confidence — often 0.3 to 0.5
on continuous etude writing, because the evidence genuinely is thin there. A
player who can see a boundary in the wrong place needs a way to say so; without
one, the honest confidence number is just an apology.

Two operations, both at measure boundaries: split a phrase in two, and merge a
phrase with the one after it. Boundaries inside a measure are supported by the
data model — anchors carry a note index — but not yet by this interface, and
saying that plainly is better than implying otherwise.

The invariant every edit preserves, stated in CLAUDE.md and enforced by tests:
structural phrase coverage tiles the analyzable music with no gaps and no
duplicate ownership. Practice ranges may overlap; structural ranges may not.
A phrase list is therefore always rebuilt from a partition of measure indices
rather than patched in place, because patching is how a gap gets introduced.
"""

from __future__ import annotations

from src.schemas.score import Phrase, PhraseBoundary, Score

# A boundary the user placed is not inferred, and does not get an inferred
# confidence. 1.0 records that this is the user's assertion, not the app's guess.
USER_CONFIDENCE = 1.0


class EditRefused(ValueError):
    """An edit that cannot be performed, with a reason to show the user."""


def _ranges(score: Score, phrases: list[Phrase]) -> list[tuple[int, int]]:
    """Each phrase as (first ordinal, last ordinal), in playing order."""
    by_id = {m.id: m for m in score.measures}
    out: list[tuple[int, int]] = []
    for phrase in phrases:
        ordinals = [by_id[mid].ordinal for mid in phrase.measure_ids if mid in by_id]
        if ordinals:
            out.append((min(ordinals), max(ordinals)))
    return sorted(out)


def _rebuild(
    score: Score,
    ranges: list[tuple[int, int]],
    previous: list[Phrase],
    edited_starts: set[int],
) -> list[Phrase]:
    """Rebuild the whole phrase list from a partition of measure indices.

    Boundary reasons are carried forward for any phrase whose start did not
    move, so a split does not erase the evidence recorded for its neighbours.
    A boundary the user created records that fact instead of inheriting an
    inferred reason it did not come from.
    """
    from src.server.analysis.assemble import make_phrase

    ordered = score.measures_in_order()
    old_by_start = {}
    by_id = {m.id: m for m in score.measures}
    for phrase in previous:
        ordinals = [by_id[mid].ordinal for mid in phrase.measure_ids if mid in by_id]
        if ordinals:
            old_by_start[min(ordinals)] = phrase

    user_boundary = PhraseBoundary(
        evidence=[],
        reason="you placed this boundary",
        confidence=USER_CONFIDENCE,
    )

    rebuilt: list[Phrase] = []
    for n, (start, end) in enumerate(ranges):
        previous_phrase = old_by_start.get(start)
        start_boundary = (
            user_boundary
            if start in edited_starts or previous_phrase is None
            else previous_phrase.start_boundary
        )
        next_start = ranges[n + 1][0] if n + 1 < len(ranges) else None
        end_boundary = (
            user_boundary
            if (next_start is not None and next_start in edited_starts)
            else (
                previous_phrase.end_boundary
                if previous_phrase is not None and previous_phrase.measure_ids
                and by_id[previous_phrase.measure_ids[-1]].ordinal == end
                else user_boundary
            )
        )
        rebuilt.append(
            make_phrase(
                ordered,
                start,
                end,
                phrase_id=f"{score.id}:ph{start:03d}",
                label=f"Phrase {n + 1}",
                start_boundary=start_boundary,
                end_boundary=end_boundary,
                user_edited=(
                    start in edited_starts
                    or (next_start is not None and next_start in edited_starts)
                    or (previous_phrase.user_edited if previous_phrase else False)
                ),
            )
        )
    return rebuilt


def split_phrase(score: Score, phrases: list[Phrase], phrase_id: str, at_measure_id: str) -> list[Phrase]:
    """Split one phrase so a new phrase begins at `at_measure_id`."""
    target = next((p for p in phrases if p.id == phrase_id), None)
    if target is None:
        raise EditRefused("That phrase is not part of this score.")

    measure = score.measure(at_measure_id)
    if measure is None or at_measure_id not in target.measure_ids:
        raise EditRefused("That measure is not inside the phrase you are splitting.")

    ranges = _ranges(score, phrases)
    start, end = next(
        (s, e) for s, e in ranges if s <= measure.ordinal <= e
    )
    if measure.ordinal == start:
        raise EditRefused(
            "A phrase already begins at that measure. Choose a later one, or "
            "merge it with the phrase before it."
        )

    new_ranges = [r for r in ranges if r != (start, end)]
    new_ranges.extend([(start, measure.ordinal - 1), (measure.ordinal, end)])
    return _rebuild(score, sorted(new_ranges), phrases, {measure.ordinal})


def merge_phrase(score: Score, phrases: list[Phrase], phrase_id: str) -> list[Phrase]:
    """Merge one phrase with the phrase that follows it."""
    target = next((p for p in phrases if p.id == phrase_id), None)
    if target is None:
        raise EditRefused("That phrase is not part of this score.")

    ranges = _ranges(score, phrases)
    by_id = {m.id: m for m in score.measures}
    ordinals = [by_id[mid].ordinal for mid in target.measure_ids if mid in by_id]
    if not ordinals:
        raise EditRefused("That phrase has no measures to merge.")

    start = min(ordinals)
    index = next(i for i, (s, _) in enumerate(ranges) if s == start)
    if index + 1 >= len(ranges):
        raise EditRefused(
            "This is the last phrase, so there is nothing after it to merge with."
        )

    following_start, following_end = ranges[index + 1]
    merged = (ranges[index][0], following_end)
    new_ranges = [r for i, r in enumerate(ranges) if i not in (index, index + 1)]
    new_ranges.append(merged)
    # The boundary that disappeared is the one the user acted on, so the merged
    # phrase is marked edited even though neither of its own ends moved.
    return _rebuild(score, sorted(new_ranges), phrases, {merged[0]})
