"""The analyzed score: stable identity, geometry, and analysis results.

Identity rules that the rest of the system relies on:

* Stable IDs are ours and are distinct from printed labels. Printed measure
  numbers repeat across movements, restart after repeats, and are often absent
  entirely -- on the fixture page they are absent. Anything that must survive
  re-analysis, selection, or a stored progress record keys on the stable ID.
* A measure's `label` is what a musician reads off the page and says out loud.
  It is for display only and is never used as a key.

Range convention: all ranges are inclusive of both endpoints, expressed as
(measure_id, note_index) anchors. Note indices are positions within that
measure's `note_ids`, so a range can start or end partway through a measure --
which is what lets a phrase boundary fall inside a measure, as the spec requires.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.schemas.geometry import Region
from src.schemas.music import NoteEvent

# "not_attempted" is kept distinct from "unreadable" on purpose. Unreadable is a
# statement about the notation: recognition looked and could not read it.
# Not-attempted is a statement about us: the request never completed, so nothing
# is known either way. Collapsing them would let an outage, a rate limit or an
# exhausted credit balance masquerade as poor recognition and quietly defame a
# perfectly legible page.
RecognitionQuality = Literal[
    "confident", "uncertain", "unreadable", "non_musical", "not_attempted"
]
InputKind = Literal["pdf_scan", "image_scan", "musicxml", "example"]


class Anchor(BaseModel):
    """A position in the score: a note within a measure."""

    model_config = {"frozen": True}

    measure_id: str
    note_index: int = Field(ge=0)


class Note(BaseModel):
    """One event, with a stable identity and its parent measure."""

    id: str
    measure_id: str
    index_in_measure: int = Field(ge=0)
    event: NoteEvent


class Measure(BaseModel):
    """A barline-delimited region with whatever was recognized inside it."""

    id: str
    label: str = Field(
        description="What a musician would call this measure. Display only, never a key."
    )
    ordinal: int = Field(ge=0, description="Position in the piece, counting from 0.")
    system_id: str
    region: Region
    note_ids: list[str] = Field(default_factory=list)

    beats: int | None = None
    beat_value: int | None = None
    key_fifths: int | None = None
    tempo_bpm: float | None = None
    tempo_is_assumed: bool = True

    quality: RecognitionQuality = "confident"
    quality_note: str = ""

    @property
    def is_analyzable(self) -> bool:
        """Whether this measure may carry a rating.

        Non-musical regions (a clef and time signature with no notes) and
        unreadable ones may not. They are rendered distinctly from easy and from
        difficult, never as 0.0.
        """
        return self.quality in ("confident", "uncertain") and bool(self.note_ids)


RibbonPlacement = Literal["clear", "crowded", "unmeasured"]


class System(BaseModel):
    """One staff line. For solo violin, one staff is one system."""

    id: str
    page_index: int = Field(ge=0)
    index: int = Field(ge=0)
    region: Region
    measure_ids: list[str] = Field(default_factory=list)

    ribbon_region: Region | None = Field(
        default=None,
        description="Where the difficulty ribbon may be drawn for this system, "
        "measured from the page's ink. May sit outside `region`: the blank gutter "
        "straddles the boundary between two system boxes.",
    )
    ribbon_placement: RibbonPlacement = Field(
        default="unmeasured",
        description=(
            "'clear' -- a blank gutter was found and the band sits in it. "
            "'crowded' -- no gutter was tall enough, so the band was placed where "
            "it obscures the least ink and may overlap notation. 'unmeasured' -- "
            "there were no pixels to check, which is the case for an engraved page "
            "served as SVG. Three states rather than a boolean, so 'not checked' "
            "cannot read as 'fine'."
        ),
    )


class Page(BaseModel):
    id: str
    index: int = Field(ge=0)
    width_px: int
    height_px: int
    render_dpi: int
    skew_corrected_deg: float = 0.0
    image_url: str = ""
    system_ids: list[str] = Field(default_factory=list)


class Score(BaseModel):
    """A whole analyzed upload.

    `fingerprint` is a content hash of the uploaded bytes. Progress and settings
    key on it, so reopening the same file restores its state while a different
    file -- even with the same filename -- cannot inherit another score's
    practice history.
    """

    id: str
    fingerprint: str
    input_kind: InputKind
    title: str = ""
    is_example: bool = False

    pages: list[Page] = Field(default_factory=list)
    systems: list[System] = Field(default_factory=list)
    measures: list[Measure] = Field(default_factory=list)
    notes: list[Note] = Field(default_factory=list)

    assumptions: list[str] = Field(
        default_factory=list,
        description="Stated assumptions, e.g. an assumed tempo. Shown to the user.",
    )
    warnings: list[str] = Field(default_factory=list)

    def measure(self, measure_id: str) -> Measure | None:
        return next((m for m in self.measures if m.id == measure_id), None)

    def note(self, note_id: str) -> Note | None:
        return next((n for n in self.notes if n.id == note_id), None)

    def notes_of(self, measure: Measure) -> list[Note]:
        by_id = {n.id: n for n in self.notes}
        return [by_id[i] for i in measure.note_ids if i in by_id]

    def measures_in_order(self) -> list[Measure]:
        return sorted(self.measures, key=lambda m: m.ordinal)

    @property
    def analyzable_measures(self) -> list[Measure]:
        return [m for m in self.measures_in_order() if m.is_analyzable]


# --------------------------------------------------------------------------
# Analysis results
# --------------------------------------------------------------------------


class DifficultyFactor(BaseModel):
    """One named contribution to a rating, in the user's language.

    Kept separate from the numeric weight so the sidebar can explain a rating
    without exposing rubric internals.
    """

    key: str
    label: str
    contribution: float = Field(description="Points contributed, on the 0-10 scale.")
    detail: str = ""


class Difficulty(BaseModel):
    """A rating for one target, or an explicit absence of one.

    `score` is None when the target could not be analyzed. None is not 0.0 and
    must never be rendered as if it were: 0.0 means genuinely easy, None means
    unknown.
    """

    target_id: str
    score: float | None = Field(default=None, ge=0.0, le=10.0)
    peak: float | None = Field(
        default=None,
        ge=0.0,
        le=10.0,
        description="Highest local rating inside this target, so a brief obstacle "
        "inside an easy phrase is not averaged away.",
    )
    peak_target_id: str | None = None
    factors: list[DifficultyFactor] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    rubric_version: str

    @property
    def is_rated(self) -> bool:
        return self.score is not None


BoundaryEvidence = Literal[
    "rest",
    "long_note",
    "slur_end",
    "cadential_contour",
    "barline",
    "meter_change",
    "key_change",
    "double_bar",
    "system_start",
    "piece_start",
    "piece_end",
]


class PhraseBoundary(BaseModel):
    """Why a boundary was placed, in terms a musician can argue with."""

    evidence: list[BoundaryEvidence] = Field(default_factory=list)
    reason: str = Field(description="One plain-language sentence.")
    confidence: float = Field(ge=0.0, le=1.0)


class Phrase(BaseModel):
    """One musical idea.

    Two ranges, deliberately not conflated:

    * `structural_start`/`structural_end` -- what the phrase *is*. These tile
      the piece with no gaps and no overlaps; exactly one phrase owns any note.
    * `practice_start`/`practice_end` -- what you *play* when practising it,
      extended through the first playable note of the next phrase so the
      boundary is rehearsed in context. These may overlap between neighbours.

    A rating describes the structural range, not the borrowed note.
    """

    id: str
    label: str
    level: Literal["section", "phrase", "trouble_spot"] = "phrase"
    parent_id: str | None = None

    structural_start: Anchor
    structural_end: Anchor
    practice_start: Anchor
    practice_end: Anchor
    has_practice_overlap: bool = False

    regions: list[Region] = Field(
        default_factory=list,
        description="One fragment per system the phrase touches, never one box spanning them.",
    )
    start_boundary: PhraseBoundary
    end_boundary: PhraseBoundary
    user_edited: bool = False

    measure_ids: list[str] = Field(default_factory=list)
