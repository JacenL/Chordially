"""Difficulty-to-colour mapping, exactly as specified in docs/design.md.

The progression is light green -> yellow -> orange -> red -> near-black, evenly
spaced at 2.5 points. Values between anchors are interpolated linearly in sRGB.
Linear sRGB interpolation is chosen over a perceptual space deliberately: the
spec pins exact hex values, and any perceptual blend would fail to reproduce
them between anchors. The anchors themselves are reproduced exactly.

The anchors sit on a 2.5 grid while the categories cut at 2.0, so a category
spans part of two ramps rather than exactly one. That is deliberate: the
progression is the one the product asked for, and bending it onto the category
grid would have meant inventing a sixth colour nobody specified.

The scale is absolute and identical for every score. A beginner etude occupies
the light-green end and stays there; nothing is stretched to make one piece use
the whole ribbon.

Category labels come from docs/product-spec.md and use half-open intervals, so
a score of exactly 2.0 is "Advanced Beginner", not "Beginner-friendly". The
final interval is closed so 10.0 has a home.

Unrated is not a colour on this scale. It gets neutral hatching, because the
spec requires unreadable content to stay visually distinct from both easy and
difficult content.
"""

from __future__ import annotations

ANCHORS: list[tuple[float, str]] = [
    (0.0, "#A5D6A0"),  # light green
    (2.5, "#E5C229"),  # yellow
    (5.0, "#EF8A24"),  # orange
    (7.5, "#D73A3A"),  # red
    (10.0, "#1A1012"),  # near-black
]

CATEGORIES: list[tuple[float, float, str]] = [
    (0.0, 2.0, "Beginner-friendly"),
    (2.0, 4.0, "Advanced Beginner"),
    (4.0, 6.0, "Competent level"),
    (6.0, 8.0, "Expert level"),
    (8.0, 10.0, "Extremely hard"),
]

UNRATED_LABEL = "Needs review"
UNRATED_COLOR = "#B9B2A6"


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(c))) for c in rgb))


def color_for(score: float | None) -> str:
    """Colour for a rating. Unrated returns the neutral colour, never green."""
    if score is None:
        return UNRATED_COLOR
    s = max(0.0, min(10.0, float(score)))

    for i in range(len(ANCHORS) - 1):
        lo_v, lo_hex = ANCHORS[i]
        hi_v, hi_hex = ANCHORS[i + 1]
        if lo_v <= s <= hi_v:
            if hi_v == lo_v:
                return lo_hex
            t = (s - lo_v) / (hi_v - lo_v)
            lo_rgb, hi_rgb = _hex_to_rgb(lo_hex), _hex_to_rgb(hi_hex)
            return _rgb_to_hex(tuple(lo + (hi - lo) * t for lo, hi in zip(lo_rgb, hi_rgb)))
    return ANCHORS[-1][1]


def category_for(score: float | None) -> str:
    """Category label. Intervals are half-open except the last, which is closed."""
    if score is None:
        return UNRATED_LABEL
    s = max(0.0, min(10.0, float(score)))
    for lo, hi, label in CATEGORIES:
        if lo <= s < hi:
            return label
    return CATEGORIES[-1][2]


def format_score(score: float | None) -> str:
    """Always exactly one decimal place, or the unrated label."""
    return UNRATED_LABEL if score is None else f"{score:.1f}"


def legend() -> list[dict]:
    """The full scale, for a legend that shows every category.

    Rendered regardless of what the loaded score actually spans. A beginner
    etude will not reach maroon, and the honest response is to show the scale
    it sits on rather than to inflate a rating so the ribbon looks richer.
    """
    entries = [
        {
            "label": label,
            "range": f"{lo:.1f}–{hi:.1f}",
            "color": color_for((lo + hi) / 2),
            "from": lo,
            "to": hi,
        }
        for lo, hi, label in CATEGORIES
    ]
    entries.append(
        {"label": UNRATED_LABEL, "range": "—", "color": UNRATED_COLOR, "from": None, "to": None}
    )
    return entries
