"""B2a: measure what Audiveris reads off the fixture scan, against the vision path.

This decides whether Audiveris replaces the vision model on the scan path. It
changes no code path and writes nothing into the application: it reads an
Audiveris MusicXML export and puts it through Chordially's own gate, so the two
recognition routes are judged by the same standard.

Prepare the export first. The unpacked Audiveris app-image needs no system Java
and no registry install:

    msiexec /a Audiveris-5.11.0-windowsConsole-x86_64.msi /qn TARGETDIR=<dir>
    <dir>\\Audiveris\\Audiveris.exe -batch -transcribe -export ^
        -output work\\audiveris-out -- fixtures\\scores\\wohlfahrt-op45-bk1-p3.pdf

Then:

    python scripts/spike_audiveris.py

What is measured, and why each number matters:

* **Measure count against geometry.** Chordially maps notes onto the scan by
  measure, and `assemble.build_score` refuses to shift a mismatched chunk into
  place. If Audiveris and OpenCV disagree about how many measures the page has,
  every downstream overlay is suspect. This is the load-bearing number, exactly
  as it was in C1.
* **How many measures pass `validate_measure`.** The same arithmetic gate the
  vision path answers to: durations must sum to the meter.
* **What it says about pitch.** Reported, not scored. Nothing here verifies
  pitch, and this script must not imply otherwise -- see B3.
"""

from __future__ import annotations

import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.schemas.analysis import AnalysisBundle  # noqa: E402
from src.schemas.music import validate_measure  # noqa: E402
from src.server.analysis.example import EXAMPLE_PATH  # noqa: E402
from src.server.recognition.musicxml_source import (  # noqa: E402
    read_part,
    transcribe_part,
)

EXPORT = Path("work/audiveris-out/wohlfahrt-op45-bk1-p3.mxl")


def main() -> int:
    if not EXPORT.exists():
        print(f"no export at {EXPORT}; see this file's docstring")
        return 1

    part, title, part_name, part_count = read_part(EXPORT.read_bytes())
    measures = transcribe_part(part, measure_limit=10_000)

    reference = AnalysisBundle.load_path(EXAMPLE_PATH)
    geometry_measures = len(reference.score.measures)

    print(f"file         {EXPORT}  ({EXPORT.stat().st_size / 1024:.0f} KB)")
    print(f"title        {title or '(none)'}")
    print(f"parts        {part_count}, took {part_name!r}")
    print()
    print("--- measure count, the load-bearing join ---")
    print(f"OpenCV geometry found     {geometry_measures} measures on this page")
    print(f"Audiveris exported        {len(measures)} measures")
    delta = len(measures) - geometry_measures
    print(f"difference                {delta:+d}")
    print()

    signatures = Counter(
        (m.beats_in_measure, m.beat_value) for m in measures if m.beats_in_measure
    )
    keys = Counter(m.key_fifths for m in measures)
    print("--- what it read ---")
    print(f"notes and rests           {sum(len(m.notes) for m in measures)}")
    print(f"measures with no notes    {sum(1 for m in measures if not m.notes)}")
    print(f"time signatures in force  {dict(signatures)}")
    print(f"key signatures in force   {dict(keys)}")
    slurred = sum(1 for m in measures for n in m.notes if n.slur != "none")
    print(f"slurred notes             {slurred}")
    print()

    print("--- Chordially's own gate: do the durations sum to the meter? ---")
    verdicts = Counter()
    failures: list[tuple[int, str, str]] = []
    for index, measure in enumerate(measures, start=1):
        verdict = validate_measure(measure, measure.beats_in_measure, measure.beat_value)
        if verdict.non_musical:
            verdicts["no notes"] += 1
        elif verdict.ok and verdict.low_confidence:
            verdicts["passed, flagged"] += 1
        elif verdict.ok:
            verdicts["passed"] += 1
        else:
            verdicts["rejected"] += 1
            total = measure.total_duration
            expected = (
                Fraction(measure.beats_in_measure, measure.beat_value)
                if measure.beats_in_measure and measure.beat_value
                else None
            )
            failures.append((index, verdict.reason, f"{total} against {expected}"))

    for name, count in verdicts.most_common():
        print(f"  {name:<16} {count}")
    passed = verdicts["passed"] + verdicts["passed, flagged"]
    musical = len(measures) - verdicts["no notes"]
    if musical:
        print(f"  {passed} of {musical} measures carrying notes validate ({passed / musical:.0%})")

    if failures:
        print("\n  rejected measures:")
        for index, reason, sums in failures[:15]:
            print(f"    #{index:<4} {reason}  [{sums}]")

    print()
    print("--- not measured here ---")
    print("Pitch. Nothing in this script or in validate_measure checks a pitch;")
    print("the gate is the violin's range plus the duration sum. Any claim about")
    print("pitch accuracy needs a by-eye comparison against the scan, or B3.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
