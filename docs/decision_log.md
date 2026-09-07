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
