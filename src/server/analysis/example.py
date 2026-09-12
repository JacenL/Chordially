"""The prepared example score.

Example mode exists so the product can be demonstrated and tested with no API
credentials at all. It loads a committed analysis produced by
`scripts/build_example_fixture.py` from a real scan -- not hand-authored data --
so what it shows is a genuine recognition result, including the measures
recognition failed to read.

It is loaded once and reused. The bundle is immutable as far as the viewer is
concerned, and re-reading 250KB of JSON per request buys nothing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.config import PROJECT_ROOT
from src.schemas.analysis import AnalysisBundle

EXAMPLE_PATH = PROJECT_ROOT / "fixtures" / "expected" / "wohlfahrt-p3-analysis.json"


class ExampleUnavailable(RuntimeError):
    """The example fixture is missing or does not match the current schema."""


@lru_cache(maxsize=1)
def load_example(path: Path | None = None) -> AnalysisBundle:
    target = path or EXAMPLE_PATH
    if not target.exists():
        raise ExampleUnavailable(
            f"Example analysis not found at {target}. "
            "Rebuild it with: python scripts/build_example_fixture.py"
        )
    try:
        return AnalysisBundle.load_path(target)
    except Exception as exc:  # noqa: BLE001 - reported to the user verbatim
        raise ExampleUnavailable(
            f"Example analysis at {target} did not validate against the current "
            f"schema: {exc}"
        ) from exc
