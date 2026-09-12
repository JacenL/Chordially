# PracticeMap — authoritative delivery checklist

Status: demo-ready. C1–C6 and C8–C19 delivered. C20 splits the remaining work
into a backend track (B1–B6) and a frontend track (F1–F5); both are unstarted. All three segmentation
levels the spec requires are now implemented. C7's persistence half and
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
  - On the example at the assumed tempo: 3 trouble spots across 15 phrases (20%).
    **Correction, made in C14:** this entry originally claimed restraint as
    though it were a guarantee about all repertoire. It is not. On the Mozart
    MusicXML page the same rule fires on 77% of phrases — and inspection shows
    it is right to: a 7.4 measure inside a 3.5 phrase is exactly what a trouble
    spot is for. Density tracks how uneven the music is. The test that asserted
    `len(spots) < len(phrases)` was replaced, because it passed at 30 of 35
    while proving nothing.
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

## C11 — Evidence for the ratings: a calibration check and a usable review packet
- [x] Complete
- Dependencies: C10.
- Why: C10 made the rubric inspectable. This asks whether it is any good. The
  answer cannot come from inside the repository, but one external reference is
  available and one document has to exist before a violinist can be asked.
- Evidence: **219 tests pass**, 7 new.

### The calibration check

Wohlfahrt printed the Op. 45 studies in increasing order of difficulty, and the
fixture page carries Etude 2 and Etude 3 — so the editor's own ordering is a
reference the rubric can be measured against. `tests/unit/test_calibration.py`
locates the boundary from the printed key and meter change (4/4 in C to 2/4 in
G) rather than a hard-coded measure number, so the test keeps meaning what it
says if recognition or segmentation changes.

| Tempo | Etude 2 | Etude 3 | Gap |
|---|---|---|---|
| 60 BPM | 3.58 | 5.07 | +1.49 |
| 90 BPM (assumed) | 4.00 | 5.71 | +1.71 |
| 160 BPM | 4.83 | 6.86 | +2.03 |

**The app agrees with Wohlfahrt at every tempo.** The ordering is not an artifact
of the assumed 90.

**What this establishes:** ordinal agreement with one editor, on one pair of
adjacent studies, from one page. **Etude 3 contributes 7 rated measures against
Etude 2's 25**, because much of the second half of the page could not be read. A
real signal and a weak one. It does not establish that 4.0 and 5.7 are the right
numbers, that the gap is the right size, or that any of it transfers beyond a
beginner's etude book. A test asserts the sample imbalance explicitly, so if the
second study ever gains enough rated measures the test fails and the caveat gets
revised upward rather than silently going stale.

### The review packet

`fixtures/expected/review-phrases.md` is now a document a teacher can mark up in
about twenty minutes: what the app claims and does not, blank fields per phrase
for the reviewer's own 0–10 and what the app missed, three questions where
disagreement would change something, and a table mapping each possible answer to
the exact constant it would move — `WEIGHTS`, `CATEGORIES`, `_saturate`, or the
segmentation evidence weights.

Regenerable with `python scripts/build_example_fixture.py --review-only`, which
reads the committed analysis and touches no provider — rewording a document
should not risk perturbing a fixture 200-odd tests are pinned to.

### One thing fixed while writing it

The packet was dumping twelve lines of raw HTTP 400 JSON, request IDs included,
at a violin teacher — and those errors were stale, describing a credit blocker
resolved in C4. Recognition shortfalls are now summarised in plain language
(8 read and rejected, 21 never read, 2 sections that disagreed with the page),
with the raw errors left in the analysis JSON where they belong.

## C12 — MusicXML import
- [x] Complete
- Dependencies: C4.
- Discharges T04's remaining acceptance clause: MusicXML as a reliable
  alternative import path.
- Evidence: **244 tests pass**, 25 new.
  - Measured on `fixtures/scores/mozart-k156-mvt1.mxl` (Mozart K.156 mvt 1,
    Violin I): 12 systems, **145 of 145 measures confident and rated**, ratings
    spanning 0.0–7.6, 35 phrases. **No measure is "Needs review" and none is
    hatched** — there is nothing to misread, so nothing is left unknown. Next to
    the scan, where 18 of 61 measures are unrated, this is the honest evidence
    that the difficulty analysis is not downstream of OCR quality.
  - Zero provider calls. The provenance line says notes were read from the file
    rather than reporting "0 sections read live", which would describe a
    recognition run that never happened.
  - What was not analysed is disclosed: the file has 4 parts and Violin I was
    taken; the part has 180 measures engraving to 2 pages and page 1 was used.

### Why the page is an SVG

The viewer positions every overlay against a page image, and MusicXML has none.
Three routes were tried:

1. **Rasterise Verovio's SVG with PyMuPDF, reuse the OpenCV pipeline** — fails.
   PyMuPDF opens the SVG and renders a blank page (`min == max == 255`); its SVG
   support does not handle Verovio's `<use>`/defs output.
2. **Rasterise through headless Chromium** — works, but would make a browser a
   runtime dependency for the sake of throwing away vector output.
3. **Read the geometry out of the SVG and serve the SVG as the page** — chosen.
   Verovio draws staff lines and barlines as two-point paths, so a measure box is
   arithmetic rather than detection: left edge from the previous barline, right
   from its own, vertical extent following the same staff-plus-margin rule
   `cv_geometry` uses on scans. The browser renders SVG natively at any zoom.

Geometry from this path is exact, and a test asserts measure boxes are flush and
ordered within each system — the same property the ribbon depends on.

### Two defects found while building it

1. **Verovio cannot initialise its fonts off the main thread.** A toolkit
   constructed inside the analysis worker reported "Bravura font could not be
   loaded" and every subsequent load returned False, so uploads engraved
   nothing while the same code worked in a script. Fixed with one shared
   toolkit constructed at import — which happens on the main thread — behind a
   lock the toolkit needs anyway, since it holds the loaded score as mutable
   state and two concurrent uploads would interleave inside it.
2. **Every measure came back unrated on the first working run.** `build_score`
   takes meter from `signatures_by_system`, deliberately not from per-measure
   transcriptions, because on a scan a mid-staff crop cannot see a signature.
   Passing `None` there left every measure without a meter and therefore without
   a rating. The importer now supplies the signature in force at each system's
   first measure, and a test asserts every system carries one.

## C13 — Interface polish
- [x] Complete
- Dependencies: C12.
- Scope: five specific problems observed in rendered screenshots, not a redesign.
- Evidence: **244 tests pass**; verified in Chromium at 1440, 1100 and 820px with
  no horizontal overflow at any width and no JavaScript errors.

1. **The toolbar was unreadable below ~1200px.** Zoom, tempo, the phrase toggle
   and a six-item legend shared one wrapping row. The legend now has its own row
   under the controls.
2. **Labels buried the notation they described.** The Mozart page carries 35
   phrases and ~30 hard spots; at 0.72 opacity that is 65 chips over the music.
   Hard-spot chips are now hidden until their spot is selected — the outline
   still shows the region — and phrase chips sit at 0.5 until hovered or
   selected. A stale `opacity: 0.85` further down the file was overriding the
   intended hidden state and is gone.
3. **Collapsing the notices gained nothing.** `.score-pane` had a fixed
   `max-height: calc(100vh - 150px)`, so it was already at its ceiling no matter
   what sat above it. The score column now owns the viewport height and the pane
   takes what is left: collapsing the notices hands back **180px**, about a whole
   system on a laptop.
4. **The rating scrolled out of view.** Selecting a phrase from the bottom of the
   sidebar list left the rating and factors above the fold. The selection panel
   is now brought back into view.
5. **Stale copy contradicting a shipped feature.** The boundary panel still read
   "Editing them arrives with phrase editing" — directly above the Split and
   Merge controls delivered in C5. It now points at them.

## C14 — Two defects in shipped work, and one corrected claim
- [x] Complete
- Dependencies: C12.
- Evidence: **254 tests pass**, 10 new.

### Defect — a phrase of silence, rated green

On the Mozart page, Phrase 15 (measures 60–61) and Phrase 18 (measures 72–74)
contained nothing but rests. Both rated **0.0, "Beginner-friendly"**, drew green
ribbon over the silence, and offered practice instruction for a passage with
nothing to play. 14 of 145 measures on that page are rest-only, so this was not
an edge case.

Fixed in `segment_score`: a range with no sounded note is absorbed into the
phrase before it, or the one after it when it starts the piece. The bars keep
their place, their 0.0 rating and their ribbon segment — a rest bar genuinely is
easy to play — they simply stop being an idea of their own. Mozart goes from 35
phrases to 33, both silent phrases gone, coverage still gapless and
non-overlapping.

Tested against four patterns (silence in the middle, leading, trailing,
alternating) plus the degenerate case of a score that is *entirely* rests, which
must not loop or return nothing.

### Defect — dead code

`musicxml_source.py` ended with `_exact_duration`, which no test called and
which carried a `del NOTE_VALUE_FRACTIONS` line whose only purpose was to stop
an unused import looking unused. Both removed.

### Not a defect — trouble-spot density

Investigated and **left alone**. Six tighter rules were measured — higher
margin, page-relative floor, standard-deviation gate, top-quartile gate,
category-crossing — and every one still left Mozart between 69% and 80%. What
the rule picks is defensible on inspection, so the detection stands and the
overstated claim in C9 above was corrected instead.

## C15 — Structural sections: the third and last level
- [x] Complete
- Dependencies: C9, C14.
- Discharges the product spec's three-level requirement. `level="section"` has
  been declared in `src/schemas/score.py` since C2 and nothing had ever emitted
  one; with phrases (C2) and trouble spots (C9) this completes the set.
- Evidence: **263 tests pass**, 9 new.
  - On the Wohlfahrt scan: **exactly 2 sections**, split at measure 29 — the
    real key and meter change where Etude 2 (4/4, no sharps or flats) becomes
    Etude 3 (2/4, 1 sharp). The same boundary `test_calibration.py` uses.
  - On the Mozart MusicXML page: **0 sections**, correctly. One meter and one key
    throughout means no evidence, and wrapping the piece in an invented
    "Section 1" is exactly the fabricated formal label the spec forbids. A test
    pins this.
  - Labels report printed evidence only — "2/4, 1 sharp", never "G major", since
    a key signature does not establish a mode. A test asserts no section label
    or reason contains "exposition", "chorus", "theme", "major" or "minor".

### Two decisions worth recording

**Sections are not another outline layer.** A section spans five systems, and
five more rectangles over the notation would undo C13's decluttering. A section
is a grouping header in the sidebar plus one double rule on the score at the
point where its evidence sits.

**Sections snap to phrase starts, so they cannot be finer than a phrase.** The
consequence, found by a test that initially failed: on a page short enough to be
a single phrase, a signature change inside it yields no sections rather than a
boundary cutting the phrase in half. The three levels nest or they are not
levels. That constraint is now asserted explicitly.

The selection chain is three deep (section ← phrase ← trouble spot), so
`parentOf` in `src/static/app.js` walks to the nearest ancestor-or-self that is
a *phrase* rather than up exactly one level — going up one from a phrase would
have outlined twenty-eight measures as "context". The breadcrumb shows whatever
levels exist: "Measures 1–28 › Phrase 1 ›".

## C16 — The rating was inflated by counting, not by calibration
- [x] Complete
- Dependencies: C15.
- Scope: the difficulty rubric only. No interface change beyond the colour
  anchors the rating maps onto.
- Evidence: **293 tests pass**, 39 new (26 in `tests/unit/test_rubric_20.py`,
  one per cause plus the counter-cases; 4 calibration; the rest colour/payload).

Straightforward first-position eighth-note studies were rating **3.2-5.1** on a
0-10 scale — "Advanced Beginner" through "Competent level" for the second study
in a beginner's method book. Seven features were counting the wrong thing. Each
is fixed at its source; nothing was subtracted from the total and no category
label was moved. `docs/architecture.md` records all seven with their
before/after.

Measured on the same scan at the same assumed tempo:

| | Etude 2 (4/4, C, eighths) | Etude 3 (2/4, G, sixteenths) | Page peak |
|---|---|---|---|
| Rubric 1.0 | 4.00 mean | 5.71 mean | 6.8 |
| Rubric 2.0 | **1.19** mean | **2.99** mean | **3.5** |

The ordering Wohlfahrt printed the studies in survives, with the gap slightly
wider than before (1.71 to 1.80), and it survives at 60, 90 and 160 BPM.

The single largest contributor was syncopation: every second eighth note in 4/4
sits off the quarter-note beat, so straight eighths scored 0.50 and straight
sixteenths 0.75 on a feature meant to find displaced accents. The second was
register, whose "no demand" ceiling was the *open* E string rather than the top
of first position, charging ordinary first-position writing up to 1.54 points —
measure 14 of the fixture, which reaches A5 and never leaves first position, was
the visible symptom.

Two defects found on the way and fixed in the same checkpoint:

- **Slurs were never read from MusicXML.** `_note_event` did not set the field,
  so the bow-demand feature was silently zero for every import. It now reads the
  part's slur spanners; the Mozart fixture has 100 slurred notes of 381.
- **`alter` meant two different things in the two adapters.** MusicXML reported
  sounding pitch, the vision model reported printed accidentals, and
  `NoteEvent.midi` was correct for only one of them. Both are normalized to
  sounding alteration at `build_score`, where the authoritative key signature is
  known. The committed example was migrated by
  `scripts/refresh_example_analysis.py`, which needs no API key because it works
  from notes already in the fixture.

### Not fixed, recorded instead
A natural sign cancelling a key-signature sharp or flat is written the same way
as no accidental at all in the provider wire format, so it reads as the
key-signature pitch. Expressing the difference would mean changing the
transcription contract and invalidating the cache; the limitation is documented
in `build_score` instead.

## C17 — Colour and select a practice passage, not a measure
- [x] Complete
- Dependencies: C15, C16.
- Evidence: **315 tests pass**, 22 new; verified in Chromium at 1440px and 400px
  with no JavaScript errors.

The ribbon was a sixty-one-slice heat map whose boundaries fell wherever a
rating happened to tick by a tenth — a picture of the rubric's rounding rather
than of the music. The coloured and selectable unit is now a **practice
section**: one or more adjacent phrases that ask for the same kind of work.

`src/features/segmentation/sections.py` groups phrases while the work stays the
same and splits where a printed key or meter change, a real step in difficulty
(0.8 on the running mean, or 1.5 of spread), or a change in the dominant demand
says it has changed. A user's own split or merge always wins. A small rating
change is never a boundary, and matching scores are never a reason to merge
unrelated ideas: the demand behind the number has to match too.

On the fixture page: **5 passages, 22 ribbon bands, 61 measures.** Etude 2 is
one passage of 28 measures at 1.6 across five staff systems, each fragment
carrying the same identity, rating and colour.

### What a click does now
Clicking a measure, a passage outline or a ribbon band selects the whole
passage, highlights every fragment of it on every system, and loads that
passage's guidance. Two clicks inside one passage give the same answer — a
trouble spot no longer intercepts a measure click, which was the behaviour that
made "click a measure, get advice about this passage" untrue. Phrases and hard
spots stay reachable from the sidebar and from their own outlines, under an
"Inside this passage" panel, and selecting one keeps the passage in the
breadcrumb and outlined on the page.

### Three decisions worth recording

**Sections cannot be stored, so edits store the decision instead.** They group
phrases by difficulty and by demand, and both move with tempo, so a section
saved at 90 BPM is the wrong grouping at 160. They are re-derived on every
request. A split is therefore recorded as "this measure begins a passage",
keyed by measure id, which survives re-derivation, retuning and phrase edits.
A test pins that an edit survives a tempo change.

**Splitting a passage can split a phrase.** A passage boundary lands on a phrase
start or it does not land, so asking for one mid-phrase is asking for that idea
to be two ideas — and `split_section` does exactly that first, rather than
silently refusing or silently cutting across the level below.

**The C15 rule is superseded, and its protection kept.** A page with no printed
signature change used to get no sections at all, because wrapping it in "Section
1" would be a formal claim the notation does not support. Passages are labelled
by the measures they span and by demands measured inside them; a test asserts no
label or reason contains "exposition", "chorus", "theme", "major", "minor" or
"verse". The Wohlfahrt page went from 2 sections to 5.

### Unknown stays distinct from easy and from hard
A stretch nobody could read forms its own passage rather than inheriting a
neighbour's colour, and a single unreadable measure inside a rated passage cuts
its band and keeps neutral hatching. That is the only thing that interrupts a
band. A test asserts no passage mixes readable and unreadable measures.

Two visual corrections made while looking at the rendered page: the passage tint
was washing over the notation (five tinted systems at once), so an unselected
passage now has no fill at all and states itself with a coloured left edge; and
unreadable passages were hatched a third time on top of the per-measure and
ribbon hatching, which obscured the very notation a reader needs in order to
judge whether recognition was right.

### Colour
The progression is **light green → yellow → orange → red → near-black**, five
anchors evenly spaced at 2.5 points. (C17 first shipped a six-anchor
light-green → green → yellow → orange → red → maroon ramp; the five-stop version
above is the later explicit decision and replaced it in the same branch.) The
anchors sit on a 2.5 grid while the category cut points sit on 2.0, so a
category spans part of two ramps — ratings and accessible labels are shown
alongside colour everywhere, so the colour is never the only statement.

## C18 — A front page that answers the reader's question first
- [x] Complete
- Dependencies: C17 (the copy describes passages, which did not exist before it).
- Evidence: **324 tests pass**, 9 new in `tests/e2e/test_landing_page.py`;
  inspected in Chromium at 1440, 820, 520, 390 and 360px with zero horizontal
  overflow at every width and no JavaScript errors.

The page opened with two equally weighted cards — "Your own scan" and "Example
score" — so the reader had to choose between them before understanding either,
and the answer to "what does this do for me?" sat under three paragraphs about
transcription services, file size limits and which measures come back
unreadable.

Now: a headline, a one-sentence lede, **one** primary action, **one** secondary
one. The upload target is large and doubles as a drop zone. "Try the example
score" is a quiet link beneath it rather than a competing card. Three short
lines say what the reader gets. Everything technical is folded into three
expandable summaries — what you can upload, what happens to your file, what the
rating does and does not mean.

### Nothing honest was removed to get there
A cleaner screen that has lost its disclosures is the same page with the true
parts deleted, so each one is pinned by a test:

- Supported formats, the page limit and the 20 MB cap stay **visible** without
  opening anything.
- The data-handling disclosure — a scan goes to Anthropic, MusicXML never leaves
  the machine, nothing is stored — is one click away and asserted by text.
- Upload progress still names the stage actually running and still explains why
  there is no percentage.
- A rejected upload still reports itself with a recovery action, stays on the
  page, and is never silently replaced by the example. That test uploads a real
  text file and checks the URL never reaches `/score/`.
- The credential status still says what this instance can actually do, and now
  says MusicXML and the example work without credentials rather than implying
  nothing does.

### Drag and drop
Added as a convenience over the picker, not instead of it: the file input stays
the accessible, keyboard-reachable path, and a drop assigns to it so there is
one source of truth for which file is about to be sent. A multi-file drop takes
the first rather than analyzing something the user did not point at, and a drop
outside the zone is swallowed so the browser does not replace the app with a PDF
viewer.

### Styling
No framework and no new dependency. The existing custom properties, serif
display face and warm paper ground are unchanged; the landing rules replace the
old `.empty-state` block in `src/static/app.css`.

## C19 — copy that described superseded behaviour
- [x] Complete
- Dependencies: C16, C17, C18.
- Why: C16 re-based the ratings and C17 replaced the six-anchor ramp, but four
  reader-facing places still described the old behaviour. One of them was a
  measured claim in the demo script that a test now contradicts, so following
  the script would have meant saying something false out loud.
- Changed:
  - `docs/demo.md` known limitations quoted Etude 2 averaging 4.0 and Etude 3
    5.7 — rubric 1.0 numbers. Measured again through `study_means`: **1.19 and
    2.99** at the assumed 90 BPM, from 25 and 7 rated measures.
    `test_calibration.py` asserts the first is below 2.0, so the doc and the
    suite disagreed.
  - "light green through maroon" in `docs/demo.md`, `README.md`,
    `fixtures/README.md` and `src/app/templates/index.html` — the last of these
    on the landing page C18 had just rewritten. The shipped ramp ends near-black
    at 10.0. README also still said six colour anchors; there are five.
  - `docs/demo.md`'s start-screen beat described the two equally weighted cards
    C18 replaced. It now describes the single primary target, the drop zone, the
    limits visible without opening anything, and the disclosure under "What
    happens to your file".
- Evidence: `python -m pytest -q` → 303 passed, 20 skipped, 5 deselected. The
  20 skips are the Playwright suite on a machine without Chromium; no test pins
  any of the changed strings, and the calibration numbers were re-measured
  rather than copied from an earlier report.
- Not changed: `CLAUDE.md` and `prompts/01-plan.md` also say "maroon".
  `docs/design.md` is the authoritative colour document by CLAUDE.md's own
  instruction, and the prompt file is a historical record of what was asked.

## C20 — Split the remaining work into a backend and a frontend track
- [x] Planning complete. The tracks below are unchecked and unstarted.
- Why: two developers now. The split follows the seam the architecture already
  has — recognition and analysis are Python behind a contract, presentation is
  four absolutely-positioned layers over a page image — so the two tracks touch
  almost disjoint file sets.
- File ownership, to keep the two out of each other's commits:
  - Backend: `src/schemas/`, `src/features/`, `src/server/`, `src/config.py`,
    `scripts/`, `tests/unit/`, `tests/integration/`.
  - Frontend: `src/static/`, `src/app/templates/`, `tests/e2e/`.
  - `src/app/main.py` is shared. Route additions only; keep them small.
- What each developer needs:
  - Frontend needs **no API key**. `fixtures/pages/wohlfahrt-p3.png`,
    `fixtures/expected/wohlfahrt-p3-analysis.json` and
    `fixtures/scores/mozart-k156-mvt1.mxl` are committed, so `/score/example`
    and the MusicXML import both run from the checkout. They do need
    `python -m playwright install chromium`; without it 20 e2e tests skip and
    prove nothing.
  - Backend needs `.env` with `PRACTICEMAP_ANTHROPIC_API_KEY` for B3/B4, and an
    Audiveris install for B2.

### Backend track

#### B1 — Where the ribbon may be drawn (do first; the frontend track waits on it)
- [ ] Not started. Dependencies: none. Small.
- Problem, measured on `fixtures/pages/wohlfahrt-p3.png`: `view_model.py` places
  the ribbon in the bottom 13% of each system band and its comment claims that
  sliver is whitespace. It is not. All 11 systems carry ink inside that band —
  8,422 dark pixels on system 6, ink in every row of the band on systems 4 and 6.
  The staff's bottom line sits ~60px above the band, but stems, beams, fingering
  digits and the treble clef descender reach 92–123px below it.
- Deliver: a per-system `ribbon_region` (page-relative, percentages only) plus a
  boolean `ribbon_overlaps_ink`, computed from the ink profile `cv_geometry`
  already builds. Place the band below the lowest ink row inside the system
  region where that fits; where it does not — which is the case on this page —
  keep a documented minimum height and set the flag rather than silently
  overlapping.
- Acceptance: for every system of both fixtures, the emitted band either
  contains zero ink pixels or has the flag set, asserted by a test that counts
  ink in the emitted rectangle rather than trusting the constant; bands stay
  flush and gapless horizontally; no style string carries a unit other than `%`
  (the existing test); the false comment in `view_model.py` is corrected.
- Do **not** decide the visual treatment here. That is F1.

#### B2 — Audiveris as a third recognition adapter
- [ ] Not started. Dependencies: none.
- Why: the scan path is the weak one, and Audiveris emits MusicXML — the format
  the importer already reads exactly. It runs locally, needs no key, has no
  credit balance to exhaust, and is deterministic. Two documented blind spots
  disappear with it: MusicXML expresses chords, so `double_stops` stops being
  permanently 0.0, and a natural cancelling a key-signature accidental becomes
  expressible.
- Cost, stated before starting: Audiveris 5.6 needs Java 21 (newer builds 24/25)
  and is not pip-installable. The installers bundle a JRE, so a demo machine is
  fine, but `pip install -r requirements-dev.txt` stops being the whole setup —
  the constraint that made C1 choose a pure-Python stack. Published accuracy is
  ~88% note-level strict F1 on clean engraved pages, ~58% mean on real scanned
  systems with usable output on 50 of 60, ~50% on photographs. Better than
  nothing on a clean 300dpi scan; not a guarantee.
- **B2a — spike, no code path switched.** Install it, run
  `Audiveris -batch -export -output <dir> -- fixtures/scores/wohlfahrt-op45-bk1-p3.pdf`,
  and record: measures found against geometry's 61, how many pass
  `validate_measure` against the meter, and a by-eye pitch spot-check of two
  systems against the scan. Acceptance: a measured comparison against the
  current vision path on the same page, and a written go/no-go in the style of
  C1. A spike that reports worse numbers and stops is a successful spike.
- **B2b — the adapter**, only if B2a says go. `audiveris_source.py` behind the
  same contract as `claude_adapter.py`, joined to `cv_geometry` measures by
  index through the existing count cross-check, selected by config with the
  vision model still available. Acceptance: the fixture PDF reaches at least the
  43 of 61 rated measures the live vision run achieved; the provenance line says
  the notes were read locally and nothing was sent to any service; zero provider
  calls; and with Audiveris absent the upload fails with a named recovery action
  rather than a traceback.

#### B3 — Stop implying pitch was verified
- [ ] Not started. Dependencies: none; strengthened by B2b.
- Problem: `validate_measure` checks two things — every note inside the violin's
  range, and durations summing exactly to the meter. **Nothing checks pitch.** A
  measure read with the right rhythm and the wrong notes is marked `confident`
  and rated. "87% validated" means arithmetically consistent, not correct.
- Deliver either a cross-check (two adapters reading the same measure, with
  disagreement marked) or, at minimum, wording that distinguishes rhythm
  validated from pitch unverified, carried into the sidebar text and the docs.
- Acceptance: no surface claims a pitch was verified when it was not; if the
  cross-check is built, a measure where the adapters disagree is not presented
  as confident; `docs/demo.md` and `README.md` updated to match.

#### B4 — Rebuild the example fixture from a complete reading
- [ ] Not started. Dependencies: B2b or a funded key.
- Problem: the committed example has 14 confident, 18 uncertain, 8 unreadable
  and **21 measures never read** — scar tissue from the C2 credit outage. Only
  32 of 61 are rated in what the demo shows, while the C4 live run reached 43.
  The demo is showing the app at its worst for a reason that no longer exists.
- Acceptance: zero `not_attempted`; at least 43 of 61 rated; regenerated by the
  documented script rather than hand-edited; the calibration test still holds
  (Etude 2 below 2.0, Wohlfahrt's ordering preserved at 60/90/160 BPM); every
  fixture-pinned number in `docs/`, `README.md` and `fixtures/README.md`
  re-measured, not adjusted by eye.

#### B5 — Persistence and self-reported progress storage (C7's remaining half)
- [ ] Not started. Dependencies: none.
- SQLite under `work/` (gitignored), versioned schema, keyed by the existing
  content `fingerprint`. Stores boundary and passage decisions, the supplied
  tempo, and self-reported progress. The uploaded bundle itself stays in memory:
  the transcription cache re-derives a page in about two seconds, while a stored
  bundle would go stale the moment the rubric version changes.
- Acceptance: an edit, a tempo and a progress report survive a real server
  restart; two scores cannot read each other's rows; a decision stored under a
  superseded rubric version is discarded rather than replayed; progress never
  changes a rating, a colour or a category, asserted by a test; a documented
  delete path, and the storage location written into `README.md`.

#### B6 — double_stops, for real
- [ ] Not started. Dependencies: B2b.
- The feature is wired, weighted and always 0.0 because the transcription format
  has no simultaneities. MusicXML has chords. Acceptance: a real double-stop
  passage rates above zero; the blind-spot entry is removed from the rubric
  disclosure only when the feature actually reads them.

### Frontend track

#### F1 — Notation legible under the ribbon
- [ ] Not started. Dependencies: B1 for the exact geometry, but not blocked by
  it — `mix-blend-mode: multiply` on `.ribbon-segment` lets the ink read through
  the colour today and can ship first.
- Acceptance: on both fixtures at 1440, 820 and 390px, beams, clef descenders
  and fingering digits inside the band stay readable in an inspected screenshot;
  the ribbon still reads as one continuous band per system with the documented
  five-anchor colours; unrated hatching stays distinguishable from both ends of
  the scale; zero horizontal overflow and no JS errors.

#### F2 — The rest of the layer legibility pass
- [ ] Not started. Dependencies: none.
- `.measure--unrated::after` hatches a whole measure at `inset: 0`, the passage
  hover tint fills 9%, and chips sit over the staff. C13 and C17 each removed one
  wash; this finishes the job.
- Acceptance: nothing puts a full-bleed fill over notation; hover and selected
  states state themselves at the edges or in the margin; the existing e2e suite
  still passes with Chromium installed.

#### F3 — Progress reporting UI
- [ ] Not started. Dependencies: B5's endpoint contract (agree it on day one,
  build against a stub).
- Three self-reported states per passage with a timestamp, plus the later
  original-rhythm revisit the spec asks for.
- Acceptance: keyboard reachable and screen-reader labelled; survives reload;
  the wording says self-reported and never implies mastery or certification; the
  panel never displays progress as changing a difficulty number.

#### F4 — Boundaries inside a measure
- [ ] Not started. Dependencies: a backend edit op if the existing one is
  measure-keyed only.
- The last partially-met product acceptance criterion. Anchors already carry
  `(measure_id, note_index)`; only the interface is missing.
- Acceptance: a boundary can be placed between two notes inside a measure and
  the phrase re-rates; existing refusals stay honest; the limitation line in
  `docs/demo.md` is deleted only once this is true.

#### F5 — Install Chromium and re-verify the browser claims
- [ ] Not started. Dependencies: none. Do this first, it is five minutes.
- `python -m playwright install chromium`. Until then 20 e2e tests skip, which
  means C17's and C18's browser evidence cannot be reproduced on this machine.

### Contracts to agree before either track starts
1. `ribbon_region` and `ribbon_overlaps_ink` per system in the view model
   (B1 produces, F1 consumes).
2. The progress endpoint's path and body shape (B5 produces, F3 consumes),
   measure-keyed so it survives re-derivation at a new tempo.
3. No commit touches both `src/features/score_viewer/view_model.py` and
   `src/static/app.css`. If a change needs both, it is two commits on two
   branches meeting at `practice-map-build`.

## Known bugs
None open. Two correctness bugs found during C2 were fixed in the same
checkpoint and are recorded above. A lack of recorded bugs does not mean the
application has been tested.

## Git delivery blockers
None. C1 and C2 are confirmed on origin/practice-map-build.

## Handoff
- Next action: the C20 tracks. Backend starts at B1 (small, and F1 wants its
  output) then B2a's Audiveris spike; frontend starts at F5 (install Chromium)
  then F1. C7's remaining half is now B5.
- Outstanding external setup: none. The Anthropic credit blocker is cleared and
  live recognition is verified working.
- Last meaningful validation: `python -m pytest -q` → **303 passed, 20 skipped,
  5 deselected** on a machine without Chromium. The 20 skips are the Playwright
  suite and the 5 deselected are the `live` demo-flow set; with Chromium
  installed the offline total is 323. Install it with
  `python -m playwright install chromium`.
- Not yet obtained: a Mendelssohn Violin Concerto excerpt. The rubric's high end
  is currently evidenced by constructed notation in `test_rubric_20.py` and by
  the real Mozart K.156 import, not by a demanding concerto page. Dropping a
  MusicXML or PDF excerpt into `fixtures/scores/` is all that is needed to check
  the top of the scale against real notation.
- Demo pre-flight: `python -m pytest tests/e2e/test_demo_flow.py -m live -q`.
  Warm the transcription cache by running it once on the demo machine.


## F01 — readable difficulty highlights and American English
- Branch: `fix/frontend-score-highlights`, based on `1d55985`.
- Scope: frontend templates, styles, selection wiring, displayed technique copy,
  and relevant browser/integration checks. No recognition/rating/grouping changes.
- Replaced opaque ribbon bars with multiply-blended, 18%-opacity measure fills;
  removed overlapping section chips and duplicate hatching. Ratings and section
  selection remain available through the existing sidebar and hover controls.
- Validation: 20 real Chromium browser tests passed (viewer and landing page);
  64 integration/practice tests passed, one live-provider test deselected.
  `git diff --check` passed. No live recognition calls were made.
- Delivery: ready to commit on the frontend branch; no shared-branch push or merge.

### F01 follow-up — tighter highlight height
- Reduced the decorative highlight to 84% of its previous height, centered on
  the measure (8% inset per edge). Hit targets and analysis geometry stay intact.
- Validation: all 11 viewer browser tests passed; diff whitespace check passed.
- Delivery: local frontend branch; previous GitHub authentication blocker remains.


## Frontend — measured upload and recognition progress
- Replaced the text-only loading area with a labelled native progress bar.
- Upload uses browser byte-transfer events; recognition uses the backend's
  existing “read N of M sections” reports, labelled completed requests (not
  successfully recognized measures). Percentages are per phase, never an ETA.
- Stages without counts remain indeterminate; only a done job opens the score.
- Prevented file replacement by drag/drop during an active upload.
- Backend job contracts and recognition code unchanged. All 11 landing-page
  browser tests passed, including count updates, indeterminate stages, mobile
  width, failure recovery, and done-only navigation. Diff check passed.
- Delivery: local frontend branch; GitHub push remains blocked by authentication.
