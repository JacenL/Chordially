# PracticeMap — ready-to-use Claude prompt kit

This folder contains written project instructions, requirements, design guidance, a research foundation, a delivery checklist, and prompts for planning, implementation, and debugging. It is not an implemented application.

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
Not available yet. During T02 replace this section with actual installation, local development, build, and test commands and document required environment variables.

## Why CLAUDE.md is focused
It contains substantial persistent instructions while detailed specifications live in dedicated documents. Even in a single long session, instructions compete with source files, tool results, and conversation context. Claude Code guidance recommends concise project memory; referenced files are read when relevant, whereas imports load their content at startup.

Official reference: https://code.claude.com/docs/en/memory
