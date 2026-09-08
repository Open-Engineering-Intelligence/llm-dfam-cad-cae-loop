# Decision Log

This log records research and architecture decisions that affect reproducibility or claims.

## 2026-09-07 - Use FreeCAD as the first CAD backend

- Decision: FreeCAD is the first deterministic CAD backend.
- Reason: It is scriptable, open-source, and suitable for a reproducible local proof of concept.
- Alternatives considered: Onshape, direct OpenSCAD-style generation, commercial CAD systems.
- Revisit condition: Revisit if FreeCAD cannot reliably generate the frozen bracket family or cannot run in the required research environment.

## 2026-09-07 - Use Gmsh and CalculiX as the first CAE pipeline

- Decision: Gmsh is the first meshing backend and CalculiX is the first static FEA solver.
- Reason: Both can support an open, reproducible CAD-CAE proof of concept without requiring commercial solver licenses.
- Alternatives considered: SimScale, Ansys, Abaqus, Code_Aster, custom simplified beam formulas.
- Revisit condition: Revisit if meshing or solver automation is not stable enough for repeated trials.

## 2026-09-07 - Treat CAD and CAE backends as implementation choices, not novelty

- Decision: FreeCAD, Gmsh, and CalculiX are experimental backends, not claimed research novelty.
- Reason: Prior work already covers CAD scripting, FEA automation, and agentic engineering workflows.
- Alternatives considered: Framing backend automation as a contribution.
- Revisit condition: Do not revisit unless a backend adapter itself introduces a separately publishable method.

## 2026-09-07 - Keep interfaces backend-agnostic

- Decision: Core contracts must remain independent of a specific CAD platform, CAE solver, LLM provider, or cloud service.
- Reason: The research question concerns proposal policies under deterministic feedback, not vendor-specific integration.
- Alternatives considered: Building directly around FreeCAD and CalculiX types.
- Revisit condition: Revisit only if a frozen benchmark requires backend-specific semantics that cannot be represented cleanly.

## 2026-09-07 - Use a single bracket family as the first benchmark

- Decision: The first benchmark is one cantilever or mounting bracket family.
- Reason: A narrow benchmark makes structural constraints, manufacturability constraints, and baseline comparisons auditable.
- Alternatives considered: Multiple part families, assemblies, topology optimization, lattice structures.
- Revisit condition: Expand only after the first benchmark has reproducible evidence and limitations are clear.

## 2026-09-07 - Build the deterministic CAD-CAE loop before introducing an LLM

- Decision: Gate 2 and Gate 3 must work without an LLM before Gate 5 starts.
- Reason: The project must separate infrastructure validity from LLM proposal-policy value.
- Alternatives considered: Starting with the LLM agent first.
- Revisit condition: Do not revisit for the first paper.

## 2026-09-07 - Restrict LLM output to structured bounded parameters

- Decision: In the core experiment, LLM output is strict JSON-compatible `DesignParameters` within frozen bounds.
- Reason: Deterministic CAD/CAE/DfAM validation should remain the source of truth.
- Alternatives considered: Arbitrary LLM-generated Python CAD scripts.
- Revisit condition: Arbitrary CAD-code generation may be studied in a later, separate paper, not this first benchmark.

## 2026-09-07 - Use deterministic DfAM criteria

- Decision: DfAM validity must come from measurable criteria such as overhang, wall thickness, support proxy, build orientation, and process assumptions.
- Reason: Subjective LLM manufacturability judgment would confound the evaluation.
- Alternatives considered: LLM-only manufacturability critique or natural-language scoring.
- Revisit condition: Revisit only after deterministic DfAM metrics are implemented and audited.

## 2026-09-07 - Exclude broad integrations from the first paper

- Decision: The first paper excludes Onshape, SimScale, Ansys integration, CFD, complex assemblies, multi-material slicing, and real printer control.
- Reason: These would blur the benchmark and weaken falsifiability.
- Alternatives considered: A broader engineering-agent platform paper.
- Revisit condition: Add these only as future work or later repository directions after the bracket study.

## 2026-09-07 - Require traditional optimizer baselines

- Decision: Traditional optimizer baselines are mandatory.
- Reason: The project must be able to conclude that the LLM does not outperform conventional optimization.
- Alternatives considered: Comparing only LLM variants or only rule-based search.
- Revisit condition: Revisit the exact optimizer choice at Gate 4, but not the requirement for at least one non-LLM baseline family.

## 2026-09-07 - Freeze Benchmark Bracket v1 as a fixed-face cantilever bracket

- Decision: Benchmark v1 is a fixed rear-face cantilever bracket with a rectangular arm, fixed base block, centered triangular rib, and deterministic fillets.
- Reason: This gives a simple numerical engineering optimization problem with reliable future CAD generation, cheap static FEA, and a beam-equation sanity check.
- Alternatives considered: L-brackets with bolt holes, complex mounting brackets, assemblies, and topology-optimized brackets.
- Revisit condition: Revisit only if Issue #2 shows the geometry cannot be generated or meshed robustly.

## 2026-09-07 - Exclude modeled bolt holes from Benchmark v1

- Decision: Benchmark v1 models zero bolt holes; mounting is represented by an ideal fixed rear face.
- Reason: Bolt holes, preload, contact, washers, and bearing stress would add modeling choices that are not needed for the first proposal-policy benchmark.
- Alternatives considered: Keeping `hole_diameter_mm` as a design variable and modeling a two-hole mounting pattern.
- Revisit condition: Add holes only in a later benchmark after the fixed-face bracket loop is reproducible.

## 2026-09-07 - Freeze four design variables for Benchmark v1

- Decision: The frozen design variables are `thickness_mm`, `width_mm`, `rib_height_mm`, and `fillet_radius_mm`.
- Reason: A four-dimensional design space is expressive enough for mass/stiffness/stress tradeoffs while remaining tractable for random, rule-based, conventional, and LLM proposal policies.
- Alternatives considered: Including `hole_diameter_mm`, rib thickness, arm length, base dimensions, and build orientation as variables.
- Revisit condition: Revisit after Gate 6 if sensitivity results show a variable is non-identifiable or a missing variable is necessary.

## 2026-09-07 - Use a PLA-like isotropic numerical material model

- Decision: Benchmark v1 uses a PLA-like isotropic reference polymer with density `1240 kg/m3`, Young's modulus `3250 MPa`, Poisson's ratio `0.36`, and yield reference `52.5 MPa`.
- Reason: The first paper needs a deterministic numerical benchmark, not a full anisotropic FDM material-calibration study.
- Alternatives considered: Generic isotropic polymer, vendor-specific calibrated FDM PLA, PETG, and orthotropic printed-material modeling.
- Revisit condition: Replace with calibrated orthotropic or printer-specific material data only after the first benchmark loop is stable.

## 2026-09-07 - Define Benchmark v1 as mass minimization with feasibility constraints

- Decision: The primary objective is minimize mass, subject to frozen structural, DfAM, geometry, and execution constraints.
- Reason: A constrained objective avoids arbitrary weighted scores and makes optimizer comparison clearer.
- Alternatives considered: Weighted aggregate score over mass, stress, displacement, and manufacturability.
- Revisit condition: Multi-objective or weighted-score variants may be added after the primary constrained benchmark is reproducible.

## 2026-09-07 - Freeze deterministic FDM/DfAM support proxy

- Decision: Benchmark v1 uses build direction `(0, 0, 1)`, minimum wall/feature thickness `2.4 mm`, and a support proxy based on unsupported exterior regions where `n dot -b > cos(45 deg)` and connected area is at least `25 mm2`.
- Reason: This converts the common overhang heuristic into a deterministic geometry condition without relying on subjective LLM judgment.
- Alternatives considered: Slicer-generated support volume, print experiments, bridge-aware rules, and LLM manufacturability critique.
- Revisit condition: Revisit after deterministic DfAM implementation or physical calibration shows the proxy is misleading.

## 2026-09-07 - Freeze initial evaluation budget at 30 expensive evaluations

- Decision: Each policy gets 30 expensive CAD/CAE/DfAM evaluations in the first comparison protocol; schema-invalid LLM retries are logged separately.
- Reason: The budget is small enough for early CAD/CAE iteration while giving random and conventional baselines more room than the provisional 20-iteration value.
- Alternatives considered: Keeping 20 evaluations, freezing repeated-trial count now, or making the budget method-specific.
- Revisit condition: Gate 2 runtime measurements may require adjusting the budget before Gate 6, with the change documented as an amendment.

## 2026-09-08 - Use a frozen thickness-descent policy for internal Issue #6

This historical internal research milestone corresponds to GitHub Issue #7,
"Implement deterministic closed-loop parameter update." It is not GitHub Issue #6.

- Decision: The first closed-loop integration uses `thickness_descent_v1`, starting
  at `(thickness, width, rib height, fillet) = (8, 50, 18, 2) mm`, decreasing
  thickness by `1 mm` through `4 mm`, and stopping at the first structural failure.
- Reason: A deterministic, bounded sequence isolates orchestration, evidence, and
  repeatability from proposal-policy uncertainty.
- Selection: Choose the lightest evaluated structurally feasible candidate by
  `(mass_g, thickness_mm, iteration_index)`. An initially infeasible design yields
  no feasible candidate. Backend and provenance failures remain run errors even
  if an earlier feasible candidate exists.
- Constraints: Compare unrounded integration-point von Mises stress and maximum
  displacement using inclusive `25 MPa` and `2.0 mm` limits. Derive mass as CAD
  volume times `0.00124 g/mm3`.
- Budget and evidence: Preserve the 30-evaluation benchmark ceiling; this policy
  uses at most five. Require three fresh serial, uncached trials, exact semantic
  identities and mesh/input hashes, and the documented numeric tolerance.
- Scope: DfAM remains `not_evaluated`, full benchmark feasibility remains `null`,
  and Gate 3 is incomplete. Mass reduction is a separate hypothesis from software
  correctness, but positive reduction in every accepted trial is required for
  internal Issue #6 milestone PASS. No result is claimed before accepted retained
  evidence exists.
- Alternatives considered: adding an LLM, an advanced optimizer, DfAM scoring, or
  a mesh-convergence study to the first loop integration.
- Revisit condition: Do not tune this policy from observed results. Compare later
  methods fairly under frozen controls and budget, and implement DfAM in a
  separately reviewed Gate 3 task.
