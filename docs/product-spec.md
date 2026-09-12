# PracticeMap — product specification

## F01 — current frontend display override (2026-09-12)
The user's latest request supersedes the ribbon presentation below: show a faint
full-measure difficulty highlight using each measure's existing rating. Use a
multiply blend at 18% opacity so dark notation remains dark, with neutral
hatching for unrated measures. Remove opaque section chips from the score;
names and one-decimal ratings stay in the sidebar and hover details. Section
selection, grouping, and difficulty calculations are unchanged. Use American
English “practice” in application copy.


## Product promise
A violinist uploads sheet music and immediately understands where a piece becomes challenging, how it divides into musical ideas, and what to do to improve each passage. The sheet music remains the primary interface; advice appears beside the selected music.

## Initial assumptions
- Hackathon duration: assume 24–48 hours for planning, adjustable by the user.
- Instrument: violin. Initial input is clear printed solo violin notation.
- Inputs: scanned PDF, PNG, and JPEG; MusicXML is an additional reliable import path.
- Choose and disclose a realistic upload/page limit during planning. Support at least one complete printed page for real scan analysis.
- Users range from beginners to advanced players. Ask for experience, comfortable positions, and target tempo if known; make setup skippable.
- The main rating describes estimated passage demand under the stated tempo/context. User experience personalizes advice and can show a separate suitability note without silently changing the scale's meaning.
- No account is required. Store settings and self-reported practice progress locally; document how score data is stored and deleted.

## Required journey
1. Upload a supported scan or choose a clearly labeled example.
2. Show honest progress through recognition and analysis.
3. Present the original score divided into practice sections, with a continuous difficulty ribbon banded by section and aligned to the engraved measures.
4. Show each section's 0.0–10.0 rating and a concise explanation.
5. Click anywhere inside a section to select that whole passage and open its practice guidance in the sidebar.
6. Explore a phrase or a local trouble spot inside the passage without losing the passage context, and without either of them intercepting a click on the score.
7. Adjust a mistaken section or phrase boundary, or mark a recognition issue.
8. Practice a recommended exercise and report progress; reconnect the passage into the surrounding phrase.

## Segmentation: one musical idea per group
The user's priority is a coherent musical idea, not an arbitrary block of notation. The earlier 2–4-measure target is a soft starting heuristic. The later instruction that a group should not be two measures or ten lines long is interpreted as rejecting mechanically tiny or sprawling groups, not forbidding a genuine two-measure phrase. Make this interpretation explicit in the plan.

Use three distinct levels:
- Practice section: one or more adjacent phrases that ask for the same kind of
  work. This is the primary unit — what the score is colored by and what a click
  selects. Boundaries come from printed evidence (key/meter change, double bar,
  repeat), from a real step in difficulty, from a change in the dominant
  technical demand, or from the user's own split. A small rating change is not a
  boundary, and matching scores are not a reason to merge unrelated ideas.
  Sections tile the piece and never split a phrase. They are labeled by the
  measures they span and the demands measured in them; a formal name the
  notation does not establish is still forbidden.
- Phrase: one musical thought, inferred from melodic contour, closure, rests, cadential evidence, articulation, and context. Neither a slur nor an ordinary measure number automatically establishes a phrase boundary.
- Trouble spot: a short technical range inside a phrase, possibly one measure or two beats. Secondary guidance inside its section, never the default target of a click on the score.

Phrase boundaries can occur within measures and continue across systems/pages. Avoid forcing equal lengths. Give each inferred boundary a brief reason and an uncertainty indicator where appropriate. Provide split, merge, and boundary adjustment interactions.

Keep each phrase's structural range separate from its practice range. Extend practice through the first playable note of the next phrase when available. At the final phrase there is no next note. Handle rests, ties, repeats, and endings explicitly; do not fabricate a continuation. Structural phrase coverage must not contain accidental gaps or duplicate ownership even when practice ranges overlap.

## Difficulty ratings
Every analyzed section and phrase receives a number from 0.0 to 10.0 inclusive, displayed with exactly one decimal digit, for example 6.7. Each analyzed measure also receives a rating; those feed the section and phrase numbers and are visible on hover, but they do not drive a measure-by-measure heat map. Missing/unreadable data remains unrated; do not use 0.0 as a missing value.

Category mapping, an app heuristic rather than a validated grading system. The
color progression in design.md runs light green → yellow → orange → red →
near-black across the same 0–10 range:
- 0.0 ≤ score < 2.0: Beginner-friendly.
- 2.0 ≤ score < 4.0: Advanced Beginner.
- 4.0 ≤ score < 6.0: Competent level.
- 6.0 ≤ score < 8.0: Expert level.
- 8.0 ≤ score ≤ 10.0: Extremely, extremely hard.

The scale is absolute and shared across pieces. Never normalize one upload to
fill the range. An easy passage inside a difficult work keeps its own low
rating, and a beginner method page is expected to occupy only the bottom of the
scale.

Evaluate supported features: rhythmic density at the stated tempo, subdivision and syncopation, accidentals and tonal context, range, interval patterns, double stops/chords, articulation and bow-control demands, endurance, and interactions among challenges. Written leaps alone do not prove position shifts; pitches alone do not always determine strings. Use conditional explanations when needed.

Define a transparent initial rubric and phrase aggregation rule in architecture.md during T02. A long easy region should not hide a brief demanding obstacle: expose local peak difficulty as well as the phrase estimate. The phrase rating applies to the structural phrase, not the added overlap note. Decimal presentation does not imply scientific precision.

Document handling of partial measures, rests, unknown tempo, and missing features. If tempo is unknown, explain the notation-based estimate and allow recalculation when tempo is provided. Keep ratings deterministic for identical validated features and settings where feasible. Recognition confidence must never become a difficulty multiplier.

## Passage-specific practice sidebar
Every recommendation includes:
- Passage location: phrase name, measure labels, and beat/note range.
- What makes this passage challenging, tied to observed notation.
- The chosen technique and why it fits this challenge.
- Numbered physical/musical instructions a violinist can execute.
- A passage-derived example or simplified exercise when recognition is reliable.
- A starting pace rule, explicit beat unit, and adjustable time/repetition guidance.
- What to listen for: intonation, rhythmic evenness, tone, articulation, coordination, or continuity as applicable.
- A self-assessed success criterion and a sensible progression/regression rule.
- Return to original rhythm, bowing/articulation, tempo, and surrounding context.
- A source link and evidence category, available in expandable detail.

Prioritize one or two fitting techniques per trouble spot, with optional alternatives. Advice must go beyond 'slow down and repeat.' Use long-short/short-long variations for suitable even-note runs, plus additional researched techniques. Do not recommend every technique for every passage.

Success is self-reported improvement, not a guarantee of mastery. Include a later original-rhythm revisit rather than equating immediate fluency with durable learning.

## Recovery and exclusions
Offer a re-upload/crop or recognition-review path for poor scans. MusicXML import and the labeled example are alternatives, not silent replacements. Clearly identify any re-engraved view separately from the original scan.

MVP excludes handwritten recognition, full orchestral part extraction, live audio grading, automatic authoritative fingering, accounts, payments, and social features. Playback is optional; do not sacrifice score mapping or exercise quality to add it.

## Product acceptance
- A real supported scan produces analysis associated with its actual visible measures.
- A multi-system example retains correct region alignment on resize and zoom.
- Phrases represent musical ideas and can be edited, including a boundary inside a measure.
- Every successfully analyzed phrase displays one decimal digit; unreadable regions display 'Needs review.'
- The score has an uninterrupted ribbon within each system, banded by practice section, with one color and one rating per section wherever that section appears. Unreadable measures keep neutral hatching inside the band.
- Clicking anywhere inside a section — a measure, the section outline, or its ribbon band — selects that whole section, highlights its full extent, and opens its guidance. Different sections load different advice. Local trouble spots are distinguished and remain secondary.
- Suitable fast even-note passages receive complementary rhythm exercises with a return to the written music.
- A contrasting passage receives a different applicable technique or an honest explanation of insufficient evidence.
- Settings and progress persist, and example mode works without API credentials.
- Real-provider failure does not masquerade as successful upload analysis.
