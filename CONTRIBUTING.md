# Contributing

This project is organized as a reproducible research codebase. Early work may be done by a small number of researchers, but every change should leave enough evidence for another person to understand and repeat it.

## Principles

- Keep the workflow research-first and evidence-based.
- Preserve deterministic CAD, meshing, simulation, validation, and evaluation boundaries.
- Restrict LLM outputs to structured proposals that can be validated before use.
- Record experiment inputs, backend versions, outputs, failure modes, and result summaries.
- Do not replace baseline comparisons with anecdotal examples.

## Development Workflow

1. Create or link an issue describing the research or engineering objective.
2. Add or update tests for pure Python contracts before changing implementation code.
3. Keep FreeCAD, Gmsh, and CalculiX integration tests separate from CI-required unit tests unless the runner image explicitly supports them.
4. Document any schema or protocol changes in the pull request.
5. For experiments, preserve raw outputs and summarize results without overwriting prior runs.

## Pull Requests

Every pull request should explain what changed, why it matters, what evidence supports it, which tests were run, and whether reproducibility contracts changed.
