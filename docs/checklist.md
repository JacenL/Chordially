# PracticeMap — authoritative delivery checklist

Status: in progress. Plan approved; C1 complete.
Working repository: https://github.com/arkyarky4546-ai/HackCMU-Happy-
Remote: verified. `origin` fetch and push both point at
arkyarky4546-ai/HackCMU-Happy-.git. Push access confirmed by a real push, not
assumed.
Working branch: practice-map-build, created from main at 95f7ceb.
Current task: C2 (domain contracts, rubric, segmentation).

Checkpoint mapping: the 9-hour budget re-sequences T00–T09 into checkpoints
C1–C7. Each checkpoint is a commit. The T-numbers below record which acceptance
conditions each checkpoint discharges.

Task workflow: complete acceptance → record actual validation → mark complete → commit task code/docs → push working branch. Top-level tasks are commit-sized increments. Split a large task before starting if needed. Plan Mode produces a proposal; T00 is finalized and committed only after leaving Plan Mode with approval.

## T00 — Approve the implementation approach
- [x] Complete (checkpoint C1)
- Dependencies: none.
- Acceptance: repository inspected; one recommended architecture; genuine scan-to-geometry path identified; phrase-length interpretation and assumptions stated; stack/runtime constraints researched; ordered plan presented and approved.
- Evidence: environment verified read-only before any decision — Python 3.14.6
  present; Node, Java, Docker and gh absent, which selected a pure-Python stack.
  All of numpy, opencv-python-headless, verovio, music21, fastapi, pymupdf,
  anthropic, playwright, pytest resolve and import on cp314. Plan approved by the
  user, including the phrase-length interpretation (one musical idea per group; a
  genuine two-measure phrase is valid, mechanical two-measure slicing is not).
- Delivery: commit f680aa7, pushed to origin/practice-map-build.
- Blocker: none.
- Defect: commit f680aa7's message carries a stray `@` on its first and last
  lines — PowerShell here-string syntax used in the Bash tool, which does not
  parse it. Content is correct. Not amended: the commit was already pushed and
  CLAUDE.md forbids rewriting published history. Cosmetic only.

## C1 — Recognition spike: go/no-go
- [x] Complete
- Acceptance: prove a real scan becomes validated musical events before any UI
  work, per CLAUDE.md ("resolve scan recognition and coordinate mapping early").
- **Verdict: GO.**
- Evidence, measured on fixtures/scores/wohlfahrt-op45-bk1.pdf page 3:
  - Geometry: 11 systems and 61 measures detected, skew −0.10°, verified by eye
    against a rendered overlay. System detection was correct on the first run;
    barline detection needed three fixes (below).
  - Transcription: **13 of 15 measures validated (87%)** across 9 chunks.
  - **Zero measure-count mismatches** between page geometry and transcription.
    This is the load-bearing contract — it is what lets a transcribed measure be
    attached to a real region on the page.
  - The 2 rejections are genuine arithmetic failures (durations summed to 7/8
    and 1/2 against 4/4), correctly surfaced rather than rendered as if fine.
  - Latency 26s per 2-measure chunk. A full page is ~31 chunks, so serial
    execution is ~13 minutes; C4 must run chunks concurrently.
  - Prompt caching is effective: 18,531 cached input tokens over the run.
- Delivery: see C1 commit.
- Blocker: none.

### What the spike changed about the plan

Three findings overrode the approved design. Each is recorded in
architecture.md's decision log with its rationale.

1. **Per-system chunks, not per-measure crops.** The plan specified transcribing
   one measure at a time to localise errors. In practice the model reported low
   confidence on nearly every measure, correctly: pitch is judged against the
   five staff lines, and a measure-sized crop does not reliably show them. Error
   localisation is preserved anyway, because each measure is still validated
   independently and the measure count is cross-checked against geometry.
2. **Chunks of ~2 measures, not whole systems.** A full system is an 8:1 strip.
   Image downscaling is driven by the long edge, so the staff was reduced to
   about a hundred pixels tall and pitch became guesswork again — raising render
   DPI does not help, because the resize happens afterwards.
3. **Arithmetic outranks self-reported doubt.** Initially a measure the model
   flagged illegible was rejected outright, which put the validation rate at
   44%. But the recurring doubt on this repertoire is eighths-versus-16ths, and
   that choice changes the measure's total duration — so a measure that sums
   exactly to the meter has already been checked on the precise point the model
   was unsure about. Reordering so durations decide, and treating illegibility
   as a confidence marker, moved the rate from 44% to 87% without weakening the
   gate: the two measures that genuinely failed to add up are still rejected.

## C2 — Domain contracts, rubric, segmentation
- [x] Complete
- Acceptance: validated domain schemas; numeric rating and colour policy with
  aggregation; phrase segmentation; tests over boundaries and missing data.
- Evidence: **79 unit tests pass.** They pin the six colour anchors byte-exactly,
  the half-open category edges (2.0 is Advanced Beginner, not Beginner-friendly),
  `None` rendering differently from 0.0, peak-biased phrase aggregation, the
  practice-overlap rule including a final phrase that borrows nothing, exact
  rational durations for dots and tuplets, and every case the beam repair must
  refuse.
- Artifacts: `fixtures/expected/wohlfahrt-p3-analysis.json` (drives example mode,
  no credentials needed) and `fixtures/expected/review-phrases.md` (awaiting a
  violinist's review; its header says so).
- Delivery: see C2 commit.

### Two correctness bugs found and fixed during C2

1. **Key and meter drifted across the page.** `key_fifths` defaults to 0, which
   is also a legitimate value (C major), so a chunk that simply showed no key
   signature reported 0 and silently overwrote a correct reading. Combined with
   running all chunks concurrently — where later chunks read context before
   earlier ones had written it — the page's 2/4 G-major etude was analyzed as
   4/4 in C, and a spurious key change at measure 10 produced a false
   0.98-confidence structural boundary. Fixed by asking explicitly whether a
   signature is *printed* in the image, and by a two-pass order: system starts
   first, everything else after. The page now reports exactly two key/meter
   states, at measures 1 and 29, which matches the score.
2. **Recognition and provider failure were conflated.** A measure whose request
   never completed was recorded identically to one recognition read and
   rejected. `not_attempted` is now a distinct state, so an outage or an
   exhausted credit balance cannot masquerade as poor recognition.

### Measured recognition on the fixture page

| Outcome | Measures | Meaning |
|---|---|---|
| confident | 14 | read and validated against the meter |
| uncertain | 18 | validated, but flagged (beam repair applied, or short measure) |
| unreadable | 8 | genuinely rejected: durations did not add up |
| **not_attempted** | **21** | **never read — see the blocker below** |

**32 of the 40 measures actually attempted validated (80%)**, consistent with
C1's 87% on its smaller sample.

## BLOCKER — application API credit exhausted
- Status: **blocking live recognition. Not blocking anything else.**
- Symptom: HTTP 400 `invalid_request_error` on 12 of 34 chunks.
- Actual message: *"Your credit balance is too low to access the Anthropic API."*
- This is the **application's** account, funding `PRACTICEMAP_ANTHROPIC_API_KEY`.
  It is separate from the Claude Code session's own usage.
- What is needed: credit on that Anthropic account. **Do not paste a key into
  chat**; the existing `.env` entry is already correct and does not need changing.
- Mitigation in place: a transcription cache (`work/transcription-cache/`, keyed
  by image bytes + model + prompt, gitignored) holds the 22 chunks that did
  succeed. Re-running rebuilt the fixture in **3 seconds instead of 685**, and
  when credit is restored only the 12 failed chunks will cost anything.
- Work continues on everything that does not need the provider: C3's viewer and
  ribbon run entirely against the saved fixture.

## T01 — Establish musical evidence and example inputs
- [ ] Complete
- Dependencies: T00.
- Acceptance: sourced technique library design; additional violin techniques researched; one real matching scan/MusicXML example with provenance and reviewed reference expectations. Include contrasting difficulty and a suitable even-note run.
- Evidence: pending.
- Delivery: pending (commit + verified push to the intended GitHub branch).
- Blocker: none recorded.

## T02 — Establish contracts, rubric, and runnable scaffold
- [ ] Complete
- Dependencies: T01.
- Acceptance: app starts; exact commands documented; validated domain schemas; numeric rating/color policy and aggregation defined; credentials example uses real chosen integration variable names; no secrets committed.
- Evidence: pending.
- Delivery: pending (commit + verified push to the intended GitHub branch).
- Blocker: none recorded.

## T03 — Prove score rendering and region selection
- [ ] Complete
- Dependencies: T02.
- Acceptance: example score displays with accurate measure regions; click/focus selects correct stable IDs; multi-system region alignment survives zoom/resize; note/beat anchor strategy supports phrase boundaries.
- Evidence: pending.
- Delivery: pending (commit + verified push to the intended GitHub branch).
- Blocker: none recorded.

## T04 — Analyze a real uploaded scan
- [ ] Complete
- Dependencies: T03.
- Acceptance: supported PDF/image upload flows through actual recognition to validated events and original-page geometry; partial recognition is visible; unsupported/provider-failed inputs have recovery; MusicXML import available. Example mode never substitutes silently.
- Evidence: pending.
- Delivery: pending (commit + verified push to the intended GitHub branch).
- Blocker: none recorded.

## T05 — Create editable musical phrases and trouble spots
- [ ] Complete
- Dependencies: T04.
- Acceptance: one-idea phrase groups with defensible reasons; structural/phrase/micro-range levels distinct; within-measure and cross-system boundaries; split/merge/edit works; practice overlap includes next available first note without changing structural ownership; final phrase handled.
- Evidence: pending.
- Delivery: pending (commit + verified push to the intended GitHub branch).
- Blocker: none recorded.

## T06 — Add ratings and the continuous difficulty ribbon
- [ ] Complete
- Dependencies: T05.
- Acceptance: analyzed phrases and measures use 0.0–10.0 with one decimal; documented rubric; local factors and phrase peak visible; green/yellow/orange/red/maroon mapping correct at boundaries; continuous per-system measure-aligned ribbon; neutral missing-data treatment; accessible selection.
- Evidence: pending.
- Delivery: pending (commit + verified push to the intended GitHub branch).
- Blocker: none recorded.

## T07 — Deliver passage-specific practice instruction
- [ ] Complete
- Dependencies: T06.
- Acceptance: sidebar explains selected challenge; fitting sourced techniques beyond slowing down; complementary rhythm variants preserve intended pitch order and duration semantics; contrasting passage gets different suitable advice; success/reconnection/source details available; unsupported transformations prevented.
- Evidence: pending.
- Delivery: pending (commit + verified push to the intended GitHub branch).
- Blocker: none recorded.

## T08 — Persist practice choices and complete interaction states
- [ ] Complete
- Dependencies: T07.
- Acceptance: self-reported progress, settings, and edits persist against correct score identity; reanalysis invalidates stale results appropriately; responsive sidebar, keyboard operation, honest loading/error/empty states, and complete legend work.
- Evidence: pending.
- Delivery: pending (commit + verified push to the intended GitHub branch).
- Blocker: none recorded.

## T09 — Deliver a reproducible hackathon demo
- [ ] Complete
- Dependencies: T08.
- Acceptance: fresh setup documented and exercised; core end-to-end flow passes; relevant build/type/domain checks pass; example works without credentials; real upload path demonstrated with configured provider or explicitly recorded as blocked; demo script and known limits updated; no unfinished core feature labeled complete.
- Evidence: pending.
- Delivery: pending (commit + verified push to the intended GitHub branch).
- Blocker: none recorded.

## Known bugs
None evaluated yet. For each bug record ID, reproduction steps, expected/actual behavior, affected task, and status. A lack of recorded bugs does not mean the application has been tested.

## Git delivery blockers
None evaluated yet. Record failed commits/pushes here or in the handoff. Task completion and remote backup are separate facts.

## Handoff
- Next action: run the Plan Mode kickoff prompt.
- Outstanding decision: architecture/provider selection and GitHub access and branch verification.
- Last meaningful validation: none; starter documents only.
