"""Measure the committed example's ribbon bands from its own page image.

`System.ribbon_region` arrives with B1, and the example fixture predates it. A
scan analyzed today gets its bands from `analyze_page`; this script gives the
committed fixture the same treatment without re-running recognition, because the
band is a fact about pixels and needs no API key.

    python scripts/measure_example_ribbon_bands.py

The staves are re-detected on the committed PNG and matched to the fixture's
systems in order. The match is asserted, not assumed: if staff detection returns
a different count than the fixture has systems, the script writes nothing and
says so. Nothing else in the fixture is touched -- not a measure box, not a
rating, not a note.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402

from src.schemas.analysis import AnalysisBundle  # noqa: E402
from src.schemas.geometry import Region  # noqa: E402
from src.server.analysis.example import EXAMPLE_PATH  # noqa: E402
from src.server.recognition import cv_geometry as cg  # noqa: E402

PAGE_IMAGE = Path("fixtures/pages/wohlfahrt-p3.png")


def main() -> int:
    bundle = AnalysisBundle.load_path(EXAMPLE_PATH)
    gray = cv2.imread(str(PAGE_IMAGE), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        print(f"could not read {PAGE_IMAGE}")
        return 1

    mask = cg.binarize(gray)
    height, width = mask.shape
    staves = cg._group_bands_into_staves(cg._group_rows(cg._find_staff_line_rows(mask)))

    systems = sorted(bundle.score.systems, key=lambda s: s.index)
    if len(staves) != len(systems):
        print(
            f"detected {len(staves)} staves but the fixture has {len(systems)} "
            "systems; refusing to guess which is which"
        )
        return 1

    clear = 0
    for system, staff in zip(systems, staves):
        staff_bottom = staff[-1][1]
        centers = [(a + b) / 2 for a, b in staff]
        spaces = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
        staff_space = float(sum(spaces) / len(spaces)) if spaces else 8.0
        staff_left, staff_right = cg._staff_extent(mask, staff)

        index = staves.index(staff)
        next_top = staves[index + 1][0][0] if index + 1 < len(staves) else height
        top, band_height, is_clear = cg.ribbon_band(
            mask,
            staff_bottom=staff_bottom,
            search_limit=next_top - staff_space * cg.RIBBON_CLEARANCE_STAVESPACE,
            staff_left=staff_left,
            staff_right=staff_right,
            staff_space=staff_space,
        )

        system.ribbon_region = Region(
            page_index=system.region.page_index,
            x=system.region.x,
            y=top / height,
            w=system.region.w,
            h=band_height / height,
        )
        system.ribbon_placement = "clear" if is_clear else "crowded"
        clear += int(is_clear)
        print(
            f"{system.id}: rows {top:.0f}-{top + band_height:.0f} "
            f"({band_height:.0f}px) {system.ribbon_placement}"
        )

    print(f"{clear} of {len(systems)} systems have a clear band")
    EXAMPLE_PATH.write_text(
        json.dumps(bundle.model_dump(mode="json"), indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {EXAMPLE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
