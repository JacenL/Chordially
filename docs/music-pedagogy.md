# Chordially — research and technique foundation

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

## Difficulty rubric research boundary
The 0.0–10.0 rating is a product heuristic. Define and document features, weighting/aggregation, missing-data behavior, and reference examples during planning. Do not present the color categories as official violin qualifications. Prefer teacher review for later calibration; do not claim such review occurred in the hackathon.
