# PracticeMap — interface specification

## Visual direction
Build a focused music-study workspace: warm off-white background, dark readable typography, generous space, restrained controls, and crisp score rendering. Use color primarily to communicate difficulty and selection. The product is a score-centered practice tool, not a chat transcript or analytics dashboard.

## Layout
- Compact header: product name, score title, upload/new score, settings.
- Main workspace: score occupies approximately two-thirds of desktop width; sticky practice sidebar occupies the remainder.
- Above the score: zoom, page navigation if needed, phrase toggle, and visible difficulty legend.
- On narrow screens: score first; selecting a region opens an accessible expandable panel or sheet.
- Initial state: upload target and 'Try example score,' plus a short explanation of the outcome.

## Score annotation layers
1. Original notation, always legible. Nothing above it may wash it out.
2. Practice-section outlines with the section's name and one-decimal rating. One
   fragment per staff system the section touches, all sharing its identity,
   rating and color. This is the primary annotation layer.
3. A continuous thin difficulty ribbon directly below each system, banded by
   practice section, with no decorative gaps.
4. Phrase outlines and trouble-spot outlines as secondary detail, off by default
   and available from a toggle.
5. A clear selected-region outline independent of the difficulty color.
6. Distinct neutral hatching for unrecognized regions.

**The colored unit is the practice section, not the measure.** A section is one
or more adjacent phrases whose technical demands and difficulty are similar; it
is defined in `src/features/segmentation/sections.py` and summarized below. One
section carries one displayed rating and one color across its whole extent.

Measure-level ratings remain the input to that number and remain visible on
hover, but they must not drive a measure-by-measure heat map: a band of color
per measure is a picture of the rubric's rounding rather than of the music.

Start from musical boundaries and the existing phrase segmentation. Split where
there is a real musical or technical change — a printed key or meter change, a
step in difficulty, a change in the dominant demand. Do not split for a small
rating change, and do not merge unrelated musical ideas just because their
numbers match. Repeated material that is not adjacent stays separately
clickable, while identical material under identical conditions must rate the
same.

The one thing that interrupts a section's band is a measure recognition could
not read: it keeps neutral hatching inside the band, because unknown material
must never be handed a difficulty color.

Use documented interpolation between color anchors for numeric values, and keep
adjoining bands flush. 'Continuous' means a connected score-aligned ribbon, not
a gradient stretched arbitrarily across an entire page.

Color anchors. The progression is light green -> green -> yellow -> orange ->
red -> maroon, one anchor every two points, so each category spans exactly one
interval between anchors:

| Score | Color | Hex | Category reached at this anchor |
|---|---|---|---|
| 0.0 | Light green | #A5D6A0 | Beginner-friendly |
| 2.0 | Green | #238B45 | Advanced Beginner |
| 4.0 | Yellow | #E5C229 | Competent level |
| 6.0 | Orange | #EF8A24 | Expert level |
| 8.0 | Red | #D73A3A | Extremely, extremely hard |
| 10.0 | Maroon | #800020 | — |

The scale is absolute and identical for every score. Do not rescale a piece so
its ribbon uses the whole range: a beginner method page is supposed to stay at
the light-green end, and stretching it would destroy the only property that lets
two different uploads be compared.

Category text follows the intervals in product-spec.md. Always provide numeric values and labels in addition to color. Place text on a contrasting surface rather than directly on a potentially low-contrast ribbon color.

## Selection behavior
- Hover/focus: show measure label, its own one-decimal estimate, brief difficulty
  factors, and which passage a click would select.
- Click/keyboard activation anywhere inside a section — a measure, the section
  outline, or its ribbon band — selects **the whole section**. Every fragment of
  it is highlighted, on every system it touches, and the sidebar, the passage
  list, the selected region, the title, the range, the rating and the advice all
  move together.
- Two clicks inside one section produce the same selection and the same
  guidance. A local trouble spot is secondary guidance shown inside the section;
  it never intercepts a click on the score.
- Phrases and trouble spots stay selectable from the passage list and from their
  own outlines. Selecting one keeps its section in the breadcrumb.
- Selecting a sidebar passage scrolls its score region into view without losing selection.
- A section or phrase spanning systems/pages has linked region fragments, not a
  box covering unrelated notation.
- Boundary editing updates section membership, ratings, colors and exercises
  consistently. Split and merge act on the section, because that is what the
  reader can see and select.

## Sidebar hierarchy
1. Section title, range, rating, local peak, and one line on what it demands.
2. Short 'Why this is challenging' explanation.
3. Primary exercise with concrete steps and a notation/text example: the
   technique, how to execute it, what to listen for, and how to return to the
   written rhythm and reconnect the passage.
4. Pace and practice-duration controls.
5. 'Ready to reconnect' success criteria and next action.
6. 'Inside this passage': the phrases it contains and any locally harder spot,
   as secondary detail rather than a competing answer.
7. Optional alternative exercise and expandable sources.

Use plain musician-facing language. Avoid exposing JSON, provider names, tokens, or internal model reasoning in the practice flow.

## Required states
Empty, uploading, recognizing, analyzing, ready, partial recognition, unsupported file, provider failure, missing credentials, and example mode. Show stages honestly; do not invent progress percentages. Preserve usable results after partial failures.

## Interaction quality
Keyboard-operable selection, visible focus, adequate contrast, accessible labels, and a phrase list alternative to small score targets. Zoom and resize must not shift annotation positions. Keep the sidebar usable while navigating a long page.
