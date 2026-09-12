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
1. Original notation, always legible.
2. Subtle phrase outlines or brackets with phrase name and one-decimal rating.
3. A continuous thin difficulty ribbon directly below each system, spanning its measures with no decorative gaps.
4. A clear selected-region outline independent of the difficulty color.
5. Distinct neutral hatching for unrecognized regions.

Difficulty is measure-based, not a single flat color per phrase. Use documented interpolation between color anchors for numeric values. Each measure has a stable representative color; keep adjoining ribbon segments flush. Do not blur local changes so much that a difficult measure disappears. 'Continuous' means a connected score-aligned ribbon, not a gradient stretched arbitrarily across an entire page.

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
- Hover/focus: show measure label, one-decimal estimate, and brief difficulty factors.
- Click/keyboard activation: select measure and parent phrase; synchronize sidebar and phrase list.
- At a measure containing two phrases, show the boundary and allow selecting either phrase through its outline/list entry. Document the default parent chosen by a measure click.
- Selecting a sidebar passage scrolls its score region into view without losing selection.
- A phrase spanning systems/pages has linked region fragments, not a box covering unrelated notation.
- Boundary editing updates phrase membership, phrase rating, and exercises consistently.

## Sidebar hierarchy
1. Phrase title, range, rating, and local peak if useful.
2. Short 'Why this is challenging' explanation.
3. Primary exercise with concrete steps and a notation/text example.
4. Pace and practice-duration controls.
5. 'Ready to reconnect' success criteria and next action.
6. Optional alternative exercise and expandable sources.

Use plain musician-facing language. Avoid exposing JSON, provider names, tokens, or internal model reasoning in the practice flow.

## Required states
Empty, uploading, recognizing, analyzing, ready, partial recognition, unsupported file, provider failure, missing credentials, and example mode. Show stages honestly; do not invent progress percentages. Preserve usable results after partial failures.

## Interaction quality
Keyboard-operable selection, visible focus, adequate contrast, accessible labels, and a phrase list alternative to small score targets. Zoom and resize must not shift annotation positions. Keep the sidebar usable while navigating a long page.
