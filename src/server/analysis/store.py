"""Edited analyses, held in memory for the life of the process.

This is not persistence and must not be described as such. An edited phrase list
survives navigation and reload; it does not survive restarting the server. That
limitation is real, it is recorded in docs/demo.md, and the honest place to say
it is here, next to the dictionary that is the whole implementation.

An edit is seeded by deep-copying the source analysis, so editing the example
never touches the lru_cached fixture that every other request reads.
"""

from __future__ import annotations

import threading

from src.schemas.analysis import AnalysisBundle

_lock = threading.Lock()
_edited: dict[str, AnalysisBundle] = {}


def get(score_id: str) -> AnalysisBundle | None:
    """The edited analysis for this score, if any edit has been made."""
    with _lock:
        return _edited.get(score_id)


def put(score_id: str, bundle: AnalysisBundle) -> None:
    with _lock:
        _edited[score_id] = bundle


def seed(score_id: str, source: AnalysisBundle) -> AnalysisBundle:
    """The editable copy for this score, creating it on first edit."""
    with _lock:
        existing = _edited.get(score_id)
        if existing is not None:
            return existing
        fresh = source.model_copy(deep=True)
        _edited[score_id] = fresh
        return fresh


def clear(score_id: str) -> bool:
    """Discard edits and fall back to the inferred segmentation."""
    with _lock:
        return _edited.pop(score_id, None) is not None
