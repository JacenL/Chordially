# PracticeMap

Upload a page of printed violin sheet music. PracticeMap finds the phrases,
rates every measure from 0.0 to 10.0, draws a measure-aligned difficulty ribbon
under each system, and tells you how to practise the passage you select —
including complementary rhythm variations built from that passage's own notes.

## Quick start

```bash
pip install -r requirements-dev.txt
python -m uvicorn src.app.main:app --reload
```

Open http://127.0.0.1:8000. The example score at `/score/example` works with no
credentials at all. Analyzing your own upload needs
`PRACTICEMAP_ANTHROPIC_API_KEY` in `.env` (copy `.env.example`).

`docs/demo.md` is the demo script, with measured timings and an honest list of
limitations. `docs/checklist.md` is the delivery status.

## What works

- Upload a PDF, PNG or JPEG of one printed page and analyze that actual file.
  Measured on the demo page: 11 systems, 61 measures, 15 phrases, 43 of 61
  measures rated.
- OpenCV finds the staves, barlines and measures in the uploaded pixels; a
  vision model reads only the notation content. All geometry is exact code, so
  overlays sit on the real measures and survive zoom and resize.
- A continuous per-system difficulty ribbon whose segment widths follow the real
  engraved barlines, with the six colour anchors from `docs/design.md`.
- Measures that could not be read stay unrated and hatched, visually distinct
  from both easy and hard, and a request that never completed is kept distinct
  from notation that was read and rejected.
- Practice instruction selected from the notation, with sources that state what
  they do and do not support.

## What is not built

Phrase boundary editing, persistence of progress or settings, MusicXML import,
multi-page analysis, and tempo-driven recalculation. See the limitations section
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
python scripts/build_example_fixture.py        # rebuild the example (needs credentials)
```

There is no build step, no bundler and no type-checker configured: the client is
plain ES modules served as-is.

### Environment variables
Copy `.env.example` to `.env` and fill in `PRACTICEMAP_ANTHROPIC_API_KEY`. The
app reads only that variable and deliberately ignores an ambient
`ANTHROPIC_API_KEY`, so example mode cannot appear credentialed when the
application's own key is unset. The example score at `/score/example` needs no
credentials at all.

## Why CLAUDE.md is focused
It contains substantial persistent instructions while detailed specifications live in dedicated documents. Even in a single long session, instructions compete with source files, tool results, and conversation context. Claude Code guidance recommends concise project memory; referenced files are read when relevant, whereas imports load their content at startup.

Official reference: https://code.claude.com/docs/en/memory
