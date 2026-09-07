# Experiment Protocol

## Scope

The first experiment evaluates a single bracket benchmark under a fixed iteration budget. The objective is to compare closed-loop proposal methods using the same deterministic CAD, CAE, and DfAM validation pipeline.

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

## Success Criteria

The first benchmark should report feasible-design rate, convergence curves, final best feasible mass, invalid CAD rate, simulation failure rate, and manufacturability outcomes for each method.

## Reproducibility Controls

- Fix parameter bounds and constraints before a comparison run.
- Use deterministic CAD generation for the same parameter input.
- Log backend versions and configuration hashes.
- Preserve raw CSV results and generated artifacts.
- Do not tune one method on another method's held-out evaluation results.
