"""Does the difficulty ribbon actually stay off the notation?

The ribbon used to be placed at a fixed fraction of the measure box, on the
reasoning that the box's lowest sliver was the whitespace between systems. It was
not: on the fixture page every one of the eleven systems carried notation inside
that band, up to 8,422 dark pixels on one of them, because stems, beams and
fingering digits reach three to four staff spaces below the bottom line while the
box reaches only halfway to the next staff.

So these tests do not check a constant. They count ink inside the rectangle the
code actually emits, against the page image the browser actually renders. A
placement claim that cannot survive being measured is the bug this file exists to
catch.

"Blank" means no row carrying more ink than `RIBBON_QUIET_INK_FRAC` of the
staff's width -- about six pixels across a 3,000-pixel staff. Demanding literally
zero would let one speck of scanner dust veto a gutter that is plainly empty, and
the fixture is a real scan with real dust.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from src.features.score_viewer.view_model import (
    RIBBON_HEIGHT_FRAC,
    RIBBON_INSET_FRAC,
    ribbon_band_rows,
)
from src.schemas.analysis import AnalysisBundle
from src.schemas.geometry import Region
from src.schemas.score import System
from src.server.analysis.example import EXAMPLE_PATH
from src.server.recognition.cv_geometry import (
    RIBBON_CLEARANCE_STAVESPACE,
    RIBBON_QUIET_INK_FRAC,
    ribbon_band,
)

PAGE_IMAGE = "fixtures/pages/wohlfahrt-p3.png"

# Ink darker than this is notation or dust; lighter is paper.
INK_THRESHOLD = 160


@pytest.fixture(scope="module")
def bundle() -> AnalysisBundle:
    return AnalysisBundle.load_path(EXAMPLE_PATH)


@pytest.fixture(scope="module")
def ink() -> np.ndarray:
    gray = cv2.imread(PAGE_IMAGE, cv2.IMREAD_GRAYSCALE)
    assert gray is not None, f"{PAGE_IMAGE} must be readable"
    return gray < INK_THRESHOLD


def band_ink(ink: np.ndarray, region: Region) -> tuple[int, int, int]:
    """(total ink, worst row's ink, band width) inside a page-relative region."""
    height, width = ink.shape
    top = int(round(region.y * height))
    bottom = int(round((region.y + region.h) * height))
    left = int(round(region.x * width))
    right = int(round((region.x + region.w) * width))
    band = ink[top:bottom, left:right]
    if band.size == 0:
        return 0, 0, max(1, right - left)
    rows = band.sum(axis=1)
    return int(band.sum()), int(rows.max()), max(1, right - left)


# --------------------------------------------------------------------------
# Measured against the real page
# --------------------------------------------------------------------------


def test_every_system_carries_a_measured_band(bundle):
    """A scan has pixels, so "unmeasured" is not an acceptable answer for one."""
    for system in bundle.score.systems:
        assert system.ribbon_region is not None, system.id
        assert system.ribbon_placement in ("clear", "crowded"), system.id


def test_a_band_called_clear_is_empty_where_it_is_drawn(bundle, ink):
    """The load-bearing test: measure the emitted rectangle, do not trust the code."""
    checked = 0
    for system in bundle.score.systems:
        if system.ribbon_placement != "clear":
            continue
        total, worst_row, width = band_ink(ink, system.ribbon_region)
        budget = max(1, round(width * RIBBON_QUIET_INK_FRAC))
        assert worst_row <= budget * 2, (
            f"{system.id}: a row inside its 'clear' band carries {worst_row} ink "
            f"pixels across {width}, which is notation, not dust"
        )
        assert total <= width, f"{system.id}: {total} ink pixels inside a clear band"
        checked += 1
    assert checked >= 10, "the fixture page should have clear bands to check"


def test_notation_inside_a_band_is_reported_as_crowded(bundle, ink):
    """The invariant that makes the flag worth having, stated as an implication.

    Any band carrying real notation must say so. This holds on any page rather
    than asserting how many crowded systems this particular one happens to have.
    """
    for system in bundle.score.systems:
        total, worst_row, width = band_ink(ink, system.ribbon_region)
        if worst_row > width * 0.05:
            assert system.ribbon_placement == "crowded", (
                f"{system.id} has {worst_row} ink pixels in one row of its band "
                "and is not reported as crowded"
            )


def old_constant_band(system) -> Region:
    """Where the ribbon used to be drawn, before the band was measured."""
    return Region(
        page_index=system.region.page_index,
        x=system.region.x,
        y=system.region.y
        + system.region.h * (1.0 - RIBBON_INSET_FRAC - RIBBON_HEIGHT_FRAC),
        w=system.region.w,
        h=system.region.h * RIBBON_HEIGHT_FRAC,
    )


def test_the_measured_band_covers_far_less_notation_than_the_old_constant(bundle, ink):
    """The regression this task exists to prevent, in one number.

    Compared only across the systems where a gutter was found, because the
    crowded one has nowhere better to be -- that is what its flag says, and
    averaging it in here would hide the improvement behind the one case the
    measurement cannot fix.
    """
    measured = old = 0
    for system in bundle.score.systems:
        if system.ribbon_placement != "clear":
            continue
        measured += band_ink(ink, system.ribbon_region)[0]
        old += band_ink(ink, old_constant_band(system))[0]

    assert old > 20_000, "the old placement really did cover this much ink"
    assert measured * 20 < old, (
        f"measured bands cover {measured} ink pixels against the old {old}; "
        "the fix is not doing enough to be worth the schema change"
    )


def test_the_crowded_system_was_not_made_worse(bundle, ink):
    """A system with no gutter keeps a band no larger than the old one covered.

    "Nowhere to put it" must not become "put it somewhere worse."
    """
    for system in bundle.score.systems:
        if system.ribbon_placement != "crowded":
            continue
        measured = band_ink(ink, system.ribbon_region)[0]
        old = band_ink(ink, old_constant_band(system))[0]
        assert measured <= old, f"{system.id}: {measured} ink pixels against {old} before"


def test_a_band_stays_between_its_own_staff_and_the_next(bundle):
    """Attached to the system it describes, and never on top of the next one."""
    systems = sorted(bundle.score.systems, key=lambda s: s.index)
    for index, system in enumerate(systems):
        band = system.ribbon_region
        assert band.y > system.region.y, f"{system.id}: band is above its own staff"
        assert band.y + band.h <= 1.0, f"{system.id}: band runs off the page"
        if index + 1 < len(systems):
            following = systems[index + 1].ribbon_region
            assert band.y + band.h <= following.y, (
                f"{system.id}: its band overlaps the next system's band"
            )


def test_the_band_is_a_page_fraction_not_a_pixel_count(bundle):
    """Percentages are what make the overlay survive zoom; pixels would not."""
    for system in bundle.score.systems:
        band = system.ribbon_region
        assert 0.0 <= band.y <= 1.0 and 0.0 < band.h < 0.2, system.id


# --------------------------------------------------------------------------
# The placement rule itself, on constructed masks
# --------------------------------------------------------------------------


def blank_mask(rows: int = 400, cols: int = 1000) -> np.ndarray:
    return np.zeros((rows, cols), dtype=np.uint8)


def find_band(mask: np.ndarray, staff_bottom: int = 100, staff_space: float = 20.0):
    return ribbon_band(
        mask,
        staff_bottom=staff_bottom,
        search_limit=mask.shape[0] - staff_space * RIBBON_CLEARANCE_STAVESPACE,
        staff_left=0,
        staff_right=mask.shape[1] - 1,
        staff_space=staff_space,
    )


def test_an_empty_gutter_gives_a_clear_band_below_the_staff():
    top, height, is_clear = find_band(blank_mask())
    assert is_clear
    assert top > 100, "the band must sit below the staff it belongs to"
    assert height > 0


def test_the_nearest_usable_gutter_wins_over_a_larger_distant_one():
    """A band far from its staff reads as belonging to nothing.

    The widest blank run under the fixture's last system is the footer margin,
    eighty pixels below the music, which is why this rule is 'first' not 'widest'.
    """
    mask = blank_mask()
    mask[125:200, :] = 255  # a wall of ink, leaving a narrow gutter above it
    top, height, is_clear = find_band(mask)
    assert is_clear
    assert top < 125, f"band at {top} skipped the gutter at 106-125"
    assert top + height <= 125


def test_a_gutter_too_short_to_hold_a_band_is_skipped():
    mask = blank_mask()
    mask[112:200, :] = 255  # only six blank rows under the staff; minimum is eleven
    top, height, is_clear = find_band(mask)
    assert is_clear
    assert top >= 200, f"band at {top} was squeezed into a six-row gutter"


def test_a_page_with_no_gutter_at_all_says_so():
    """Dense engraving exists. Reporting it beats silently covering the notes."""
    mask = blank_mask()
    mask[100:, :] = 255
    top, height, is_clear = find_band(mask)
    assert is_clear is False
    assert top >= 100 and height > 0
    assert top + height <= mask.shape[0]


def test_a_dust_speck_does_not_veto_a_gutter():
    mask = blank_mask()
    mask[130, 500:503] = 255  # three pixels across a thousand
    _, _, is_clear = find_band(mask)
    assert is_clear


# --------------------------------------------------------------------------
# The fallback, for pages with no pixels to measure
# --------------------------------------------------------------------------


def test_an_unmeasured_system_falls_back_to_the_bottom_of_its_box():
    """The MusicXML path serves an SVG, so there is no ink to profile."""
    system = System(
        id="s",
        page_index=0,
        index=0,
        region=Region(page_index=0, x=0.1, y=0.2, w=0.8, h=0.1),
    )
    assert system.ribbon_placement == "unmeasured"
    top, height = ribbon_band_rows(system)
    assert height == pytest.approx(0.1 * RIBBON_HEIGHT_FRAC)
    assert top == pytest.approx(0.2 + 0.1 * (1.0 - RIBBON_INSET_FRAC - RIBBON_HEIGHT_FRAC))


def test_a_measured_system_uses_what_was_measured():
    system = System(
        id="s",
        page_index=0,
        index=0,
        region=Region(page_index=0, x=0.1, y=0.2, w=0.8, h=0.1),
        ribbon_region=Region(page_index=0, x=0.1, y=0.34, w=0.8, h=0.006),
        ribbon_placement="clear",
    )
    assert ribbon_band_rows(system) == (0.34, 0.006)
