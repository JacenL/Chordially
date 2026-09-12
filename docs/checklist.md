# PracticeMap — authoritative delivery checklist

Status: demo-ready. C1–C6 and C8–C10 delivered. C7's persistence half and
within-measure boundary editing remain, recorded below.
Working repository: https://github.com/arkyarky4546-ai/HackCMU-Happy-
Remote: verified. `origin` fetch and push both point at
arkyarky4546-ai/HackCMU-Happy-.git. Push access confirmed by a real push, not
assumed.
Working branch: practice-map-build, created from main at 95f7ceb.
Current task: none in flight.

## How this document is organized

The original plan listed tasks T00–T09. The recognition spike (C1) changed
enough about the design that a straight T-by-T sequence no longer described the
work, and the 9-hour budget re-sequenced it into seven commit-sized checkpoints
C1–C7. Each checkpoint is one Git checkpoint and discharges named T-acceptance
conditions, which are reproduced in full inside the checkpoint that owns them.
No T condition was dropped; the map below says where each one lives.

| T | Original subject | Discharged by |
|---|---|---|
| T00 | Approve the implementation approach | C1 |
| T01 | Musical evidence, technique library, example inputs | C2 (example input) + C6 (sourced technique library) |
| T02 | Contracts, rubric, runnable scaffold | C2 (contracts, rubric) + C3 (app starts, commands documented) |
| T03 | Score rendering and region selection | C3 |
| T04 | Analyze a real uploaded scan | C4 |
| T05 | Editable phrases and trouble spots | C5 |
| T06 | Ratings and the continuous difficulty ribbon | C2 (rubric, colour policy) + C3 (ribbon, legend, selection) |
| T07 | Passage-specific practice instruction | C6 |
| T08 | Persist practice choices; complete interaction states | C7 |
| T09 | Reproducible hackathon demo | C7 |

Task workflow: complete acceptance → record actual validation → mark complete →
commit task code/docs → push working branch. Split a checkpoint before starting
it if it will not fit one coherent commit.

## C1 — Recognition spike: go/no-go
- [x] Complete
- Discharges T00.
- Acceptance: prove a real scan becomes validated musical events before any UI
  work, per CLAUDE.md ("resolve scan recognition and coordinate mapping early");
  repository inspected; one recommended architecture; genuine scan-to-geometry
  path identified; phrase-length interpretation and assumptions stated;
  stack/runtime constraints researched; ordered plan presented and approved.
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
  - Environment verified read-only before any decision — Python 3.14.6 present;
    Node, Java, Docker and gh absent, which selected a pure-Python stack. numpy,
    opencv-python-headless, verovio, music21, fastapi, pymupdf, anthropic,
    playwright and pytest all resolve and import on cp314.
- Delivery: commits f680aa7 and d173d13, pushed to origin/practice-map-build.
- Blocker: none.
- Defect: commit f680aa7's message carries a stray `@` on its first and last
  lines — PowerShell here-string syntax used in the Bash tool, which does not
  parse it. Content is correct. Not amended: the commit was already pushed and
  CLAUDE.md forbids rewriting published history. Cosmetic only.

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
- Discharges T02 (validated domain schemas; numeric rating and colour policy
  with aggregation; credentials example uses the real integration variable name;
  no secrets committed), T06 (documented rubric, 0.0–10.0 with one decimal,
  local factors and phrase peak, colour mapping correct at boundaries, neutral
  missing-data treatment) and T01's example-input half (one real matching scan
  with provenance and a reference expectation file).
- Evidence: **79 unit tests pass.** They pin the six colour anchors byte-exactly,
  the half-open category edges (2.0 is Advanced Beginner, not Beginner-friendly),
  `None` rendering differently from 0.0, peak-biased phrase aggregation, the
  practice-overlap rule including a final phrase that borrows nothing, exact
  rational durations for dots and tuplets, and every case the beam repair must
  refuse.
- Artifacts: `fixtures/expected/wohlfahrt-p3-analysis.json` (drives example mode,
  no credentials needed) and `fixtures/expected/review-phrases.md` (awaiting a
  violinist's review; its header says so).
- Delivery: commit aa9c63f, pushed to origin/practice-map-build.

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

## RESOLVED BLOCKER — application API credit was exhausted
- Status: **cleared 2026-09-12 during C4.** Re-probed at the start of the C4
  session and still failing; re-probed ~45 minutes later and returning 200.
  Credit was added to the account in between. Verified twice: a direct
  `messages.create` call, and 12 chunks read live inside a real upload with
  zero failures.
- Original symptom: HTTP 400 `invalid_request_error` on 12 of 34 chunks.
- Actual message: *"Your credit balance is too low to access the Anthropic API."*
- This is the **application's** account, funding `PRACTICEMAP_ANTHROPIC_API_KEY`.
  It is separate from the Claude Code session's own usage.
- What is needed: credit on that Anthropic account. **Do not paste a key into
  chat**; the existing `.env` entry is already correct and does not need changing.
- Mitigation in place: a transcription cache (`work/transcription-cache/`, keyed
  by image bytes + model + prompt, gitignored) holds the 22 chunks that did
  succeed. Re-running rebuilt the fixture in **3 seconds instead of 685**, and
  when credit is restored only the 12 failed chunks will cost anything.
- Consequence, now moot: C4's "real supported uploaded score" condition was
  going to be unsignable. It is signed off with a live run instead. The
  provenance disclosure built while the blocker was active is kept, because a
  cached run and a live run are still different facts and the interface should
  keep saying which one happened.

## C3 — Score viewer, difficulty ribbon, and selection
- [x] Complete
- Dependencies: C2.
- Discharges T03 in full, T06's interface half, and T02's runnable-scaffold half.
- Acceptance:
  - Example score displays over the original scan with accurate measure regions;
    example mode works with no credentials and is labelled, never substituted
    silently.
  - Click and keyboard activation select the correct stable IDs; focus is
    visible; a phrase list provides an alternative to small score targets.
  - Multi-system region alignment survives zoom and resize; a phrase crossing
    systems renders as linked fragments, not one box over unrelated notation.
  - A continuous per-system, measure-aligned ribbon with flush segments and no
    decorative gaps; segment widths follow real measure widths.
  - Ratings show 0.0–10.0 to one decimal with category labels; the six colour
    anchors and their interpolation match docs/design.md; unrated measures show
    neutral hatching and "Needs review", never 0.0 and never green.
  - Difficulty legend visible and complete.
  - Sidebar shows the selected phrase's identity, range, rating, local peak, and
    the factors behind the rating. Exercise content is C6 and is marked as not
    yet present rather than faked.
  - App starts; install/dev/test commands documented in README.md and CLAUDE.md.
- Evidence: **114 unit, integration and browser tests pass** (79 from C2, 35 new).
  - Alignment through zoom and resize is measured, not asserted: a Playwright
    test records all 61 measure overlays as fractions of the page image at
    1400px and 820px viewport widths and at 100% and 150% zoom, and requires
    agreement within 0.002 of page width — under two pixels, far narrower than
    the gap between adjacent measures.
  - Ribbon continuity is checked twice: on the computed percentages, and again
    on `getBoundingClientRect()` in Chromium, where adjacent segments in each of
    the 11 systems must touch within 1px. Segment widths are asserted unequal,
    so nothing is distributed evenly.
  - A unit test rejects any style string carrying a unit other than `%`, which
    is what makes the zoom guarantee structural rather than maintained.
  - Selection: clicking a measure selects the phrase owning its first note and
    syncs outline, phrase list and sidebar; arrow keys, Home and End move and
    select; one roving tab stop covers all 61 measures.
  - 8 of 15 phrases cross a system break and render as linked fragments, one per
    system, verified to occupy distinct vertical bands.
  - Rendered and reviewed by screenshot at 1440×950.
- Delivery: see C3 commit.
- Blocker: none.

### Two interface defects found and fixed during C3

1. **Phrase chips covered the notation above them.** Each chip hung over the top
   edge of its outline, which put it inside the *previous* system's band and on
   top of real notes. Moved inside the outline, into the ledger space above its
   own staff, and held at reduced opacity until hovered or selected. Notation
   legibility outranks labelling.
2. **A rated phrase hid its unreadable measures.** The ribbon hatched them, but
   the sidebar showed only the phrase's number, implying the rating covered
   music it was never computed from. The sidebar now names the specific unrated
   measure, says whether it was unreadable or never attempted, and states that
   the phrase rating comes from the measures around it. Found by a browser test,
   not by reading the code.

### Not in C3, deliberately

- Upload is present on the start screen but disabled and labelled as not wired
  up. It is C4's work and is not faked.
- The practice sidebar shows passage identity, rating, local peak, rating
  factors and boundary reasoning. Exercises, pace rules, listening goals and
  sources are C6, and the panel says so rather than showing generic advice.
- `requirements.txt` and `requirements-dev.txt` were added here: the repository
  had no dependency manifest at all, which made "fresh setup documented" in C7
  unachievable.

## C4 — Real upload path
- [x] Complete
- Dependencies: C3.
- Discharges T04.
- Acceptance: supported PDF/image upload flows through actual recognition to
  validated events and original-page geometry; chunks run concurrently (C1
  measured ~13 minutes serially, which is not usable); honest staged progress
  with no invented percentages; partial recognition stays visible and usable;
  unsupported files and provider failure each have a specific recovery action;
  MusicXML import available as a stated alternative; example mode never
  substitutes for a failed upload silently; upload size/page limits enforced and
  disclosed; transmission to the provider disclosed in the flow.
- Evidence: **124 tests pass**, including a live end-to-end upload test
  (`-m live`) that posts the real PDF, polls the job to completion, and asserts
  the resulting page carries a ribbon and a provenance line.
  - Measured on `fixtures/scores/wohlfahrt-op45-bk1-p3.pdf` (page 4 of the book,
    extracted as a one-page file and verified to render pixel-identical to the
    fixture source, so the cache keys match):
    11 systems, 61 measures, 15 phrases, **43 of 61 measures rated (70%)**,
    ratings spanning 1.0–7.0, 14 of 15 phrases rated.
  - First run: 65s, 22 sections from cache and **12 read live with zero
    failures**. Second run: 1.7s, fully cached.
  - Quality split afterwards: 20 confident, 23 uncertain, 18 unreadable,
    **0 not_attempted** — the 21 measures previously never read are now read.
  - Scope enforcement tested for empty files, unsupported formats, a file lying
    about being a PDF, oversize uploads and images too small to find staves.
    Every rejection carries a named recovery action.
- Blocker: none. The credit blocker above is cleared.

## C5 — Editable phrases and trouble spots
- [x] Complete for measure-boundary edits. **Within-measure boundaries remain
  unbuilt** — see the limitation below.
- Dependencies: C4, C9.
- Discharges T05: split and merge work, structural/phrase/trouble-spot levels
  are distinct, boundaries cross systems, practice overlap is recomputed
  without changing structural ownership, and the final phrase is handled.
- Evidence: **212 tests pass** (207 offline, 5 live), 22 new on this checkpoint.
  - The load-bearing invariant is asserted after every edit: structural coverage
    tiles the measures with **no gaps and no duplicate ownership**, and every
    phrase stays contiguous. This is why an edit rebuilds the list from a
    partition of measure indices rather than patching two phrases in place —
    patching is how a gap gets introduced, and the user would only find it by
    clicking the orphaned measure.
  - Split then merge returns the exact original member sets.
  - Practice overlap is recomputed, and the "first *playable* note" rule is
    tested against a real case: the split in the fixture borrows past measure
    15, which has no readable notes, to measure 16. Borrowing an empty measure
    would hand the player a rest and call it the join.
  - A merged phrase's rating equals a fresh aggregation over the union of its
    members; a split separates a hard half from an easy one instead of averaging
    them.
  - A boundary the user placed records confidence 1.0 and the reason "you placed
    this boundary" — it is an assertion, not an inference, and is not dressed up
    as one. Untouched neighbours keep their original inferred reasons.
  - Four refusals tested by name: splitting where a phrase already begins,
    splitting at a measure outside the phrase, merging the last phrase, and
    editing a phrase id belonging to another score.
  - Driven end to end in Chromium: split, merge, refusal message, and undo.
- **Limitation, stated rather than implied:** boundaries can only be placed at
  measure lines. The product spec asks for a boundary inside a measure, and the
  data model supports it — anchors carry a note index — but the interface does
  not. Product acceptance criterion 3 is therefore partially met.
- **Limitation:** edits live in memory and are lost when the server restarts.
  `docs/demo.md` says so.
- Discharges T05.
- Acceptance: one-idea phrase groups with defensible reasons; structural,
  phrase and micro-range levels distinct; boundaries within a measure and across
  systems; split/merge/adjust works; practice overlap includes the next
  available first note without changing structural ownership; the final phrase,
  which borrows nothing, is handled; structural coverage keeps no gaps and no
  duplicate ownership after an edit.
- Evidence: pending.

## C6 — Passage-specific practice instruction
- [x] Complete
- Dependencies: C5.
- Discharges T07 and T01's technique-library half.
- Acceptance: sourced technique library with evidence categories, separating
  teacher pedagogy, research findings, and app heuristics; sidebar explains the
  selected challenge from observed notation; fitting techniques beyond slowing
  down; complementary rhythm variants preserve intended pitch order and duration
  semantics and are offered only on suitable even-note runs; a contrasting
  passage receives different applicable advice or an honest statement of
  insufficient evidence; pace rule, listening goals, self-assessed success
  criterion, return-to-context step, and expandable sources all present;
  unsupported transformations prevented; exercises referencing nonexistent notes
  or another score's IDs rejected.
- Evidence: **151 tests pass**, 27 of them on this checkpoint.
  - Five techniques, each a validated record with steps, listening goals, a pace
    rule, success criteria, a return-to-context step and evidence category.
    Citations resolve on load; a technique claiming pedagogical or research
    backing without a source fails validation.
  - Rhythm variants are computed on `Fraction`s from the phrase's own notes and
    every variant is asserted to total exactly the written duration, for eighth,
    16th, quarter and 32nd runs. Pitch order is asserted unchanged.
  - The pattern matches docs/music-pedagogy.md exactly: a 16th pair becomes a
    dotted 16th plus a 32nd, summing to 2/16.
  - Seven refusals are tested by name: runs that are too short, or contain
    rests, ties, tuplets, mixed values, an already-dotted note, or a 64th with
    no shorter printed value.
  - Selection is driven by features read from the notation, never by a rating
    alone. Different phrases of the fixture receive different primary
    techniques, and a phrase whose measures could not be read never receives a
    rhythm variation built from notes nobody read.
  - Advice is addressed as score id plus phrase id; an unknown phrase or a
    phrase from another score is a 404, not a best guess.

## C7 — Persistence and interaction states (partial), demo (done)
- [ ] **Persistence not built. Demo and states delivered.**
- Dependencies: C6.
- Discharges T09 in full; T08 only in part.
- Delivered: the required state set (empty, uploading, recognizing/analyzing,
  ready, partial recognition, unsupported file, provider failure, missing
  credentials, example mode) is rendered honestly; keyboard operation and the
  legend work; `docs/demo.md` is a measured demo script with an honest
  limitations list; the core journey passes end to end in a real browser.
- Not delivered: self-reported practice progress, settings, and score-scoped
  persistence. Analyses live in memory for the life of the process. The score
  fingerprint that persistence would key on already exists and is already
  content-based, so the foundation is there.
- Why deferred: explicitly listed as deferrable for the deadline, and no demo
  requirement depends on it.
- Acceptance: self-reported progress, settings and edits persist against the
  correct score fingerprint and cannot leak between scores; re-analysis
  invalidates stale results; responsive sidebar; keyboard operation; the full
  required state set (empty, uploading, recognizing, analyzing, ready, partial
  recognition, unsupported file, provider failure, missing credentials, example
  mode) rendered honestly; fresh setup documented and exercised; core end-to-end
  flow passes; example works without credentials; the real upload path is either
  demonstrated with a configured provider or explicitly recorded as blocked;
  demo script and known limits updated; no unfinished core feature labelled
  complete.
- Evidence: **154 tests pass** — 151 offline plus 3 `live` browser/API tests.
  The full demo journey (upload, analyze, select, read an exercise) passes in
  Chromium in 7.3s with a warm cache and zero JavaScript errors.

## C8 — Tempo recalculation
- [x] Complete
- Dependencies: C2, C3.
- Why: the score page displayed "Set a tempo to recalculate" with no such
  control. That was a false claim in the product, and the underlying feature is
  real: `rate_measure` measures demand per second, so tempo changes every rating.
- Acceptance: a supplied tempo re-rates every measure and phrase; a printed
  tempo is never overwritten by a global setting; the shared example bundle is
  not mutated; malformed input does not cost the user their analysis.
- Evidence: **171 tests pass**, 20 new.
  - Measured on the example: measure 1 rates 2.7 at 60 BPM, 3.2 assumed (90),
    and 4.2 at 160. A faster tempo is asserted never to lower a rating, and to
    raise at least one.
  - `load_example` is lru_cached, so a test asserts the cached bundle's ratings,
    per-measure tempos and assumptions are byte-identical after a retune. Without
    the deep copy, one user's tempo would leak into every later request.
  - A measure with a printed tempo keeps it under a 200 BPM override, and the
    notice says how many did.
  - Junk (`banana`, `90bpm`, `-5`) and out-of-range values fall back to the
    assumed tempo and still render the score; out-of-range is refused rather
    than clamped, so the page cannot disagree with the input box.

## C9 — Trouble spots: the third segmentation level
- [x] Complete
- Dependencies: C2, C3, C8.
- Discharges the product spec's third level and journey step 6, "explore a local
  trouble spot without losing the parent phrase context".
- Acceptance: a short technical range inside a phrase, marked only where one
  genuinely stands out; selectable without losing the parent; practice
  instruction applies to it; distinct from the phrase outline and from the
  difficulty colours.
- Evidence: **190 tests pass**, 26 new on this checkpoint.
  - On the example at the assumed tempo: 3 trouble spots across 15 phrases.
    Restraint is the point — a spot in every phrase would be noise, and a test
    asserts there are fewer spots than phrases.
  - Negative cases pinned: a uniformly hard phrase, a uniformly easy one, a rise
    below the 0.8 margin, a phrase too short to have an inside, and a phrase
    whose peak measure is unrated all yield no spot.
  - **Spots are derived, never stored.** They follow the ratings, and ratings
    follow tempo: the example has 3 spots at 90 BPM and 2 at 160, because
    Phrase 1's spot stops standing out once the whole phrase is demanding. A
    test asserts the sets differ, and another that retuning twice does not
    accumulate them.
  - Every spot's measures are a subset of its parent's; a spot crossing a system
    gets one region fragment per system; a spot borrows no practice overlap,
    because overlap is a phrase-level rule.
  - `region_fragments` was extracted from `segment_score` so phrases and spots
    share one implementation; the existing segmentation tests covered the
    refactor.

### One interaction defect found and fixed

The on-score trouble-spot outline was unclickable: the measure hit-target layer
sits above the annotation layer and intercepted every pointer event, so the box
was decoration. Rather than fight the z-order, selection now resolves to the
**most specific target owning a measure** — clicking the measure a spot is
marked on selects the spot, any other measure selects its phrase, and the parent
stays in context either way. The outline stops claiming pointer events, so it
cannot create a dead zone. Found by a browser test, not by reading the code.

## C10 — Show the rubric at the point of use
- [x] Complete
- Dependencies: C2, C3, C8.
- Why: every screen is organised around a 0.0–10.0 number, and a reader who
  asked "why 6.8?" got three factor labels and a footer disclaimer. The rubric
  cannot be validated in an afternoon, but it can be made arguable.
- Acceptance: the full rubric is inspectable beside the rating it produced; the
  explanation is generated from the constants that compute ratings, not written
  by hand; what the rubric cannot see is stated as prominently as what it can.
- Evidence: **212 tests pass**, 5 new.
  - `rubric_explanation()` reads `WEIGHTS`, `LABELS`, `RUBRIC_VERSION` and the
    curve from `src/features/difficulty/rubric.py`. A test asserts the disclosed
    weights equal the weights actually used, so a hand-edited explanation cannot
    drift from the code — the failure mode this design exists to prevent.
  - Each factor now reports the weight it was drawn from: "Note rate +0.8 of
    3.4" instead of "+0.8". A contribution with no scale is a number nobody can
    judge.
  - Seven blind spots listed by name — bowing beyond what is printed, fingering,
    string choice, shifts, the player's hand, the player's level, and the sound
    itself — each with why the rubric is silent about it.
  - The disclosure states plainly that no violinist has reviewed the scale and
    names the review packet.

### One defect found while building it

`tempo_is_assumed` means "the page prints no tempo", which stays true after the
user supplies one. Reusing it for the disclosure reported a user's own 160 BPM
back to them as an assumption. Supplied-ness is now passed explicitly through
`build_view(..., supplied_tempo=...)`, and a test pins the distinction.

## Known bugs
None open. Two correctness bugs found during C2 were fixed in the same
checkpoint and are recorded above. A lack of recorded bugs does not mean the
application has been tested.

## Git delivery blockers
None. C1 and C2 are confirmed on origin/practice-map-build.

## Handoff
- Next action: persistence (C7's remaining half), then within-measure
  boundary editing, then structural sections.
- Outstanding external setup: none. The Anthropic credit blocker is cleared and
  live recognition is verified working.
- Last meaningful validation: `python -m pytest -q` → 151 passed;
  `python -m pytest -q -m live` → 3 passed. Browser tests skip themselves if
  Chromium is absent; install it with `python -m playwright install chromium`.
- Demo pre-flight: `python -m pytest tests/e2e/test_demo_flow.py -m live -q`.
  Warm the transcription cache by running it once on the demo machine.
