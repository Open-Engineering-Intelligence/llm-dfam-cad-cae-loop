# Internal milestone Issue #6: Deterministic Structural Closed Loop

## Scope and status

This document retains the historical internal research milestone label
"Issue #6." The matching GitHub tracker item was Issue #7, "Implement
deterministic closed-loop parameter update"; GitHub Issue #6 is a separate task.

The internal Issue #6 milestone implements the first deterministic, non-LLM
closed loop on top of the merged Issue #5 CalculiX pipeline. The approved policy
is `thickness_descent_v1`. It is a structural-only integration benchmark: DfAM
is recorded as `not_evaluated`, `full_benchmark_feasible` is `null`, and Gate 3
remains incomplete.

The geometry, material, load, structural limits, and 30-evaluation ceiling come
from the frozen [Benchmark Bracket v1 specification](benchmark_bracket_v1.md)
and [configuration](../configs/bracket_default.yaml).

This document is the implementation and experiment contract. It contains no
closed-loop result claim; results may be reported only from retained evidence
that passes the protocol below. The Issue #5 baseline is PR #36, merge commit
`4109c991e3eac4315781cc2fb15001b56f165962`, and is accepted without re-review.

## Frozen policy

`thickness_descent_v1` starts from:

```text
thickness_mm = 8
width_mm = 50
rib_height_mm = 18
fillet_radius_mm = 2
```

After each structurally feasible evaluation, reduce `thickness_mm` by exactly
`1 mm`. Stop at `4 mm` or immediately after the first structurally infeasible
evaluation. At most five candidates are evaluated: `8, 7, 6, 5, 4 mm`.
The frozen Benchmark v1 budget remains 30 expensive evaluations; this policy's
early stopping deliberately uses no more than five of them.

Structural feasibility requires both values to pass without pre-comparison
rounding:

- maximum integration-point von Mises stress `<= 25 MPa`;
- maximum displacement magnitude `<= 2.0 mm`.

Choose the best design from evaluated structurally feasible candidates using
the ascending tuple `(mass_g, thickness_mm, iteration_index)`. Mass is computed
from the CAD volume as `cad_volume_mm3 * 0.00124 g/mm3`.

If the initial `8 mm` candidate is structurally infeasible, stop with no feasible
design. A backend, timeout, malformed result, or provenance failure makes the
run an error. It remains an error even if an earlier feasible candidate exists;
the earlier best may be retained for diagnosis but cannot turn the run into a
successful result. No failed candidate is retried automatically.

## Candidate-specific analysis

Existing CAD, Gmsh, and CalculiX backend configuration files and discovery
rules remain unchanged. Resolve and record the effective analysis for every
iteration. The load region must follow the candidate geometry exactly:

```text
z = thickness_mm
y = [-width_mm / 2, +width_mm / 2]
x = [98, 108] mm
total load = -150 N in z
```

Each candidate has a 300-second enclosing timeout. The existing FreeCAD and
CalculiX limits remain 60 seconds and 120 seconds, respectively. Tool execution
is isolated by candidate output directory. Executable discovery continues to
honor `FREECAD_CMD` and `CALCULIX_CCX`, followed by the existing discovery
behavior.

## Implementation shape

The implemented main units are closed-loop contracts, a deterministic controller,
a structural evaluator, and a runner/CLI under
`open_engineering_intelligence.pipeline`. These compose the existing backends;
they do not change backend configuration semantics. The evaluator returns
structured per-stage outcomes and provenance, while the controller owns proposal,
stopping, feasibility, and best-candidate selection.

## Commands and retained artifacts

Run one new trial:

```powershell
py -3.12 -m open_engineering_intelligence.pipeline.closed_loop --output <new-trial>
```

Run the required three-trial experiment:

```powershell
py -3.12 -m open_engineering_intelligence.pipeline.closed_loop --experiment --output <new-experiment>
```

Re-verify retained evidence without rerunning the external tools:

```powershell
py -3.12 -m open_engineering_intelligence.pipeline.closed_loop --verify <experiment-directory>
```

Verification exits nonzero for any missing, inconsistent, or failed required
evidence. Source execution uses an editable install with existing extras:
`py -3.12 -m pip install -e .[dev,cae]`.

The canonical experiment layout is:

```text
outputs/closed_loop/issue6_thickness_descent_v1/<experiment-id>/
  experiment_report.json
  repeatability.json
  trial-001/
    experiment_config.json
    environment_manifest.json
    closed_loop_result.json
    iterations/000/
      parameters.json
      effective_analysis.json
      decision.json
      iteration_manifest.json
      evaluation.stdout.log
      evaluation.stderr.log
      freecad.stdout.log
      freecad.stderr.log
      cad/
      mesh/
      fea/
  trial-002/...
  trial-003/...
```

The three trial-level filenames are exactly `experiment_config.json`,
`environment_manifest.json`, and `closed_loop_result.json`. Tool logs such as
`evaluation.stdout.log` are stored directly in the iteration directory beside
`iteration_manifest.json`; there is no intermediate `logs/` directory.

## Experiment and acceptance protocol

Run three fresh trials serially, with separate new directories and no artifact
cache or cross-trial reuse. Start the experiment only from a clean working tree,
record the full implementation commit SHA in each trial's environment evidence,
and require the same clean commit in all three trials. Repeatability requires
exact equality for semantic identities, parameter and decision records, mesh
SHA-256, and CalculiX input-deck SHA-256. Numeric outputs pass when, for every
compared pair `a, b`:

```text
abs(a - b) <= max(1e-9, 1e-8 * max(abs(a), abs(b)))
```

Software/run acceptance requires all trials to complete without backend or
provenance errors, the verifier to accept the retained evidence, exact
discrete-policy behavior, and repeatability under the rule above. Mass reduction
remains a separate research hypothesis so it cannot be inferred from software
correctness alone. Internal Issue #6 milestone PASS additionally requires every
trial to accept a candidate thinner than `8 mm` after at least two evaluations
and to record a strictly positive mass reduction from the initial candidate. A
null or negative result fails the milestone and must be reported without changing
the policy or fabricating a successful result.

## Scientific claim boundary

The read-only verifier must execute from the recorded clean implementation commit
and matching source tree. Check out that commit before verifying older evidence;
verification does not silently substitute a newer controller or evaluator.

For three trials, compare all three pairs, including trial 002 against trial 003.
Relocating retained evidence is allowed: run-relative references remain authoritative,
while original invocation paths remain recorded as historical provenance.

Accepted evidence can support claims that this fixed policy followed its declared
sequence, that the deterministic toolchain produced traceable structural results,
and that those retained results repeated within the declared identity and numeric
rules on the tested environment. It can report the observed structural feasibility
and mass change for these candidates.

The internal Issue #6 milestone cannot establish full Benchmark v1 feasibility,
DfAM validity, mesh convergence, printed-part performance, generalization beyond
this bracket and environment, or superiority over an LLM or conventional
optimizer. It also cannot turn software correctness alone into evidence that the
mass-reduction hypothesis was supported; milestone PASS depends on the accepted
observed results.

For a later fair comparison, retain the integer `thickness_mm` grid `4..14`, keep
`width_mm = 50`, `rib_height_mm = 18`, and `fillet_radius_mm = 2`, preserve the
30-evaluation ceiling, and report this policy's five-evaluation early-stopping
consequence. Do not tune these controls from observed comparison results. LLM
policies, advanced optimizers, DfAM evaluation, and mesh-convergence studies are
outside the internal Issue #6 milestone.
