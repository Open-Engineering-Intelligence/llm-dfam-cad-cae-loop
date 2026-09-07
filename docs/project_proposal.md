# Project Proposal

## Research Problem

LLM-assisted engineering design systems often demonstrate isolated CAD generation, but they rarely separate proposal generation from deterministic engineering validation. This project studies whether an LLM-assisted agent can improve a parametric mechanical design through repeated, auditable feedback from CAD, FEA, and DfAM validators.

## Hypothesis

An LLM-assisted design agent that proposes strict structured parameters can improve feasible bracket designs across iterations when feedback includes deterministic structural and manufacturability measurements. Its value must be demonstrated against non-LLM baselines, not assumed from qualitative examples.

## Research Questions

- Can structured LLM proposals reduce invalid design attempts compared with unconstrained generation?
- Does feedback from deterministic CAD, FEA, and DfAM validators improve design quality over repeated iterations?
- Does the LLM-assisted method outperform rule-based or random-search baselines under the same evaluation budget?
- Which feedback fields are most useful for the next design proposal?

## Contributions

- A minimal backend-agnostic closed-loop architecture for engineering design agents.
- A reproducible bracket benchmark with bounded parameters and explicit constraints.
- Interface contracts separating LLM proposal, CAD generation, CAE simulation, DfAM validation, and evaluation.
- Baseline comparisons designed to measure the value of LLM guidance over traditional search.

## System Boundary

The first phase uses structured JSON-compatible parameters as the only design-action surface. The LLM does not generate arbitrary CAD scripts in the core workflow. CAD and CAE steps are deterministic adapters, initially FreeCAD and CalculiX, with Gmsh for meshing.

## Design Variables

- `thickness_mm`
- `width_mm`
- `rib_height_mm`
- `fillet_radius_mm`
- `hole_diameter_mm`

## Constraints

- Maximum von Mises stress
- Maximum displacement
- Maximum mass
- Minimum wall thickness
- Maximum overhang angle
- Support requirement or support proxy

## Evaluation Metrics

- Feasible-design rate
- Invalid CAD rate
- Meshing failure rate
- Simulation failure rate
- Final mass
- Maximum von Mises stress
- Maximum displacement
- Manufacturability score
- Iterations to first feasible design
- Best feasible objective value under a fixed budget

## Baselines

- Rule-based parameter update
- Random search
- Future Bayesian optimization or genetic algorithm
- LLM-assisted design agent

## Experimental Plan

1. Define the bracket benchmark, parameter bounds, material, load, and boundary conditions.
2. Implement deterministic CAD generation and export.
3. Automate meshing and static FEA.
4. Parse stress, displacement, mass, and failure states into structured records.
5. Add DfAM validators for overhang angle, wall thickness, and support proxy.
6. Run repeated trials for each baseline under the same iteration budget.
7. Report convergence curves, feasibility rates, final objectives, and failure modes.

## Risks

- FreeCAD, Gmsh, and CalculiX automation may be platform-sensitive.
- FEA settings may dominate results if not fixed and logged.
- LLM proposals may appear useful because of prompt tuning rather than a robust method.
- Manufacturability proxies may be too coarse to represent real FDM constraints.

## Future Extensions

- Alternative CAD backends such as Onshape.
- Alternative CAE backends such as SimScale, Ansys, or other solvers.
- Richer benchmarks, assemblies, and multi-load cases.
- Bayesian optimization and genetic algorithm baselines.
- Multi-material, slicing-aware, and real-printer feedback loops.
