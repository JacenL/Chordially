"""User corrections to practice-section boundaries.

Sections are derived on every request, because they group phrases by how hard
they are and by what they demand, and both move when the tempo does. So a user's
split cannot be stored *as a section* -- the next retune would rebuild the list
and throw it away. What is stored is the decision behind it, keyed by a measure
id: this measure begins a section, or this one does not.

Two operations, matching the two the phrase level already offers:

**Split** makes a measure begin a section. A section boundary can only land on a
phrase start, so if the chosen measure is not one, the owning phrase is split
there first. That is not a side effect to hide: a section is a group of whole
phrases, and asking for a boundary in the middle of a musical idea is asking for
that idea to be two ideas.

**Merge** removes the boundary between a section and the one after it, including
a boundary the printed key or time signature produced. The evidence for that
boundary is still reported in the sidebar; the user is allowed to disagree with
what it implies for how they want to practise, which is the whole point of
offering the control.

Both are recorded on the bundle's `SectionEdits` and survive retuning, editing
and reloading, for as long as the server process lives. They are not persistence
and `src/server/analysis/store.py` says so.
"""

from __future__ import annotations

from src.features.segmentation.edit import EditRefused, split_phrase
from src.features.segmentation.sections import find_sections
from src.schemas.analysis import AnalysisBundle


def _sections_of(bundle: AnalysisBundle) -> list:
    """Sections as they currently stand, derived from what the bundle holds."""
    phrases = [p for p in bundle.phrases if p.level == "phrase"]
    return find_sections(
        bundle.score,
        phrases,
        bundle.measure_difficulty,
        starts=set(bundle.section_edits.starts),
        joins=set(bundle.section_edits.joins),
    )


def split_section(bundle: AnalysisBundle, at_measure_id: str) -> AnalysisBundle:
    """Begin a new section at `at_measure_id`, splitting its phrase if needed."""
    measure = bundle.score.measure(at_measure_id)
    if measure is None:
        raise EditRefused("That measure is not part of this score.")

    ordered = bundle.score.measures_in_order()
    if ordered and ordered[0].id == at_measure_id:
        raise EditRefused(
            "A section already begins at the first measure of the piece."
        )

    phrases = [p for p in bundle.phrases if p.level == "phrase"]
    owner = next((p for p in phrases if at_measure_id in p.measure_ids), None)
    if owner is None:
        raise EditRefused("That measure does not belong to a phrase.")

    if owner.measure_ids[0] != at_measure_id:
        # A section groups whole phrases, so the phrase has to give way first.
        rebuilt = split_phrase(bundle.score, phrases, owner.id, at_measure_id)
        bundle.phrases = [p for p in bundle.phrases if p.level != "phrase"] + rebuilt

    if at_measure_id not in bundle.section_edits.starts:
        bundle.section_edits.starts.append(at_measure_id)
    if at_measure_id in bundle.section_edits.joins:
        bundle.section_edits.joins.remove(at_measure_id)
    return bundle


def merge_section(bundle: AnalysisBundle, section_id: str) -> AnalysisBundle:
    """Join this section to the one after it."""
    sections = _sections_of(bundle)
    index = next((i for i, s in enumerate(sections) if s.id == section_id), None)
    if index is None:
        raise EditRefused("That passage is no longer part of this score.")
    if index + 1 >= len(sections):
        raise EditRefused(
            "This is the last passage on the page, so there is nothing after it "
            "to merge with."
        )

    boundary_measure = sections[index + 1].measure_ids[0]
    if boundary_measure not in bundle.section_edits.joins:
        bundle.section_edits.joins.append(boundary_measure)
    if boundary_measure in bundle.section_edits.starts:
        bundle.section_edits.starts.remove(boundary_measure)
    return bundle


def reset_sections(bundle: AnalysisBundle) -> AnalysisBundle:
    """Discard section edits and go back to the derived grouping."""
    bundle.section_edits.starts.clear()
    bundle.section_edits.joins.clear()
    return bundle
