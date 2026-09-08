# Research Roadmap

This roadmap defines gates that must be passed in order. Implementation should not outrun the research freeze.

For implementation status, see [README](../README.md#current-status). Frozen
Benchmark v1 values are defined by the [normative specification](benchmark_bracket_v1.md)
and its [configuration](../configs/bracket_default.yaml), not by historical
planning notes in this roadmap. Gate descriptions do not authorize new work.

## Gate 0 - Research Freeze

Acceptance:

- `docs/literature_map.md` is complete enough to guide implementation without overclaiming novelty.
- `docs/research_gap.md` explicitly states established prior work, non-novelty claims, research questions, and falsifiable hypotheses.
- `docs/research_roadmap.md` defines the execution gates.
- `docs/decision_log.md` records initial decisions and revisit conditions.
- Benchmark assumptions requiring validation are identified before implementation consumes them.

Historical status: this gate was originally proposed for v0.1 review. That entry
describes the research-freeze proposal, not the current implementation status.

## Gate 1 - Benchmark Freeze

Corresponds to GitHub Issue #1: Define bracket benchmark.

Freeze:

- Bracket geometry.
- Coordinate system.
- Mounting configuration.
- Load application.
- Material.
- Build orientation.
- Design variables.
- Parameter bounds.
- FEA constraints.
- DfAM constraints.
- Objective function.
- Evidence required for PASS/FAIL.

Benchmark v1 is frozen. Its mounting model, design variables, material and load,
constraints, mass objective, and evaluation budget are authoritative in the
[benchmark specification](benchmark_bracket_v1.md) and
[configuration](../configs/bracket_default.yaml). The
[sanity check](benchmark_sanity_check.md) and [decision log](decision_log.md)
record justification and limitations. Do not reopen the freeze based on an older
description here; changes require an explicitly authorized specification amendment.

Historical note (superseded pre-freeze checklist): the initial proposal considered
two mounting holes, hole diameter as a variable, a 120 g mass limit, and a
20-iteration budget. These are not active Benchmark v1 requirements. The
specification and decision log record the adopted definitions; the earlier
provisional-value checklist remains available in Git history.

## Gate 2 - Deterministic CAD-CAE PoC

Scope:

```text
parameters -> FreeCAD -> STEP -> Gmsh -> CalculiX -> parsed stress/displacement/mass
```

Status: complete at the Issue #5 baseline merged by PR #36, commit
`4109c991e3eac4315781cc2fb15001b56f165962`. CAD generation and export, Gmsh
meshing, CalculiX static execution, parsed stress/displacement, structured
failures, and provenance are implemented. Issue #6 accepts this baseline without
re-review.

Rules:

- No LLM.
- No DfAM scoring beyond geometry fields needed for the PoC.
- Record deterministic artifact paths and structured failure reasons.
- Keep backend adapters replaceable.

## Gate 3 - Deterministic Closed Loop + DfAM

Add:

- Geometry validity.
- Overhang measurement.
- Minimum wall-thickness measurement.
- Support requirement or support proxy.
- Explicit build orientation.
- A deterministic rule-based update loop.

Rules:

- Implement the deterministic rule-based loop before the LLM agent.
- DfAM validity must be measured by deterministic criteria, not by subjective LLM judgment.

Current Issue #6 scope implements only the deterministic structural
`thickness_descent_v1` integration slice described in
[the Issue #6 contract](issue6_deterministic_closed_loop.md). It records DfAM as
`not_evaluated` and full benchmark feasibility as `null`; therefore Gate 3 remains
incomplete. LLM policies, advanced optimizers, DfAM metrics, and mesh-convergence
studies do not enter this issue.

## Gate 4 - Baselines

At minimum:

- Random search.
- Rule-based search.
- One stronger conventional optimizer if feasible, such as Bayesian optimization or a genetic algorithm.

Rules:

- All methods must use the same evaluation budget.
- Failure rates count against the method that produced them.
- Baselines must be runnable without an LLM provider.

## Gate 5 - LLM Agent

LLM input:

- Natural-language requirement.
- Current parameters.
- Deterministic feedback.
- Iteration history in an explicitly defined bounded format.

LLM output:

- Strict structured JSON parameters only.

Rules:

- Do not allow arbitrary generated CAD code in the core experiment.
- Validate every proposal before CAD generation.
- Log invalid proposals, retries, and token/API cost when available.

## Gate 6 - Experiments

Measure:

- Feasible-design rate.
- Iterations/evaluations to first feasible design.
- Best feasible objective.
- Final mass.
- Maximum von Mises stress.
- Displacement.
- DfAM manufacturability metrics.
- Invalid proposal rate.
- CAD failure rate.
- Meshing failure rate.
- FEA failure rate.
- Token/API cost if useful.

Rules:

- Use repeated trials.
- Fix or log randomized seeds.
- Preserve raw CSVs, configuration hashes, backend versions, and artifact manifests.
- Write final Results only after reproducible evidence exists.

## Gate 7 - Ablation

Compare:

- No feedback or minimal feedback.
- Physics feedback only.
- DfAM feedback only.
- Physics plus DfAM feedback.

Optional:

- Sensitivity to LLM model choice.
- Sensitivity to feedback-window length.
- Sensitivity to objective weighting.

Rules:

- Do not tune ablations on final comparison outputs.
- Report null or negative LLM results.

## Gate 8 - Paper Package

Acceptance:

- Final result tables are produced from preserved raw outputs.
- Figures are reproducible from scripts or documented generation steps.
- `paper/references.bib` contains verified metadata for cited work.
- Limitations distinguish benchmark scope, backend sensitivity, DfAM proxy limits, and LLM prompt/model sensitivity.
- The repository can reproduce the pure Python checks and document the heavier CAD/CAE environment requirements.
