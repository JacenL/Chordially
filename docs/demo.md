# PracticeMap — demo script

Status: an account of working software. Every number below was measured on
2026-09-12 against the build at commit `7a68e74` or later, not estimated.

## Before you start

```bash
pip install -r requirements-dev.txt
python -m uvicorn src.app.main:app --reload
```

Open http://127.0.0.1:8000.

A one-minute pre-flight that exercises the whole journey in a real browser:

```bash
python -m pytest tests/e2e/test_demo_flow.py -m live -q
```

It passes in about 7 seconds with a warm transcription cache. If it passes, the
demo works.

**Warm the cache before demoing.** The first analysis of a page calls the
provider and takes about a minute; every later analysis of the same page is
served from `work/transcription-cache/` in under two seconds. Run the pre-flight
once on the machine you will demo from.

## The script

### 1. The start screen (15 seconds)
Point out that there are two honest routes in: your own scan, and a clearly
labelled example. Read the limits aloud — one page, 20 MB, printed notation, and
the page image is sent to Anthropic for reading. Nothing is hidden in a tooltip.

### 2. Upload the real score (30 seconds warm, ~65 seconds cold)
Choose `fixtures/scores/wohlfahrt-op45-bk1-p3.pdf` and press **Analyze this
page**. This is a real one-page scan of Wohlfahrt Op. 45 Book 1, page 4 of the
book.

While it runs, point at the stage text. It names the stage actually running and
counts real sections — "read 12 of 34 sections". There is deliberately no
progress bar, because the stages take very different amounts of time and a
smoothly sweeping bar would be invented.

### 3. The analyzed page (45 seconds)
What lands is the uploaded scan with three layers over it:

- **Phrase outlines** with each phrase's name and 0.0–10.0 rating.
- **The difficulty ribbon**, one unbroken run under each system, measure-aligned,
  green through maroon. Segment widths follow the real engraved barlines.
- **Hatched regions** where recognition could not read the notation. Say this
  out loud: hatching is not "easy" and not "hard", it is *unknown*, and the
  legend has a sixth entry for it.

Point at the **Source** line at the top. It states how many sections were read
live and how many were reused from an earlier reading of that exact image. A
cached run and a live run are different facts and the page says which happened.

Measured on this page: 11 systems, 61 measures, 15 phrases, 43 of 61 measures
rated, ratings spanning 1.0–7.0.

### 3b. Change the tempo (20 seconds)
Type 160 into the toolbar's tempo field and press Recalculate. The whole ribbon
warms: this etude at 160 BPM is not the same music it is at 90, and the ratings
say so. Phrase 1 moves from 4.1 to 4.9. "back to assumed" restores the disclosed
90 BPM default.

Worth saying: the ratings measure demand per second, so tempo is not a display
preference. Any measure that prints its own tempo keeps it, and the notice says
how many did.

### 3c. The structure it found (15 seconds)
The phrase list is grouped under two headers: **Measures 1–28, 4/4 no sharps or
flats** and **Measures 29–61, 2/4 1 sharp**. That is a real structural boundary —
the page carries two different etudes and the app found the seam from the printed
key and meter change, marked on the score with a double rule.

Worth saying: the labels report what is printed, not what it means. "1 sharp",
not "G major", because a key signature does not establish a mode. And the Mozart
file gets no sections at all, because it has one key and one meter throughout —
inventing a "Section 1" would be a formal claim the notation does not support.

### 4. Select a passage (30 seconds)
Click the first phrase in the sidebar list, or click straight on the score.
Selection syncs the outline, the phrase list and the sidebar.

The sidebar shows the phrase's rating, its **local peak** — the hardest single
measure inside it — and why: "Note rate +0.8, Fast subdivision +0.8, Off-beat
placement +0.6", measured on the hardest measure rather than averaged across
the phrase.

Open **How this number was worked out**. This is the answer to the question a
judge or a teacher will actually ask. It shows every weight in the rubric, the
tempo the rating was computed from, and — given the same prominence — the seven
things the rubric cannot see: bowing beyond what is printed, fingering, string
choice, shifts, your hand, your level, and how it sounds. It also says outright
that no violinist has reviewed the scale.

The explanation is generated from the same constants that compute the ratings, so
it cannot drift into describing a rubric the code no longer implements.

Show the boundary panel. Each boundary carries a plain-language reason and an
honest confidence: "The line settles downward onto the tonic — moderate evidence
(0.37)". On continuous etude writing that confidence is often low, and it says
so rather than rounding up.

### 5. The exercise (60 seconds — the heart of the demo)
Phrase 1 gets **Complementary rhythms**, chosen because *a run of 12 equal notes
is printed here*. Read that line out: the technique was selected from the
notation, not from the rating.

The variants are built from the passage's own notes. Long–short shows
`E4 dotted eighth, G4 16th, B4 dotted eighth, A4 16th…` — the printed pitches in
their printed order, with the durations redistributed inside each pair. Then the
complement, short–long, and the same pattern displaced by one note so a
different pair is joined.

The line underneath is the point: *each variant lasts exactly as long as the
written run, so the beat does not move*. That is arithmetic on exact fractions,
asserted in the tests, not a claim.

Then steps, what to listen for, a pace rule, a success criterion, and the way
back into the music — including playing through the first note of the next
phrase, which is why phrases carry a practice range distinct from their
structural range.

Open **Sources**. Simon Fischer's article is cited with what it supports *and
what it does not*: it is teacher pedagogy, not a controlled trial. Techniques
PracticeMap chose on its own are badged "app heuristic" and say so.

### 5b. Drill the hard spot inside it (25 seconds)
Some phrases carry a dark box around one or two measures — a **hard spot**, the
spec's third level below section and phrase. Click measure 14 inside Phrase 3.
The sidebar shows a breadcrumb, "Phrase 3 › Hard spot", and Phrase 3 stays
outlined on the score: you have gone one level in without losing where you are.
The exercise re-targets to just those measures.

Only three of the fifteen phrases have one, and that restraint is deliberate — a
spot marked on every phrase would say nothing. They are also derived rather than
stored, so they move with the tempo: set 160 BPM and one of them disappears,
because once the whole phrase is demanding, that measure no longer stands out.

### 5c. Correct a boundary you disagree with (25 seconds)
Segmentation is inference and says so — several boundaries on this page carry
"moderate evidence (0.37)". Pick one you think is wrong, choose a measure from
the dropdown and press **Split here**; or **Merge with next** to join two ideas
the app separated. The phrase re-rates immediately, and the corrected boundary is
marked "edited" and records confidence 1.0 with the reason "you placed this
boundary" — your assertion, not the app's guess.

Try merging the last phrase: it refuses, and says there is nothing after it to
merge with. "Undo all boundary edits" returns to the inferred segmentation.

### 5d. The other input path (30 seconds — the strongest contrast)
Go back, and upload `fixtures/scores/mozart-k156-mvt1.mxl` — Mozart's String
Quartet K.156, Violin I. The page is engraved by Verovio rather than scanned,
and the difference is the whole point: **145 of 145 measures rated, nothing
hatched, nothing sent to any service.** The source line says the notes were read
from the file.

Say what this shows: the difficulty analysis is not downstream of OCR quality.
The scan path has recognition risk and reports it honestly; the MusicXML path has
none. The same ribbon, phrases and exercises come out of both.

### 6. A contrasting passage (20 seconds)
Select Phrase 8. It gets a different technique, because its measures could not
all be read and there is no even run to pair. Nothing generic is substituted.

Click any hatched measure. The sidebar names that specific measure as unrated
and distinguishes *unreadable notation* from *a request that never completed* —
one is a judgement about the page, the other about us.

### 7. Close (10 seconds)
Zoom to 300% and resize the window. The annotations stay on their measures,
because every overlay is positioned in page-relative percentages and the browser
does no coordinate arithmetic at all.

## If something goes wrong

- **The provider is down or out of credit.** Analysis still runs: geometry needs
  no credentials, so you still get the real page map with every measure marked
  as never read. Say that is what you are seeing. Do not describe it as
  successful recognition.
- **An upload is rejected.** That is the designed behaviour for anything outside
  the disclosed scope. The message names a recovery action; read it out.
- **Anything else.** Fall back to `/score/example`, which needs no credentials
  and is labelled "Example score" in the header. Say explicitly that it is
  prepared data.

## Known limitations, honestly

- **One page per upload.** A multi-page PDF is accepted; the first page carrying
  staves is analyzed and the rest is not read. The page says which page it used.
- **Printed notation only.** Handwriting is out of scope and untested.
- **MusicXML is the exact path.** A `.musicxml`, `.xml` or `.mxl` file is read
  directly: no transcription service, nothing sent anywhere, and no measure left
  unrated. Only the first part and the first engraved page are analysed, and the
  page says so.
- **Recognition is imperfect and says so.** On the demo page, 43 of 61 measures
  validated. The other 18 failed an arithmetic check — their durations did not
  sum to the meter — and are left unrated rather than shown as a guess.
- **Ratings are heuristic.** The 0.0–10.0 scale and its five categories are
  PracticeMap's own, documented in the rubric and inspectable from the sidebar.
  No source here validates them and no violinist has reviewed them;
  `fixtures/expected/review-phrases.md` is the packet waiting for that review.
- **One external check exists, and it is weak.** Wohlfahrt printed these studies
  in increasing order of difficulty and the app agrees — Etude 2 averages 4.0,
  Etude 3 averages 5.7, and the ordering holds at 60, 90 and 160 BPM. That is
  ordinal agreement with one editor on one pair of studies, from 25 and 7 rated
  measures. Worth saying out loud; not worth overclaiming.
- **Tempo is assumed at 90 BPM** when none is printed, which the page states.
  The toolbar's tempo field recalculates every rating from a supplied tempo;
  measures that print their own tempo keep it.
- **Phrase boundaries can be split and merged, but only at measure lines.** The
  spec also asks for a boundary inside a measure. The data model supports it —
  boundaries are note-level anchors — but the interface does not.
- **Edits are not saved.** They survive navigation and reload; they do not
  survive restarting the server.
- **Nothing persists.** Analyses live in memory for the life of the process, and
  self-reported practice progress is not stored. Restarting the server loses
  uploaded analyses; the example is always available.
- **No audio.** PracticeMap does not listen to you and cannot tell you whether
  you played it correctly. Success criteria are self-assessed by design.
- **Fingerings, shifts and string choices are never asserted** from interval
  size alone, because the notation does not establish them.

## Provenance of the example

`fixtures/scores/wohlfahrt-op45-bk1.pdf` — Franz Wohlfahrt, *Sixty Studies for
the Violin*, Op. 45 Book 1. Public domain. `wohlfahrt-op45-bk1-p3.pdf` is page 4
of that file extracted as a one-page document, verified to render
pixel-identical to the page the prepared example was built from. See
`fixtures/README.md`.
