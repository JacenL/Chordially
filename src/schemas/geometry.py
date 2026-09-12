"""Coordinate conventions, stated once and depended on everywhere.

    Normalized page coordinates. Origin is the TOP-LEFT of the rendered page.
    x and y are fractions of page width and height, in [0, 1].
    A Region is (x, y, w, h).

Normalization is what makes annotation robust. The browser positions overlays
as percentages of the page image, so zooming, resizing, or serving the page at a
different render resolution cannot move an overlay off its measure -- there is
no transform to recompute and therefore none to get wrong.

It also means geometry computed cheaply at one resolution stays valid against a
render at any other, which is how measure boxes found at 200 DPI are used to
crop from a 400 DPI image.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Region(BaseModel):
    """A rectangle in normalized page coordinates."""

    model_config = {"frozen": True}

    page_index: int = Field(default=0, ge=0)
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def to_percent_style(self) -> str:
        """CSS for an absolutely positioned overlay inside the page container."""
        return (
            f"left:{self.x * 100:.4f}%;top:{self.y * 100:.4f}%;"
            f"width:{self.w * 100:.4f}%;height:{self.h * 100:.4f}%"
        )


class RegionFragments(BaseModel):
    """One logical span that may occupy several rectangles.

    A phrase crossing a system or page break is not one box. Modelling it as a
    list of fragments is what keeps a phrase outline from becoming a rectangle
    that swallows unrelated notation between the two ends.
    """

    fragments: list[Region] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.fragments
