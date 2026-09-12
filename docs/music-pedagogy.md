# PracticeMap — research and technique foundation

## Evidence policy
Use primary music-practice research and identifiable violin teachers' own materials. Distinguish experimental findings, qualitative reports, teacher pedagogy, and app heuristics. Summarize in original language and link sources. Do not manufacture citations or imply that a source validates the app's numeric difficulty scale.

The following are researched starting points, not a completed systematic review. During T01, inspect these sources and research the additional candidate techniques below. If web access is unavailable, state the limitation and retain only supported claims.

## Starting sources

### S01 — Rhythm and accent practice
Simon Fischer, 'Practicing in rhythms and accents,' Basics, August 2011.
https://www.simonfischeronline.com/uploads/5/7/7/9/57796211/242_august_2011_rhythm_practice.pdf

Evidence: violin teacher pedagogy. Describes complementary dotted rhythms, varied pattern starting points, and attention to pitch, sound, timing, and ease. Supports including targeted rhythm/accent exercises; it is not a controlled trial proving a universal improvement rate.

### S02 — Interleaved practice
'Optimizing Music Learning: Exploring How Blocked and Interleaved Practice Schedules Affect Advanced Performance,' 2016.
https://pmc.ncbi.nlm.nih.gov/articles/PMC4989027/
https://doi.org/10.3389/fpsyg.2016.01251

Evidence: small study involving ten advanced clarinetists. Results favored interleaving when ratings differed, with variation across raters. Use as limited support for offering passage alternation and later revisits, not proof of an optimal violin schedule.

### S03 — Slow practice and its limits
Emma Allingham and Clemens Wöllner, 'Putting practice under the microscope: The perceived uses and limitations of slow instrumental music practice,' Psychology of Music, 2023; first published online in 2022.
https://doi.org/10.1177/03057356221129650

Evidence: qualitative questionnaire research on musicians' perspectives. Supports framing slow practice around specific purposes and acknowledging possible differences between slow and fast execution. It does not establish a universally optimal starting tempo or increment.

## Initial technique: complementary rhythmic variation
ID: rhythm-pairs
Status: supported by S01; detailed application rules below are app design choices.

Applies to: suitable runs of equal-duration notes with reliable pitches and grouping.
Goal: focus coordination on alternating neighboring transitions.
Instructions:
1. Select a small complete group from the actual passage.
2. Keep pitch order; temporarily alternate long-short durations.
3. Reverse the pattern to short-long.
4. Listen for accurate pitch, precise rhythm, clean sound, and ease.
5. Restore the original even durations and original articulation.
6. Connect the group to its surrounding phrase and revisit later.

For a verified pair of sixteenth notes, one possible temporary pattern is dotted-sixteenth plus thirty-second; reverse it for the complement. This preserves the pair's total duration. Compute durations exactly, show the beat unit, and label the pattern as a practice transformation. This example is an app illustration, not a quotation from S01.

Do not transform ties, rests, tuplets, unequal rhythms, or conflicting multi-voice durations using a blind pairwise rule. Either support their semantics explicitly or choose a different exercise. Do not invent exact notes when transcription is uncertain.

## Candidate techniques to research before enabling
| ID | Possible trigger | Proposed exercise focus | Required caution |
|---|---|---|---|
| accent-groups | Reliable even-note run | Temporary grouped/displaced accents | Restore original accents and phrasing; S01 is a starting source |
| short-bursts | Long fast passage | Short fluent groups, then connect | Research application and pacing; avoid tension |
| transition-loop | Local stumble or inferred obstacle | Small range spanning the transition | Explain why this transition was selected |
| shift-isolation | Annotated or user-confirmed position change | Prepare and land on target pitch | Do not infer a definite shift from interval size alone |
| bow-only | Confirmed string sequence | Practice bow path using open strings | String assignments must be supported |
| intonation-reference | Tonal pitch relationships or double stops | Compare with a suitable reference pitch | Choose reference from harmonic context |
| subdivision | Syncopation or complex subdivision | Count/tap a reliable subdivision, then play | Preserve meter and distinguish tuplets |
| slow-with-goal | Dense unfamiliar information | Isolate one listening/coordination objective | S03 supports purposes/limitations, not exact dosage |
| alternate-passages | Several established practice targets | Alternate short focused blocks | S02 transfer to violin is limited |
| reconnect-overlap | Neighboring phrases | Play through boundary into next first note | Preserve structural range and repeat semantics |

For each enabled technique, add a directly supporting source, applicability rules, step-by-step instructions, exclusions, and progression criteria. Disable unsupported techniques or clearly label them as unvalidated app heuristics instead of claiming research support.

## Structured technique records
When implementation begins, put machine-readable records in src/content/techniques.json (or the stack's equivalent), with:
id, title, triggerFeatures, exclusions, steps, listeningGoals, tempoRule,
successCriteria, returnToContext, sourceIds, evidenceCategory.

Store factual source metadata once, and refer to stable source IDs. Generated passage-specific advice must use valid technique IDs and real score ranges. Validate both before display.

## Enabled techniques (rubric 3.0 / library additions)
Sources S04–S11 in `src/content/sources.json`:

| ID | Source | Category | What it supports |
|---|---|---|---|
| S04 | Fischer, *Classical shifts* (Strad, Jul 2000) | teacher pedagogy | Shift through the audible intermediate note, then hide it |
| S05 | Galamian, *Principles of Violin Playing and Teaching* (1962) | teacher pedagogy | Equal bow division for slurs; shifting on the old finger; tempo raised in steps |
| S06 | Fischer, *Splitting the double stop* (Strad, Feb 2001) | teacher pedagogy | Each voice alone, then tune lower to upper |
| S07 | Fischer, *String crossing: staying close* (Strad, Sep 2002) | teacher pedagogy | Rehearse crossings on open strings; bow at the between-strings level |
| S08 | Ash & Holding 1990, *Human Factors* 32(2) | small experimental study | Chaining (add a segment at a time) beat whole-task practice on a keyboard sequence |
| S09 | Duke, Simmons & Cash 2009, *JRME* 56(4) | observational study | Precise error location and immediate correction predicted retention; total time did not |
| S10 | Bernardi et al. 2013, *Front. Hum. Neurosci.* 7:451 | small experimental study | Mental practice improved accuracy/anticipation, less than physical practice |
| S11 | Fischer, *Intonation: testing, relating, comparing* (Strad, Dec 2000) | teacher pedagogy | Check stopped notes against open strings; tune by relation |

Techniques enabled from these: `shift-preparation` (S04, S05), `double-stop-split` (S06, S11), `crossing-open-strings` (S07), `bow-division` (S05), `add-a-note` (S08, S05), `stop-and-fix` (S09), `mental-run` (S10), `open-string-reference` (S11). Every technique whose trigger depends on an estimated feature (string, position) says so in its cautions; the rubric labels those features "(estimated)".

## Difficulty rubric research boundary
The 0.0–10.0 rating is a product heuristic. Define and document features, weighting/aggregation, missing-data behavior, and reference examples during planning. Do not present the color categories as official violin qualifications. Prefer teacher review for later calibration; do not claim such review occurred in the hackathon.

### Difficulty rubric anchors
Rubric 3.0 (`src/features/difficulty/rubric.py`) is calibrated against constructed measures that match the level descriptions in graded string syllabi: the ASTA Certificate Advancement Program handbook (http://www.tnasta.org/docs/handbook.pdf) and Shar Music's difficulty ratings (https://www.sharmusic.com/pages/sheet-music-difficulty-ratings). The bands are the app's own; the syllabi are used only to order the anchors.

| Band (0–10) | Anchor notation | Syllabus description drawn on |
|---|---|---|
| < 2.0 | First-position quarters/eighths in an open-string key, moderate tempo, no double stops | "Beginner": first position, simple keys and rhythms |
| 2.0–4.0 | Eighths with accidentals or a few leaps, occasional relocation above first position, easy slurs | "Early intermediate": limited shifting, keys to three sharps/flats |
| 4.0–6.0 | Sixteenths at moderate tempo, frequent string crossings, third position, occasional double stops | "Intermediate": positions 1–3, simple double stops, dotted rhythms |
| 6.0–8.0 | Fast sixteenths high on the E string, thirds/sixths, several relocations per bar | "Advanced": all positions, double stops, fast passage work |
| > 8.0 | Concerto texture: sixteenth double stops above the octave at fast tempo | "Concerto / professional" |

The left-hand model (`lefthand.py`) is an estimate: it assumes the lowest workable position and the highest open string at or below each pitch, because printed parts rarely carry fingerings. Reviewers should treat "String crossings (estimated)" and "Position changes (estimated)" as upper-bound hints, not fingering advice. Tempo is read from a metronome mark, from `<sound tempo>`, or, failing both, from a tempo word (Presto, Andante…) with the assumption disclosed on the score.
