"""Re-derive the committed example analysis from the notes already in it.

`scripts/build_example_fixture.py` needs an API key, because it re-reads the
scan. This script needs nothing: the transcribed notes are already in the
fixture, and everything else in the file -- ratings, factors, phrase scores,
sections, trouble spots -- is arithmetic over those notes.

Run it whenever the rubric changes, so the committed example stops carrying
ratings from a superseded version of it. The viewer re-rates on every request
anyway, so a stale file never reaches a user; the reason to refresh it is that a
fixture is also a *record*, and one whose stored numbers disagree with the code
that produced them is a trap for the next reader.

    python scripts/refresh_example_analysis.py

Two things happen, in order.

**Accidentals are normalized once.** A vision transcription reports only the
accidentals printed in a measure and leaves the key signature implied; from C16
onward `alter` means the sounding alteration everywhere downstream, applied at
`build_score`. The notes already in this fixture predate that, so the key
signature the page prints is applied to them here. The pass is idempotent: a
note that already carries an alteration is left alone.

**Everything derived is recomputed** by the same `retune` the app uses, so the
fixture and a live request cannot disagree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schemas.analysis import AnalysisBundle  # noqa: E402
from src.server.analysis.assemble import apply_key_signature  # noqa: E402
from src.server.analysis.example import EXAMPLE_PATH  # noqa: E402
from src.server.analysis.recompute import retune  # noqa: E402


def main() -> int:
    bundle = AnalysisBundle.load_path(EXAMPLE_PATH)

    if bundle.score.input_kind != "musicxml":
        by_measure = {m.id: m for m in bundle.score.measures}
        changed = 0
        for note in bundle.score.notes:
            measure = by_measure.get(note.measure_id)
            updated = apply_key_signature(
                note.event, measure.key_fifths if measure else 0
            )
            if updated is not note.event:
                note.event = updated
                changed += 1
        print(f"applied the printed key signature to {changed} notes")

    refreshed = retune(bundle, None)

    rated = [d.score for d in refreshed.measure_difficulty.values() if d.score is not None]
    print(
        f"{len(rated)} of {len(refreshed.score.measures)} measures rated; "
        f"range {min(rated):.1f}-{max(rated):.1f}, "
        f"mean {sum(rated) / len(rated):.2f}"
    )
    print(
        f"{sum(1 for p in refreshed.phrases if p.level == 'section')} sections, "
        f"{sum(1 for p in refreshed.phrases if p.level == 'phrase')} phrases, "
        f"{sum(1 for p in refreshed.phrases if p.level == 'trouble_spot')} trouble spots"
    )

    EXAMPLE_PATH.write_text(
        json.dumps(refreshed.model_dump(mode="json"), indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {EXAMPLE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
