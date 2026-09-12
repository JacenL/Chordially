# Chordially

Upload a page of printed violin sheet music. Chordially divides it into
practice passages, rates each one from 0.0 to 10.0, colours the page passage by
passage from light green to near-black, and tells you how to practise the one you
select — including complementary rhythm variations built from that passage's
own notes.

## Local final integration

Branch `final` combines all backend branches merged through `bcc68e8` with the
frontend work. Use Python 3.13 (tested locally), install `requirements-dev.txt`,
and run `python -m uvicorn src.app.main:app --reload`. The local virtual
environment is `.venv313`.

The frontend uses subtle measure highlights, an upload/status bar, and preserves
sidebar position during selection. Scanned uploads are re-engraved and labelled.
The home screen reports when Audiveris is missing. No Grok wrapper is included.

Audiveris is **not installed in this Mac checkout**. Configure its executable via
`PRACTICEMAP_AUDIVERIS_EXE` in `.env` after installing it. MusicXML and example
mode work now. Progress persistence and note-level boundary editing remain
unimplemented backend contracts; they are not claimed complete by this merge.

## Quick start

```bash
pip install -r requirements-dev.txt
python -m uvicorn src.app.main:app --reload
```

Open http://127.0.0.1:8000. Nothing needs an API key: MusicXML is parsed
locally and a scanned page is recognized locally by Audiveris. See
**Reading scans** below for the one extra install that needs.

`docs/demo.md` is the demo script, with measured timings and an honest list of
limitations. `docs/checklist.md` is the delivery status.

## What works

- Upload a PDF, PNG or JPEG of one printed page and analyze that actual file.
  Audiveris recognizes it on this machine — no API key, no network call, no
  credit balance, and the same page gives the same answer every time. Measured
  on the demo page: 14.8s, 56 measures, 51 rated, nine practice passages. The
  page shown is re-engraved from what was read, which the source line says.
- Or import MusicXML (`.musicxml`, `.xml`, `.mxl`), which is read exactly from
  the file — engraved with Verovio, no recognition step, and no measure left
  unrated. Measured on Mozart K.156: 145 of 145 measures rated.
- The committed example is the other route: a real scan with OpenCV-measured
  geometry, annotated over the original page image. All geometry is exact code,
  so overlays sit on the real measures and survive zoom and resize.
- A continuous per-system difficulty ribbon banded by practice passage rather
  than by measure, whose widths follow the real engraved barlines, with the five
  colour anchors from `docs/design.md`. One passage carries one rating and one
  colour everywhere it appears, including across a line break.
- Clicking anywhere inside a passage — a measure, its outline, or its ribbon
  band — selects the whole passage and loads its guidance. Phrases and local
  hard spots are secondary detail inside it.
- Measures that could not be read stay unrated and hatched, visually distinct
  from both easy and hard, and a request that never completed is kept distinct
  from notation that was read and rejected.
- Practice instruction selected from the notation, with sources that state what
  they do and do not support.

## What is not built

Persistence of progress and settings, structural sections, phrase boundaries
inside a measure, and multi-page analysis. See the limitations section
of `docs/demo.md`.

---

## About this repository's origins

This started as a Claude prompt kit: written project instructions, requirements,
design guidance, a research foundation, a delivery checklist, and prompts for
planning, implementation, and debugging. Those documents are still here and are
still authoritative.

## Use it
1. Copy this folder's contents into the intended application repository. If that repository already has instructions, merge deliberately instead of overwriting them. Include the hidden .gitignore and .env.example files.
2. Open that repository in Claude Code and select the intended Opus 5 model and Plan Mode in the interface.
3. Paste prompts/01-plan.md into Claude. The referenced project files must be present in that repository.
4. Review the plan's recognition/geometry feasibility and scope. Approve the plan and leave Plan Mode.
5. Use prompts/02-implement.md if an explicit implementation message is needed. Claude should then continue through the checklist, committing and pushing completed tasks.
6. Use prompts/03-debug.md with a concrete bug report during debugging.

The authorized GitHub destination is https://github.com/arkyarky4546-ai/HackCMU-Happy-. Claude must verify or configure the remote for this exact repository, including its trailing hyphen. The kit does not create a repository, establish authentication, or grant tool-level permissions. The intended default working branch is practice-map-build. The Git policy does not authorize merging or public site deployment.

## Files and responsibilities
| File | Purpose |
|---|---|
| CLAUDE.md | Persistent engineering, musical, workflow, and Git instructions |
| docs/product-spec.md | Authoritative product requirements and acceptance criteria |
| docs/design.md | Layout, color mapping, annotations, and interaction behavior |
| docs/music-pedagogy.md | Sourced starting techniques and further research requirements |
| docs/architecture.md | Concrete planning constraints and decisions to resolve |
| docs/checklist.md | Ordered tasks, completion evidence, blockers, bugs, and handoff |
| docs/safe-execution.md | Repository preflight, safe checkpoints, validation, and recovery |
| docs/demo.md | Target demo script, to be updated with observed behavior |
| prompts/01-plan.md | Initial message for Plan Mode |
| prompts/02-implement.md | Implementation authorization and execution request |
| prompts/03-debug.md | Focused debugging message |
| .gitignore | Secret, upload, dependency, and generated-file exclusions |
| .env.example | Instructions for documenting actual integration variables after selection |

## Important assumptions
- Phrase lengths follow musical ideas. Two measures can be a genuine phrase; arbitrary two-measure slicing is not acceptable.
- Phrase ratings and local measure ratings serve different UI roles.
- The proposed difficulty category thresholds and color hex values are adjustable product defaults, not validated violin grades.
- An unreadable passage stays unrated rather than receiving a false number.
- Research notes distinguish evidence from application choices. Additional candidate techniques require research before use.

## Application structure to create after planning
```text
src/
  app/                       # Or the chosen framework's equivalent
  components/
  features/
    upload/
    score-viewer/
    segmentation/
    difficulty/
    practice/
  server/
    recognition/
    analysis/
  schemas/
  content/
tests/
  unit/
  integration/
  e2e/
fixtures/
  README.md                  # Provenance and reviewed expectations
  scores/                    # Actual matching PDF and MusicXML
  expected/                  # Reviewed reference analysis
.github/
  workflows/
    ci.yml                   # Actual build/check commands after setup
```

Do not create fake example scores, expected data, dependency files, or CI commands merely to fill these paths. Create real assets/configuration during their checklist tasks. Keep the chosen package lockfile in Git.

## Development commands
Python 3.14 (built and tested on CPython 3.14.6). No Node, Java or Docker needed.

```bash
pip install -r requirements-dev.txt      # runtime + test dependencies
python -m playwright install chromium    # once, for the browser tests

python -m uvicorn src.app.main:app --reload   # run the app: http://127.0.0.1:8000
python -m pytest -q                            # whole suite
python -m pytest tests/unit tests/integration -q   # fast: no browser needed
python scripts/refresh_example_analysis.py     # re-derive the example, no key needed
python scripts/build_example_fixture.py        # re-read the scan (needs credentials)
```

There is no build step, no bundler and no type-checker configured: the client is
plain ES modules served as-is.

### Reading scans
Scan recognition runs locally through **Audiveris 5.11**, which is a Java
application and so is not covered by `pip install`. The Windows console MSI
unpacks without administrator rights and carries its own JDK:

```
msiexec /a Audiveris-5.11.0-windowsConsole-x86_64.msi /qn TARGETDIR=work\audiveris\extracted
```

Chordially looks for it at `work/audiveris/extracted/Audiveris/Audiveris.exe`,
then at `PRACTICEMAP_AUDIVERIS_EXE`, then on `PATH`. When it is absent, a scan
upload fails with a sentence and a recovery action; MusicXML import and the
example score still work. Set `PRACTICEMAP_SCAN_ENGINE=vision` to use the
original Anthropic path instead.

### Environment variables
Optional. `PRACTICEMAP_ANTHROPIC_API_KEY` in `.env` (copy `.env.example`) is
needed only for the legacy vision scan path and for re-reading the example scan
from source. The app reads only that variable and deliberately ignores an
ambient `ANTHROPIC_API_KEY`.

## Why CLAUDE.md is focused
It contains substantial persistent instructions while detailed specifications live in dedicated documents. Even in a single long session, instructions compete with source files, tool results, and conversation context. Claude Code guidance recommends concise project memory; referenced files are read when relevant, whereas imports load their content at startup.

Official reference: https://code.claude.com/docs/en/memory
