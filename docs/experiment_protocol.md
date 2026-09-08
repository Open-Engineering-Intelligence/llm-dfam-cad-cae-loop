# Experiment Protocol

## Scope

The first experiment evaluates a single bracket benchmark under a fixed
evaluation budget. The long-term objective is to compare proposal methods using
the same deterministic CAD, CAE, and DfAM pipeline. Issue #6 is a structural-only
integration experiment and follows the normative contract in
[Issue #6: Deterministic Structural Closed Loop](issue6_deterministic_closed_loop.md).

## Required Records

Each iteration must record:

- Method name
- Trial id and iteration index
- Random seed
- Full design parameters
- CAD artifact path or CAD failure reason
- Mesh artifact path or meshing failure reason
- FEA result path or simulation failure reason
- Mass, maximum von Mises stress, and maximum displacement
- Manufacturability measurements
- Constraint pass/fail flags
- Evaluation score
- Feedback passed to the next proposal step

For Issue #6, records also include the resolved candidate-specific analysis,
geometry/mesh/input identities and hashes, backend versions and executable
provenance, per-stage timing and failure details, the exact decision and stopping
reason, and CAD volume used to derive mass. DfAM status is `not_evaluated` and
full benchmark feasibility is `null`.

## Success Criteria

The full benchmark should report feasible-design rate, convergence curves, final
best feasible mass, invalid CAD rate, simulation failure rate, and
manufacturability outcomes for each method. Issue #6 acceptance is narrower:
three fresh serial trials must follow the frozen `8..4 mm` thickness-descent
policy, complete without backend or provenance error, and pass retained-evidence
verification and repeatability checks. These conditions establish software/run
acceptance. Mass reduction is a separate hypothesis, but Issue #6 milestone PASS
also requires each accepted trial to evaluate at least two candidates, select a
thickness below `8 mm`, and record a strictly positive mass reduction.

## Reproducibility Controls

- Fix parameter bounds and constraints before a comparison run.
- Use deterministic CAD generation for the same parameter input.
- Log backend versions and configuration hashes.
- Preserve raw CSV results and generated artifacts.
- Do not tune one method on another method's held-out evaluation results.

Issue #6 uses fresh output directories with no cache reuse. The experiment must
start from a clean working tree; each trial records the full implementation commit
SHA, and all three trials must identify the same clean commit. Semantic identities,
parameter/decision records, mesh SHA-256, and CalculiX input SHA-256 must match
exactly across its three trials. Numeric values must satisfy
`abs(a-b) <= max(1e-9, 1e-8 * max(abs(a), abs(b)))`. The experiment verifier
checks retained artifacts and exits nonzero on failure.

The Benchmark v1 ceiling remains 30 expensive evaluations. The Issue #6 policy
uses at most five because it stops at `4 mm` or the first structural failure; this
unused budget is reported rather than reassigned. Later fair reruns retain the
integer thickness grid `4..14` and fixed width/rib/fillet controls. No controls
may be tuned from observed results.
