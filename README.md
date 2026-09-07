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

The first benchmark is a cantilever or mounting bracket with a small parameter set:

- `thickness`
- `width`
- `rib_height`
- `fillet_radius`

Initial constraints include maximum von Mises stress, maximum displacement, mass, minimum wall thickness, maximum overhang angle, and a support requirement proxy.

Benchmark v1 is frozen in `docs/benchmark_bracket_v1.md`, with an analytical reference check in `docs/benchmark_sanity_check.md`.

## Current Status

This repository is in the first initialization phase. It contains the reproducible project structure, interface contracts, configuration schema, documentation skeleton, and CI for the pure Python layer. Full FreeCAD, Gmsh, and CalculiX automation are planned but intentionally not implemented in the first commit.

## Roadmap

1. Deterministic CAD-CAE proof of concept for the bracket benchmark.
2. Structured LLM design-agent proposals with strict output validation.
3. DfAM validators for overhangs, wall thickness, and support proxy scoring.
4. Repeated experimental evaluation against rule-based and random-search baselines.
5. Paper-ready result tables, figures, ablations, and reproducibility package.

## Reproducibility

The project separates proposal generation from deterministic evaluation. LLM output is restricted to structured parameter proposals; CAD and FEA execution must be deterministic and logged. Experiment records should include configuration hashes, parameter values, backend versions, validation outcomes, failure reasons, and result artifacts.

Run the pure Python checks:

```powershell
python -m pip install -e .[dev]
python -m pytest -q
ruff check .
```

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
