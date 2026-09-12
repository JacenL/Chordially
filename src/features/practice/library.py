"""Load and validate the technique library.

The library is data, not code, so it is validated on load like any other
external input. A technique whose sourceIds name a source that does not exist
is a broken citation, and a broken citation in a teaching tool is worse than a
missing one -- it is caught here rather than rendered.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CONTENT_DIR = Path(__file__).resolve().parent.parent.parent / "content"

EvidenceCategory = Literal[
    "teacher pedagogy", "research-informed", "small experimental study",
    "qualitative questionnaire research", "app heuristic",
]


class Source(BaseModel):
    model_config = {"extra": "forbid"}

    id: str
    title: str
    author: str
    publication: str
    url: str
    evidenceCategory: EvidenceCategory
    supports: str
    doesNotSupport: str


class Technique(BaseModel):
    model_config = {"extra": "forbid"}

    id: str
    title: str
    evidenceCategory: EvidenceCategory
    sourceIds: list[str] = Field(default_factory=list)
    fits: str
    triggerFeatures: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(min_length=1)
    listeningGoals: list[str] = Field(min_length=1)
    tempoRule: str
    successCriteria: str
    returnToContext: str
    cautions: list[str] = Field(default_factory=list)

    @field_validator("sourceIds")
    @classmethod
    def _heuristics_claim_nothing(cls, value: list[str], info) -> list[str]:
        category = info.data.get("evidenceCategory")
        if category in ("teacher pedagogy", "research-informed") and not value:
            raise ValueError(
                "a technique claiming pedagogical or research backing must name a source"
            )
        return value


class Library(BaseModel):
    sources: dict[str, Source]
    techniques: dict[str, Technique]

    def source_list(self, ids: list[str]) -> list[Source]:
        return [self.sources[i] for i in ids if i in self.sources]


@lru_cache(maxsize=1)
def load_library(directory: Path | None = None) -> Library:
    base = directory or CONTENT_DIR
    sources_raw = json.loads((base / "sources.json").read_text(encoding="utf-8"))
    techniques_raw = json.loads((base / "techniques.json").read_text(encoding="utf-8"))

    sources = {s["id"]: Source.model_validate(s) for s in sources_raw["sources"]}
    techniques = {t["id"]: Technique.model_validate(t) for t in techniques_raw["techniques"]}

    for technique in techniques.values():
        missing = [sid for sid in technique.sourceIds if sid not in sources]
        if missing:
            raise ValueError(
                f"technique {technique.id} cites unknown source(s): {', '.join(missing)}"
            )
    return Library(sources=sources, techniques=techniques)
