"""A complete analysis result: the score plus everything computed about it.

This is the unit the viewer consumes and the unit `scripts/build_example_fixture.py`
writes. Keeping it a validated model rather than a loose dict matters at exactly
one place -- `load_path` -- where a JSON file from disk enters the program. A
fixture is still an external artifact: it can be stale, hand-edited, or produced
by an older schema, and the honest failure mode is a validation error naming the
field, not a viewer that renders half a score and a stack trace.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from src.schemas.score import Difficulty, Phrase, Score


class RecognitionReport(BaseModel):
    """What the recognition pass actually did, including what it failed to do.

    Surfaced to the user in plain language. `errors` holds provider and
    measure-count messages verbatim for the log view; they are never rendered
    into the practice flow.
    """

    chunks_attempted: int = 0
    mismatched_chunks: int = 0
    errors: list[str] = Field(default_factory=list)
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


class SectionEdits(BaseModel):
    """A user's own section boundaries, kept apart from the derived ones.

    Sections are re-derived on every request -- they depend on ratings, and
    ratings move with tempo -- so a user's split cannot be stored as a section.
    It is stored as the decision that produced it: this measure begins a section,
    that one does not. Both are keyed by measure id, which survives re-analysis;
    a section id would not.
    """

    starts: list[str] = Field(
        default_factory=list,
        description="Measure ids that must begin a section, whatever the heuristic says.",
    )
    joins: list[str] = Field(
        default_factory=list,
        description="Measure ids where a derived section boundary is suppressed.",
    )

    @property
    def is_empty(self) -> bool:
        return not self.starts and not self.joins


class AnalysisBundle(BaseModel):
    """Score, ratings, phrases and recognition status as one validated object."""

    score: Score
    measure_difficulty: dict[str, Difficulty] = Field(default_factory=dict)
    phrases: list[Phrase] = Field(default_factory=list)
    phrase_difficulty: dict[str, Difficulty] = Field(default_factory=dict)
    recognition: RecognitionReport = Field(default_factory=RecognitionReport)
    section_edits: SectionEdits = Field(default_factory=SectionEdits)

    @classmethod
    def load_path(cls, path: Path) -> "AnalysisBundle":
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))

    def measure_rating(self, measure_id: str) -> Difficulty | None:
        return self.measure_difficulty.get(measure_id)

    def phrase_rating(self, phrase_id: str) -> Difficulty | None:
        return self.phrase_difficulty.get(phrase_id)

    def phrase(self, phrase_id: str) -> Phrase | None:
        return next((p for p in self.phrases if p.id == phrase_id), None)
