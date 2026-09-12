"""Measure geometry from a scanned page, using classical computer vision.

This module answers the hardest question in docs/architecture.md: how actual
measure positions are obtained rather than estimated by a language model. It
never calls a model. It reads ink.

The pipeline exploits one fact about solo violin notation: there is exactly one
staff per system. That collapses system detection into staff detection and makes
barline grouping unambiguous.

    render -> binarize -> deskew -> staff lines -> staves -> barlines -> measures

Coordinate convention (also recorded in src/schemas/geometry.py):
    Normalized page coordinates. Origin is the TOP-LEFT of the rendered page.
    x and y are fractions of page width and height respectively, in [0, 1].
    A box is (x, y, w, h). Normalization means the browser can position overlays
    with percentages, so zoom and resize cannot desynchronize them from the
    image -- there is no transform math to get wrong.
"""

from __future__ import annotations

import dataclasses
import io
import math

import cv2
import numpy as np

# Rendering resolution for geometry. 200 is ample for finding staff lines and
# barlines and keeps the morphology fast.
RENDER_DPI = 200

# Rendering resolution for the crops sent to a vision model. Higher than the
# analysis DPI because beam counting is the accuracy bottleneck: at 200 DPI a
# single beam and a double beam are a few pixels apart and eighths get read as
# 16ths. Because measure boxes are stored in NORMALIZED coordinates, the same
# box crops correctly out of a render at any resolution -- geometry is computed
# once, cheaply, and reused against a sharper image at no extra analysis cost.
CROP_DPI = 400

# A staff line is a near-horizontal run of ink spanning much of the system.
# Expressed as a fraction of page width.
STAFF_LINE_MIN_WIDTH_FRAC = 0.30

# Five lines make a staff. Real scans lose or merge lines, so accept 4-6 and
# reconstruct spacing from the median gap.
STAFF_LINES_EXPECTED = 5

# A barline spans the staff vertically. Tolerance accounts for scan erosion at
# the top and bottom line.
BARLINE_MIN_HEIGHT_FRAC = 0.88

# How far above and below the staff to look for the protrusion that betrays a
# note stem, in staff spaces.
BARLINE_MARGIN_STAVESPACE = 1.2

# Maximum fraction of that margin band a true barline may fill. Kept above zero
# so a slur, a tie, or scan speckle crossing the margin does not veto a real
# barline.
BARLINE_MAX_PROTRUSION = 0.25

# How far to either side to look for the whitespace that surrounds a barline,
# in staff spaces.
BARLINE_ISOLATION_STAVESPACE = 0.75

# Maximum between-the-lines ink allowed in that neighbourhood. A notehead
# touching a stem greatly exceeds this; the air around a barline does not.
BARLINE_MAX_NEIGHBOUR_INK = 0.18

# Barlines are thin. Anything wider than this multiple of staff-line spacing is
# a beam group, a stem cluster, or smudge -- not a barline.
BARLINE_MAX_WIDTH_STAVESPACE = 0.90

# Two detected barlines closer than this (in staff spaces) are the same barline
# found twice, or a thick-thin final barline pair. Merge them.
BARLINE_MERGE_DIST_STAVESPACE = 1.6

# A measure narrower than this is a detection artifact, not a measure.
MEASURE_MIN_WIDTH_STAVESPACE = 2.5

# A measure narrower than this fraction of its own system's median measure
# width is a false split, and the barline that produced it is dropped.
MEASURE_MIN_WIDTH_MEDIAN_FRAC = 0.45

# Vertical room above and below the staff in a measure box, in staff spaces,
# before clamping to the neighbouring system. Ledger-line notes below the staff
# are the binding case.
BOX_MARGIN_STAVESPACE = 4.5


@dataclasses.dataclass(frozen=True)
class Box:
    """A rectangle in normalized page coordinates, origin top-left."""

    x: float
    y: float
    w: float
    h: float

    def as_pixels(self, page_w: int, page_h: int) -> tuple[int, int, int, int]:
        return (
            int(round(self.x * page_w)),
            int(round(self.y * page_h)),
            int(round(self.w * page_w)),
            int(round(self.h * page_h)),
        )


@dataclasses.dataclass(frozen=True)
class DetectedMeasure:
    system_index: int
    index_in_system: int
    box: Box


@dataclasses.dataclass(frozen=True)
class DetectedSystem:
    index: int
    box: Box
    staff_space_px: float
    measures: list[DetectedMeasure]


@dataclasses.dataclass(frozen=True)
class PageGeometry:
    """Everything downstream needs, with no dependency on how it was found."""

    width_px: int
    height_px: int
    render_dpi: int
    skew_deg: float
    systems: list[DetectedSystem]

    @property
    def measure_count(self) -> int:
        return sum(len(s.measures) for s in self.systems)


def render_page(pdf_path: str, page_index: int, dpi: int = RENDER_DPI) -> np.ndarray:
    """Render one PDF page to a grayscale array. Raises if the page is absent."""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        if not 0 <= page_index < doc.page_count:
            raise IndexError(
                f"page {page_index} out of range for {doc.page_count}-page document"
            )
        pix = doc[page_index].get_pixmap(dpi=dpi)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
    if pix.n >= 3:
        return cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
    return arr[:, :, 0].copy()


def load_image(data: bytes) -> np.ndarray:
    """Decode an uploaded PNG/JPEG to grayscale."""
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError("could not decode image data")
    return img


def binarize(gray: np.ndarray) -> np.ndarray:
    """Return a uint8 mask where 255 marks ink.

    Otsu handles the even lighting of a flatbed scan well. We invert because
    every morphological operation below is phrased in terms of ink being
    foreground.
    """
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return mask


def estimate_skew(mask: np.ndarray, max_deg: float = 2.0, step: float = 0.1) -> float:
    """Estimate page rotation by maximizing horizontal-projection sharpness.

    Staff lines are the strongest horizontal feature on the page. When the page
    is level, their ink concentrates into a few rows and the row-sum profile has
    high variance. Rotating away from level smears it. So we sweep small angles
    and keep the sharpest. This is cheap and, unlike Hough, cannot be misled by
    the long horizontal beams that fill this repertoire.
    """
    best_angle, best_score = 0.0, -1.0
    h, w = mask.shape
    # Downscale for speed; skew is a global property and survives decimation.
    small = cv2.resize(mask, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    n = int(round(max_deg / step))
    for i in range(-n, n + 1):
        angle = i * step
        if angle:
            m = cv2.getRotationMatrix2D(
                (small.shape[1] / 2, small.shape[0] / 2), angle, 1.0
            )
            rot = cv2.warpAffine(
                small, m, (small.shape[1], small.shape[0]), flags=cv2.INTER_NEAREST
            )
        else:
            rot = small
        profile = rot.sum(axis=1, dtype=np.float64)
        score = float(np.var(profile))
        if score > best_score:
            best_angle, best_score = angle, score
    return best_angle


def deskew(img: np.ndarray, angle_deg: float, border_value: int) -> np.ndarray:
    if abs(angle_deg) < 1e-6:
        return img
    h, w = img.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle_deg, 1.0)
    return cv2.warpAffine(
        img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=border_value
    )


def _find_staff_line_rows(mask: np.ndarray) -> list[int]:
    """Row indices whose ink spans enough width to be a staff line."""
    h, w = mask.shape
    # Keep only long horizontal runs. This erases noteheads, stems and text
    # while leaving staff lines (and, harmlessly, some beams).
    kernel_w = max(15, int(w * 0.05))
    horiz = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_w, 1))
    )
    row_ink = (horiz > 0).sum(axis=1)
    threshold = w * STAFF_LINE_MIN_WIDTH_FRAC
    return [y for y in range(h) if row_ink[y] >= threshold]


def _group_rows(rows: list[int], max_gap: int = 2) -> list[tuple[int, int]]:
    """Collapse adjacent row indices into (start, end) bands."""
    if not rows:
        return []
    bands: list[tuple[int, int]] = []
    start = prev = rows[0]
    for y in rows[1:]:
        if y - prev <= max_gap:
            prev = y
        else:
            bands.append((start, prev))
            start = prev = y
    bands.append((start, prev))
    return bands


def _group_bands_into_staves(bands: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    """Cluster line-bands into staves using the gap between consecutive lines.

    Within a staff, line spacing is nearly constant. Between staves the gap is
    several times larger. So we split wherever the gap jumps well above the
    running median.
    """
    if len(bands) < STAFF_LINES_EXPECTED:
        return []
    centers = [(a + b) / 2 for a, b in bands]
    gaps = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
    if not gaps:
        return []
    median_gap = float(np.median(gaps))
    # A between-staff gap is conspicuously larger than a within-staff gap.
    split_threshold = median_gap * 2.2

    staves: list[list[tuple[int, int]]] = []
    current = [bands[0]]
    for i, gap in enumerate(gaps):
        if gap > split_threshold:
            staves.append(current)
            current = [bands[i + 1]]
        else:
            current.append(bands[i + 1])
    staves.append(current)

    # A staff has five lines. Tolerate four (a faint line lost to thresholding)
    # or six (a line split in two by scan noise). Anything else is not a staff:
    # stray text underlines and page furniture land here and are dropped.
    return [s for s in staves if 4 <= len(s) <= 6]


def _staff_extent(mask: np.ndarray, line_bands: list[tuple[int, int]]) -> tuple[int, int]:
    """Leftmost and rightmost column occupied by this staff's lines.

    Needed because this engraving draws no barline where a system begins.
    Without it the clef, key signature, time signature and the whole first
    measure fall outside every detected box.
    """
    rows = np.concatenate([np.arange(a, b + 1) for a, b in line_bands])
    strip = mask[rows, :]
    # A staff-line column is inked on most of the lines that pass through it.
    coverage = (strip > 0).sum(axis=0) / strip.shape[0]
    cols = np.flatnonzero(coverage >= 0.6)
    if cols.size == 0:
        return 0, mask.shape[1] - 1
    return int(cols[0]), int(cols[-1])


def _find_barlines(
    mask: np.ndarray,
    top: int,
    bottom: int,
    staff_space: float,
    line_bands: list[tuple[int, int]],
) -> list[int]:
    """Column indices of barlines within one staff band.

    Height alone does not separate barlines from note stems. In this repertoire
    stems routinely run the full staff height, so a height test finds both and
    over-segments every system by roughly a factor of two.

    The discriminator that does work is what happens OUTSIDE the staff. A stem
    exists to reach a beam or flag, so it protrudes past the staff lines. A
    barline terminates exactly at the top and bottom staff line. So we require a
    tall continuous run inside the staff AND near-absence of ink in a margin
    band immediately above and below it.
    """
    band = mask[top : bottom + 1, :]
    band_h = band.shape[0]
    if band_h <= 2:
        return []

    # Keep only ink that forms a tall continuous vertical run.
    kernel_h = max(3, int(band_h * BARLINE_MIN_HEIGHT_FRAC))
    vert = cv2.morphologyEx(
        band, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_h))
    )

    col_ink = (vert > 0).sum(axis=0)
    required = band_h * BARLINE_MIN_HEIGHT_FRAC
    tall_enough = col_ink >= required

    # The protrusion test. Margins are measured just outside the staff; a
    # barline leaves them clean, a stem does not.
    margin_px = max(3, int(round(staff_space * BARLINE_MARGIN_STAVESPACE)))
    page_h = mask.shape[0]
    above = mask[max(0, top - margin_px) : top, :]
    below = mask[bottom + 1 : min(page_h, bottom + 1 + margin_px), :]

    def _protrusion(strip: np.ndarray) -> np.ndarray:
        if strip.size == 0:
            return np.zeros(mask.shape[1], dtype=np.float64)
        return (strip > 0).sum(axis=0) / strip.shape[0]

    clean_above = _protrusion(above) <= BARLINE_MAX_PROTRUSION
    clean_below = _protrusion(below) <= BARLINE_MAX_PROTRUSION

    # The isolation test. Engravers leave air on both sides of a barline; a note
    # stem has a notehead welded to it. Measuring ink on the rows BETWEEN staff
    # lines (the staff lines themselves are inked in every column and would
    # drown the signal) separates the two cleanly -- including the stems whose
    # beams sit inside the staff, which the protrusion test above cannot see.
    staff_rows = np.arange(top, bottom + 1)
    line_rows = np.concatenate([np.arange(a, b + 1) for a, b in line_bands])
    between_rows = np.setdiff1d(staff_rows, line_rows, assume_unique=False)
    if between_rows.size:
        between = (mask[between_rows, :] > 0).sum(axis=0) / between_rows.size
    else:
        between = np.zeros(mask.shape[1], dtype=np.float64)

    gap = max(2, int(round(staff_space * BARLINE_ISOLATION_STAVESPACE)))
    # Neighbourhood ink, ignoring the candidate column and its immediate
    # neighbours so a thick barline does not veto itself.
    pad = np.pad(between, gap, mode="constant")
    width = mask.shape[1]
    left_ink = np.empty(width)
    right_ink = np.empty(width)
    for i in range(width):
        left_ink[i] = pad[i : i + gap - 1].max(initial=0.0)
        right_ink[i] = pad[i + gap + 2 : i + 2 * gap + 1].max(initial=0.0)
    isolated = (left_ink <= BARLINE_MAX_NEIGHBOUR_INK) | (
        right_ink <= BARLINE_MAX_NEIGHBOUR_INK
    )

    candidate_cols = np.flatnonzero(
        tall_enough & clean_above & clean_below & isolated
    )
    if candidate_cols.size == 0:
        return []

    # Collapse runs of adjacent columns into single barlines, rejecting any run
    # too wide to be a barline.
    max_width = max(2.0, staff_space * BARLINE_MAX_WIDTH_STAVESPACE)
    centers: list[int] = []
    run_start = prev = int(candidate_cols[0])
    for c in candidate_cols[1:]:
        c = int(c)
        if c - prev <= 1:
            prev = c
            continue
        if (prev - run_start + 1) <= max_width:
            centers.append((run_start + prev) // 2)
        run_start = prev = c
    if (prev - run_start + 1) <= max_width:
        centers.append((run_start + prev) // 2)

    # Merge near-duplicates: the thick+thin pair of a final barline, or one
    # barline detected as two because of a scan gap.
    merge_dist = staff_space * BARLINE_MERGE_DIST_STAVESPACE
    merged: list[int] = []
    for c in centers:
        if merged and (c - merged[-1]) < merge_dist:
            merged[-1] = (merged[-1] + c) // 2
        else:
            merged.append(c)
    return merged


def _drop_spurious_barlines(barlines: list[int]) -> list[int]:
    """Remove barlines that split one real measure into slivers.

    Self-calibrating on purpose: engravers space measures within a system
    roughly in proportion to their note density, so real measures in one system
    have comparable widths. A gap far below that system's median is therefore a
    false split rather than a very short measure, and the barline that created
    it can be dropped. Using the median of the system in hand avoids hard-coding
    any assumption about note values, meter or engraving size.
    """
    if len(barlines) < 3:
        return barlines
    bl = list(barlines)
    while len(bl) > 2:
        gaps = [bl[i + 1] - bl[i] for i in range(len(bl) - 1)]
        median_gap = float(np.median(gaps))
        i = int(np.argmin(gaps))
        if gaps[i] >= median_gap * MEASURE_MIN_WIDTH_MEDIAN_FRAC:
            break
        if i == 0:
            drop = 1  # keep the staff's left edge
        elif i == len(gaps) - 1:
            drop = len(bl) - 2  # keep the staff's right edge
        else:
            # Drop whichever of the two bounding barlines leaves the merged
            # measure closest to this system's typical width.
            merge_left = gaps[i - 1] + gaps[i]
            merge_right = gaps[i] + gaps[i + 1]
            drop = i if abs(merge_left - median_gap) <= abs(merge_right - median_gap) else i + 1
        bl.pop(drop)
    return bl


def analyze_page(gray: np.ndarray, render_dpi: int = RENDER_DPI) -> PageGeometry:
    """Full geometry pipeline for one already-rendered page."""
    mask = binarize(gray)
    skew = estimate_skew(mask)
    if abs(skew) > 1e-6:
        gray = deskew(gray, skew, border_value=255)
        mask = binarize(gray)

    h, w = mask.shape
    line_rows = _find_staff_line_rows(mask)
    bands = _group_rows(line_rows)
    staves = _group_bands_into_staves(bands)

    systems: list[DetectedSystem] = []
    for si, staff in enumerate(staves):
        top = staff[0][0]
        bottom = staff[-1][1]
        centers = [(a + b) / 2 for a, b in staff]
        spaces = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
        staff_space = float(np.median(spaces)) if spaces else 8.0

        staff_left, staff_right = _staff_extent(mask, staff)
        barlines = _find_barlines(mask, top, bottom, staff_space, staff)

        # This engraving omits the barline at a system's start, and sometimes at
        # its end. Supply both from the staff's own extent so the clef, key and
        # time signature -- and the whole first measure -- are not discarded.
        edge_tol = staff_space * MEASURE_MIN_WIDTH_STAVESPACE
        if not barlines or (barlines[0] - staff_left) > edge_tol:
            barlines.insert(0, staff_left)
        if not barlines or (staff_right - barlines[-1]) > edge_tol:
            barlines.append(staff_right)

        barlines = _drop_spurious_barlines(barlines)

        if len(barlines) < 2:
            # A staff with no usable barlines yields no measures. It is recorded
            # as an empty system rather than silently dropped, so downstream can
            # show it as unrecognized instead of pretending it is not there.
            systems.append(
                DetectedSystem(
                    index=si,
                    box=Box(0.0, top / h, 1.0, (bottom - top) / h),
                    staff_space_px=staff_space,
                    measures=[],
                )
            )
            continue

        # Vertical extent of a measure box: the staff plus room for ledger
        # lines, beams and fingering digits, which in this repertoire sit mostly
        # BELOW the staff on the G and D strings. A margin generous enough to
        # catch them would bleed into the neighbouring system, so it is clamped
        # to halfway toward whichever staff is adjacent. That takes all the
        # context actually available without ever crossing into other notation.
        want = staff_space * BOX_MARGIN_STAVESPACE
        prev_bottom = staves[si - 1][-1][1] if si > 0 else None
        next_top = staves[si + 1][0][0] if si + 1 < len(staves) else None
        top_limit = (top + prev_bottom) / 2 if prev_bottom is not None else 0.0
        bottom_limit = (bottom + next_top) / 2 if next_top is not None else float(h - 1)
        box_top = max(0.0, top_limit, top - want)
        box_bottom = min(float(h - 1), bottom_limit, bottom + want)

        min_width = staff_space * MEASURE_MIN_WIDTH_STAVESPACE
        measures: list[DetectedMeasure] = []
        for left, right in zip(barlines, barlines[1:]):
            if (right - left) < min_width:
                continue
            measures.append(
                DetectedMeasure(
                    system_index=si,
                    index_in_system=len(measures),
                    box=Box(
                        x=left / w,
                        y=box_top / h,
                        w=(right - left) / w,
                        h=(box_bottom - box_top) / h,
                    ),
                )
            )

        systems.append(
            DetectedSystem(
                index=si,
                box=Box(
                    x=barlines[0] / w,
                    y=box_top / h,
                    w=(barlines[-1] - barlines[0]) / w,
                    h=(box_bottom - box_top) / h,
                ),
                staff_space_px=staff_space,
                measures=measures,
            )
        )

    return PageGeometry(
        width_px=w,
        height_px=h,
        render_dpi=render_dpi,
        skew_deg=skew,
        systems=systems,
    )


@dataclasses.dataclass(frozen=True)
class Chunk:
    """A run of consecutive measures within one system, cropped together."""

    system_index: int
    start_measure: int
    count: int
    box: Box


def system_chunks(system: DetectedSystem, max_measures: int = 2) -> list[Chunk]:
    """Split a system into crops that a vision model can actually read.

    Two constraints pull against each other. Pitch is judged against the five
    staff lines, so the crop must show the whole staff -- which rules out
    isolated measure crops. But a whole system is an extreme strip (here roughly
    8:1), and image downscaling is driven by the LONG edge, so a wide strip is
    shrunk until the staff is only a hundred pixels tall and pitch becomes
    guesswork again. Rendering at a higher DPI does not help: the resize happens
    afterwards.

    Chunking a few measures at a time satisfies both. The full staff height is
    present, and the aspect ratio stays modest enough that the crop is not
    downscaled at all.
    """
    chunks: list[Chunk] = []
    measures = system.measures
    for start in range(0, len(measures), max_measures):
        group = measures[start : start + max_measures]
        if not group:
            continue
        left = group[0].box.x
        right = group[-1].box.x + group[-1].box.w
        chunks.append(
            Chunk(
                system_index=system.index,
                start_measure=start,
                count=len(group),
                box=Box(x=left, y=system.box.y, w=right - left, h=system.box.h),
            )
        )
    return chunks


def crop(gray: np.ndarray, box: Box, pad_frac: float = 0.01) -> np.ndarray:
    """Crop a normalized box out of a page, with a little horizontal padding.

    The padding matters: a measure's first notehead sits just right of the
    barline and its last beam can overhang slightly. Cropping flush to the
    detected barlines can clip both.
    """
    h, w = gray.shape
    pad = int(round(w * pad_frac))
    x0 = max(0, int(round(box.x * w)) - pad)
    x1 = min(w, int(round((box.x + box.w) * w)) + pad)
    y0 = max(0, int(round(box.y * h)))
    y1 = min(h, int(round((box.y + box.h) * h)))
    return gray[y0:y1, x0:x1]


def encode_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return buf.tobytes()


def annotate(gray: np.ndarray, geom: PageGeometry) -> np.ndarray:
    """Draw detected systems and measures onto a copy, for visual verification.

    Used by the C1 spike and by tests. Not used at runtime.
    """
    out = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    h, w = gray.shape
    for system in geom.systems:
        sx, sy, sw, sh = system.box.as_pixels(w, h)
        cv2.rectangle(out, (sx, sy), (sx + sw, sy + sh), (255, 120, 0), 2)
        for m in system.measures:
            mx, my, mw, mh = m.box.as_pixels(w, h)
            cv2.rectangle(out, (mx, my), (mx + mw, my + mh), (0, 0, 255), 2)
            cv2.putText(
                out,
                f"{system.index}.{m.index_in_system}",
                (mx + 4, my + 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 140, 0),
                2,
            )
    return out
