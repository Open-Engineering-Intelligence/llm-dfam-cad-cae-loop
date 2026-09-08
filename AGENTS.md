# Agent Routing and Scope

This is `Open-Engineering-Intelligence/llm-dfam-cad-cae-loop`: a reproducible
bracket benchmark studying structured design proposals evaluated by deterministic
engineering backends, with fair non-LLM baseline comparisons.

## Read What the Task Needs

- [README](README.md): implementation status and repository layout.
- [Benchmark specification](docs/benchmark_bracket_v1.md): authoritative frozen
  values; [configuration](configs/bracket_default.yaml) is its executable
  counterpart. [Analytical sanity check](docs/benchmark_sanity_check.md) supplies
  a reference, not a substitute for CAD/CAE validation.
- [Architecture](docs/system_architecture.md): intended contracts;
  [roadmap](docs/research_roadmap.md): gate order;
  [decision log](docs/decision_log.md): rationale and superseded alternatives.
- [Contributing](CONTRIBUTING.md): development workflow;
  [experiment protocol](docs/experiment_protocol.md): actual experiment runs.
  Use [test configuration](pyproject.toml), relevant tests, and
  [CI](.github/workflows/ci.yml) for applicable validation commands.

## Engineering Pipeline

```text
DesignParameters -> FreeCAD -> CAD artifacts/manifest (STEP for meshing)
                 -> Gmsh -> mesh/manifest -> CalculiX -> structured physics result
```

The PR #35 baseline implements CAD generation/export and Gmsh meshing. CalculiX
and structured physics results are planned stages, not completed functionality.
The roadmap describes dependencies, not authorization to start the next issue.

## Scope and Invariants

- Work in this repository; do not import unrelated repositories' instructions,
  branch policies, experiment gates, or results. Read only task-relevant context.
- Follow explicit user task instructions within higher-priority safety and tool
  constraints. Already-approved work needs no additional process approval unless
  a material unresolved decision changes scope or authorization.
- Change frozen values only through an explicitly authorized amendment to the
  benchmark specification, keeping its configuration and linked records
  consistent. Do not invent replacements or redefine values in secondary docs.
- Keep proposals bounded and structured, backends deterministic, and failures
  explicit. Preserve artifacts, manifests, fingerprints, backend/configuration
  provenance, and prior experiment results. Numerical results are not proof of
  real printed-part performance.
- [Design-agent prompt](prompts/design_agent_system.md) governs the future
  application role, not the coding agent maintaining this repository.
- Do not automatically commit, discard user work, create worktrees, merge, push,
  or publish without task-specific authorization. Preserve unrelated changes.

## Validation and Completion

- Match planning and validation to the change. Documentation-only changes need
  consistency, link, and diff checks, not unrelated full test or CAE runs.
- Keep pure Python checks separate from optional external integration tests.
  Claims that FreeCAD, Gmsh, or CalculiX works require real integration evidence;
  mocks, imports, and skipped tests do not establish external functionality.
- Reuse traceable evidence covering unchanged code, inputs, configuration,
  dependencies, and environment; identify its source and what was not rerun.
  Rerun affected checks after changes, or when the user explicitly requests them.
- For an explicit full integration request, run the applicable integration suite
  and inspect failures and skips. If a dependency is missing, report the blocked
  coverage and prerequisite; do not present skipped coverage as successful.
