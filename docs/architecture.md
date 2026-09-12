# PracticeMap — architecture decisions

Status: proposed constraints; stack and providers are intentionally undecided.
During Plan Mode, recommend the concrete architecture. After approval, replace the decision slots below with the selected implementation and supporting documentation links.

## Required pipeline
Upload → validate file → extract/render pages → recognize notation and geometry → normalize and validate → infer structure/phrases → compute difficulty → select grounded techniques → render score and sidebar.

Retain stable references to the original score throughout. A vision model's prose description alone is insufficient for exact score overlays and passage-derived exercises.

## Decisions to resolve in T00–T02
| Decision | Required resolution |
|---|---|
| Web stack | Choose one stack compatible with deployment and recognition runtime |
| Recognition | Compare a small number of realistic providers/libraries using current documentation; select one |
| Geometry | Explain how actual measure/note positions are obtained and checked, not just estimated by an LLM |
| Rendering | Original scan viewer, coordinate conversion, page/system handling, and optional re-engraving |
| Hosting | Proposed runtime and limits; identify whether recognition needs a separate process/service |
| LLM use | Specify tasks, model configuration, schema validation, and cost/latency constraints |
| Persistence | Define local progress storage and uploaded-file lifecycle |
| Rubric | Concrete feature rules, weights/aggregation, tempo assumptions, and unknown-value handling |

Choose a recommended path, not an unresolved menu. Do not promise a provider emits geometry or MusicXML until verified. If the initial approach cannot support real upload-to-overlay mapping, expose the limitation and propose a feasible scope before extensive UI work.

## Minimum conceptual data contracts
These are contract requirements, not a prescribed library syntax. Convert them into validated schemas during T02.

- Score: id, input kind, title if known, pages, recognition status, assumptions, warnings.
- Page: id, index, source dimensions, rotation/transform metadata, systems.
- System: id, pageId, region, ordered measureIds.
- Measure: stable id, printed label, ordinal, systemId, geometry fragments, meter/key/tempo context, noteIds, recognition quality.
- Note/event: stable id, measureId, rational onset/duration, pitches or rest, ties/slurs/articulation where available, geometry if supported, uncertain fields.
- Phrase: id, label, structural start/end event anchors, practice start/end anchors, region fragments, boundary reasons, uncertainty, user-edited flag.
- Trouble spot: id, parentPhraseId, exact range, supported feature evidence.
- Difficulty: targetId, nullable score, factors, peak where relevant, assumptions, rubricVersion. Display one decimal; reject invalid scores.
- Exercise: id, phraseId/troubleSpotId, techniqueId, exact range, steps, transformed events if applicable, tempo rule, listening goals, success criteria, return step, sourceIds.
- Progress: score fingerprint/id, targetId, user edits, self-reported state, settings, timestamp.

Distinguish stable IDs from printed numbering, which can repeat or be absent. Document range endpoint conventions. Keep pitch spelling and sounding pitch distinct if necessary. Preserve tuplets/ties rather than flattening them into incorrect durations.

## Geometry requirements
- Use normalized page coordinates or a clearly specified equivalent.
- Record origin, axes, source dimensions, crop/rotation transforms, and zoom mapping.
- Attach ribbon segments to measure geometry; never distribute equal widths unless the real measures have equal widths.
- Phrase ranges crossing systems/pages require multiple fragments.
- Note/beat-level boundary editing requires an actual anchor strategy. If recognition supplies only measure boxes, propose and disclose how finer boundaries are supported.

## Reliability boundaries
- Validate upload type, size, page count, and parser failures.
- Validate provider output before downstream calculations.
- Keep missing values explicit and separate from zero.
- Reject exercises referencing nonexistent notes or wrong score IDs.
- Cache or reuse analysis for unchanged inputs/settings where feasible; invalidate affected outputs on edits.
- Label example mode and re-engraved notation explicitly.
- Keep secrets server-side and temporary uploads out of Git.
- Record latency and limits from actual observations; do not claim benchmarks before running them.

## Expected source organization after stack selection
src/app or equivalent: screens and endpoints.
src/components: shared UI.
src/features/{upload,score-viewer,segmentation,difficulty,practice}: product features.
src/server/{recognition,analysis}: adapters and orchestration.
src/schemas: runtime-validated domain contracts.
src/content: technique library and source metadata.
tests/{unit,integration,e2e}: appropriate behavioral checks.
fixtures: reviewed matching score inputs and reference results.

Create these as they become useful; do not fill the repository with empty placeholder modules.

## Decision log

### 2026-09-12 — Stack: pure Python
FastAPI + Jinja2 + vanilla ES modules; Pydantic contracts; pytest and Playwright
(Python bindings) for tests. Chosen because the machine has Python 3.14.6 but no
Node, Java or Docker, and because Verovio, music21, OpenCV and Playwright all
ship Python packages. Consequence: one runtime, one `pip install`, one start
command, and no JS build step — which is worth more than a component framework
on a 9-hour budget.

### 2026-09-12 — Geometry from OpenCV, content from a vision model
The page's measure positions are found by classical CV (staff-line projection,
barline morphology) and never by a model. A model supplies only musical content.
All arithmetic is Python. This is what makes overlays exact rather than
estimated, and it satisfies the requirement above that positions be obtained and
checked rather than guessed.

Consequence: boxes are stored in normalized page coordinates, so the browser
positions overlays in percentages and zoom/resize cannot desynchronize them.
A useful second consequence: geometry computed on a 200-DPI render crops
correctly out of a 400-DPI render of the same page, because normalized
coordinates are resolution-independent.

Three discriminators were needed to separate barlines from note stems, and only
the third made it reliable: (a) a tall continuous vertical run inside the staff,
(b) absence of ink in a margin just outside the staff — stems protrude to reach
their beams, barlines terminate at the staff lines, and (c) whitespace on at
least one side, because an engraver leaves air around a barline whereas a stem
has a notehead welded to it. Detection also supplies a virtual barline at each
staff's left and right edge, since this engraving draws none at a system's start
and the clef, time signature and entire first measure would otherwise be
discarded.

### 2026-09-12 — Transcription unit: a chunk of ~2 measures (revised twice)
The approved plan said one measure per request, to localise errors. Measured
against the real scan, that produced low confidence almost everywhere: pitch is
a relative judgement against five staff lines and a measure crop does not
reliably contain them. Whole systems failed differently — an 8:1 strip is
downscaled by its long edge until the staff is ~100px tall, and raising render
DPI cannot help because the resize happens after rendering.

A run of about two measures keeps the whole staff in frame at an aspect ratio
that is not downscaled at all. Consequence: roughly 31 requests per page instead
of 61, each more accurate. Error localisation is retained because every measure
is still validated on its own and the returned measure count is cross-checked
against the count geometry found — a mismatch marks the chunk for review rather
than silently misaligning notes to regions.

### 2026-09-12 — Validation: arithmetic outranks self-reported doubt
A measure is accepted on whether its durations sum to the time signature, not on
whether the model said it felt sure. Self-reported illegibility is recorded as a
confidence marker instead. Rationale: the recurring ambiguity on this repertoire
is whether a beam group is eighths or 16ths, and that choice changes the total
duration — so a measure that lands exactly on the meter has already been
verified on the very point in doubt. Measured effect: validation went from 44%
to 87% on the same data, while both measures that genuinely failed to add up
stayed rejected. Missing values remain explicit: a rejected measure is unrated
(`None`, never 0.0) and renders as needing review.

### 2026-09-12 — Credential: PRACTICEMAP_ANTHROPIC_API_KEY, read explicitly
The client is always constructed as `Anthropic(api_key=...)`. A bare
`Anthropic()` would resolve `ANTHROPIC_API_KEY`, then `ANTHROPIC_AUTH_TOKEN`,
then an `ant auth login` profile on disk — silently borrowing an unrelated
credential, billing the wrong account, and making "example mode runs without
credentials" untestable, because the app would appear to work with its own key
unset. Consequence: a test asserts no bare construction exists, and the
zero-credential check unsets the app's key while deliberately leaving an ambient
`ANTHROPIC_API_KEY` set.

### 2026-09-12 — Wire format is lean; the domain model is rich
A nested schema (system → measures → notes, with a Literal enum per field) is
rejected by the structured-output layer with "Schema is too complex". The
provider boundary therefore uses a flat list of short plain-typed notes, each
tagged with its measure index, converted to the validated domain types in
Python. Also: `max_length` on a string field is stripped from the schema sent to
the API but still enforced client-side, so an over-long remark became a hard
ValidationError that discarded an otherwise good transcription. Length is
constrained by the prompt instead.

### 2026-09-12 — The browser does no coordinate arithmetic
Every overlay leaves Python as a percentage string and the browser positions it
inside a `position:relative` page element. Zoom is implemented as one CSS
custom property changing the page's width; nothing recalculates, because there
is nothing to recalculate. A unit test rejects any style string carrying a unit
other than `%`, and a Playwright test measures every measure overlay as a
fraction of the page image at two viewport widths and two zoom levels and
requires agreement to within 0.002 of page width -- under two pixels, far less
than the gap between adjacent measures.

Consequence: "annotations survive zoom and resize" is a property of the
coordinate system rather than a behaviour to maintain, and adding a new overlay
type cannot reintroduce drift.

### 2026-09-12 — Ribbon geometry: flush by construction, inside the system band
A ribbon segment starts at its own measure's left edge and ends at the *next*
measure's left edge, not at its own right edge. Adjoining segments therefore
share an edge exactly and no rounding gap can open between them; the run is
stretched to the system's own extent at both ends. Widths still come from the
engraved barlines, so nothing is distributed equally.

Vertically the ribbon sits in the lowest sliver of the system band. That band is
the staff plus margin, clamped by `cv_geometry` to halfway toward the
neighbouring staff, so bands tile the page with no gap between them -- there is
no gutter to draw in. The bottom 13% of the band, inset by 2%, is the whitespace
between staves: "directly below each system" without covering notation.

### 2026-09-12 — A measure click selects the phrase owning its first note
Structural phrase ranges are `(measure ordinal, note index)` pairs and tile the
analyzable music, so a boundary can fall inside a measure and two phrases can
appear in one. The click rule is stated once, in `owning_phrase`: the phrase
containing that measure's first note wins. The other phrase stays reachable from
its outline and from the phrase list, and the measure is marked as both ending
one phrase and starting the next so the split is visible rather than silently
resolved.

A measure recognition could not read belongs to no phrase and returns None. It
is never attached to a neighbour to keep the coverage tidy.

### 2026-09-12 — Unrated is rendered as unknown in three places, not one
Hatching on the ribbon was not enough. A rated phrase can contain a measure
nobody could read, and showing only the phrase's number implied the rating
covered music it was never computed from. The sidebar now names the specific
unrated measure and says which kind of failure it was -- unreadable notation
versus a request that never completed -- alongside the phrase rating and the
statement that the rating comes from the measures around it.
