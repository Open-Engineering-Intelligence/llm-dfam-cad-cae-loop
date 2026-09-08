# llm-dfam-cad-cae-loop

Closed-loop LLM-assisted parametric mechanical design under structural and additive-manufacturing constraints.

## Research Question

Can an LLM-assisted engineering agent iteratively improve parametric mechanical designs when every proposal is constrained to strict structured parameters and evaluated through deterministic structural and additive-manufacturing feedback?

## Motivation

Engineering design agents should be judged by reproducible evidence, not by impressive one-off CAD generation. This project studies a minimal closed loop in which an LLM or optimizer proposes bounded design parameters, deterministic backends generate and evaluate geometry, and structured feedback drives the next proposal.

The first target is intentionally narrow: a cantilever or mounting bracket benchmark with structural limits, mass objectives, and FDM-oriented manufacturability checks. The goal is to measure whether an LLM-assisted loop adds value compared with rule-based and random-search baselines.

## System Architecture

The core workflow is backend-agnostic:

```text
requirement -> agent/optimizer -> structured parameters -> CAD adapter
            -> geometry validation -> CAE adapter -> physics validation
            -> DfAM validation -> evaluation -> feedback -> next proposal
```

The first implementation targets FreeCAD for CAD generation, Gmsh for meshing, and CalculiX for static FEA. These are adapters, not assumptions baked into the research method.

## Research Scope

In scope:

- AI for engineering design under explicit constraints
- Parametric CAD driven by strict JSON/YAML-compatible design parameters
- Deterministic geometry, CAE, and manufacturability validation
- Baseline comparisons against non-LLM optimization methods
- Reproducible experiment logs and CSV result tables

Out of scope for the first phase:

- GUI or web dashboards
- Onshape, SimScale, Ansys, or cloud CAD/CAE integrations
- Complex assemblies, CFD, topology optimization, multi-material slicing, and real printer control
- LLM-generated arbitrary Python CAD code as the main workflow

## Initial Benchmark

Benchmark v1 is the frozen fixed-rear-face cantilever bracket defined in the
[authoritative specification](docs/benchmark_bracket_v1.md). Use that specification
and its [configuration](configs/bracket_default.yaml) for parameter names, bounds,
mounting, material, loading, constraints, objective, and evaluation budget.
The [analytical reference check](docs/benchmark_sanity_check.md) is a sanity check,
not a replacement for deterministic CAD/CAE validation.

## Current Status

The deterministic structural closed loop was implemented by PR #37 (reviewed
implementation commit `bf7bd84052183476835001cdfd1019d325a07c42`, merge commit
`33cd79f430571d05fa1469c7ab474126a4e899af`) on top of the static-FEA baseline
merged by PR #36 (commit `4109c991e3eac4315781cc2fb15001b56f165962`):

- FreeCAD bracket generation produces a native document, STEP, STL, and a CAD
  manifest with geometry fingerprint and tessellation metadata.
- Gmsh consumes STEP plus the CAD manifest and produces a tetrahedral volume mesh
  and mesh manifest; STL is not the meshing input.
- CalculiX 2.22 performs the frozen linear-static analysis and produces validated,
  structured stress, displacement, reaction, artifact, and provenance records.
- Integration tests cover the external CAD, mesh, and solver stages. Their
  presence is not a claim that they have passed in every environment.
- Gate 2 and the structural-only
  [`thickness_descent_v1` closed-loop milestone](docs/issue6_deterministic_closed_loop.md)
  are complete. The closed loop provides single-trial, three-trial serial
  experiment, and retained-evidence verification modes.
- Historical internal research planning labels this closed-loop milestone
  "Issue #6"; the matching GitHub tracker item is Issue #7, "Implement
  deterministic closed-loop parameter update." GitHub Issue #6 is a separate,
  unrelated task.
- The structural-only milestone does not evaluate DfAM or complete Gate 3. DfAM
  remains `not_evaluated`, and full benchmark feasibility remains `null`. This
  status update makes no new experimental result claim.

Historical note: the initial commit contained only contracts, configuration,
documentation, and pure Python CI. That initialization-only status is superseded
by the CAD/export and meshing implementations above.

## Roadmap

Follow the [gated research roadmap](docs/research_roadmap.md): deterministic
CAD-CAE PoC, deterministic closed loop and DfAM, non-LLM baselines, then the LLM
proposal policy, experiments, ablations, and paper package. The roadmap is not
permission to advance beyond the explicitly authorized task.

## Reproducibility

The project separates proposal generation from deterministic evaluation. LLM output is restricted to structured parameter proposals; CAD and FEA execution must be deterministic and logged. Experiment records should include configuration hashes, parameter values, backend versions, validation outcomes, failure reasons, and result artifacts.

Run the pure Python checks:

```powershell
python -m pip install -e .[dev]
python -m pytest -q -m "not integration"
ruff check .
```

External integration tests are separate: install with
`python -m pip install -e .[dev,cae]`, then run
`python -m pytest -q -m integration`. They require FreeCAD, Gmsh, and CalculiX;
`FREECAD_CMD` and `CALCULIX_CCX` can select existing executables. Missing tools
cause explicit skips; skips do not demonstrate backend success.
See [agent routing and validation scope](AGENTS.md) for task-specific checks.

The closed-loop entry point exposes a single-trial command, a three-trial serial
experiment, and a retained-evidence verifier through
`py -3.12 -m open_engineering_intelligence.pipeline.closed_loop`. The contract,
artifact layout, tolerances, and claim limits are documented in the linked
[internal milestone contract](docs/issue6_deterministic_closed_loop.md).

## Repository Structure

```text
configs/                         Benchmark and backend configuration
docs/                            Research proposal, architecture, protocol, and literature map
experiments/bracket_v1/          First benchmark experiment workspace
baselines/                       Rule-based, random-search, and future optimizer baselines
prompts/                         LLM system and proposal prompts
outputs/                         Ignored generated CAD, mesh, FEA, figure, and log artifacts
paper/                           Manuscript draft, figures, and bibliography
scripts/                         Reproducibility and runner scripts
src/open_engineering_intelligence/
  agents/                        Design-agent interfaces
  cad/                           CAD backend interfaces and adapters
  cae/                           CAE backend interfaces and adapters
  optimization/                  Optimizer interfaces and baselines
  validators/                    Geometry, physics, and manufacturability validators
  pipeline/                      Closed-loop orchestration contracts
  utils/                         Shared utilities
tests/                           Unit tests for schema and pure Python contracts
```
