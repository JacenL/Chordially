"""Re-rate an analysis at a different tempo.

The rubric measures demand per second, not per note, so tempo is not a display
preference -- it changes every number on the page. A run of 16ths that is
comfortable at 60 BPM is a different piece of music at 120. Until now the app
said so and offered no way to act on it.

Nothing here touches recognition. Re-rating is arithmetic over an analysis
already in memory: no provider call, no geometry, no cost. That is what makes a
full page reload the right mechanism rather than client-side re-painting.

Two rules govern the recomputation.

**A printed tempo outranks a supplied one.** If the page prints a tempo for a
measure, that is evidence read off the score, and a global setting must not
silently overwrite it. Only measures whose tempo was *assumed* are retuned. The
resulting notice says both things happened.

**Never mutate the input.** `load_example` is lru_cached, so the example bundle
is shared by every request in the process; retuning it in place would leak one
user's tempo into everyone else's page and corrupt the fixture for the life of
the server.
"""

from __future__ import annotations

from src.features.difficulty.rubric import DEFAULT_TEMPO_BPM
from src.schemas.analysis import AnalysisBundle
from src.server.analysis.assemble import rate_phrases, rate_score

# A violinist's plausible range. Outside it the note-rate feature saturates and
# the rating stops meaning anything, so the value is refused rather than clamped
# -- a silently clamped tempo would make the page disagree with the input box.
MIN_TEMPO_BPM = 20.0
MAX_TEMPO_BPM = 300.0


class TempoOutOfRange(ValueError):
    """A tempo outside the range the rubric can say anything useful about."""


def parse_tempo(raw: str | None) -> float | None:
    """Read a tempo from a query parameter. Junk is None, not an error.

    A malformed URL should leave the user looking at their score at the assumed
    tempo, not at an error page with their analysis gone.
    """
    if raw is None or not str(raw).strip():
        return None
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if not (MIN_TEMPO_BPM <= value <= MAX_TEMPO_BPM):
        return None
    return value


def retune(bundle: AnalysisBundle, tempo_bpm: float | None) -> AnalysisBundle:
    """A copy of `bundle` rated at `tempo_bpm`. None restores the assumed tempo."""
    if tempo_bpm is not None and not (MIN_TEMPO_BPM <= tempo_bpm <= MAX_TEMPO_BPM):
        raise TempoOutOfRange(
            f"{tempo_bpm:.0f} BPM is outside the {MIN_TEMPO_BPM:.0f}-"
            f"{MAX_TEMPO_BPM:.0f} BPM range these ratings are meaningful over."
        )

    fresh = bundle.model_copy(deep=True)
    score = fresh.score

    applied = 0
    printed = 0
    for measure in score.measures:
        if not measure.tempo_is_assumed:
            printed += 1
            continue
        measure.tempo_bpm = tempo_bpm if tempo_bpm is not None else DEFAULT_TEMPO_BPM
        applied += 1

    fresh.measure_difficulty = rate_score(score)
    fresh.phrase_difficulty = rate_phrases(fresh.phrases, fresh.measure_difficulty)
    score.assumptions = _assumptions(tempo_bpm, applied, printed)
    return fresh


def _assumptions(tempo_bpm: float | None, applied: int, printed: int) -> list[str]:
    """The tempo disclosure, matching what was actually done to the measures."""
    if applied == 0 and printed == 0:
        return []

    if tempo_bpm is None:
        if applied == 0:
            return []
        text = (
            f"No tempo is printed, so ratings assume {DEFAULT_TEMPO_BPM:.0f} BPM. "
            "Set a tempo above to recalculate."
        )
    else:
        text = f"Ratings recalculated at {tempo_bpm:.0f} BPM, which you supplied."

    if printed:
        text += (
            f" {printed} measure{'s' if printed != 1 else ''} print a tempo and keep "
            "their own."
        )
    return [text]
