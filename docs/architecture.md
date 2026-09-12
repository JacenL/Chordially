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
No implementation decisions are approved yet. Add dated entries only for material choices and changes, including rationale and consequences.
