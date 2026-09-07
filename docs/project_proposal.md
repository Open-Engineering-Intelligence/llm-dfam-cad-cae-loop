# Project Proposal

## Research Problem

LLM-assisted engineering design systems often demonstrate isolated CAD generation, but they rarely separate proposal generation from deterministic engineering validation. This project studies whether an LLM-assisted agent can improve a parametric mechanical design through repeated, auditable feedback from CAD, FEA, and DfAM validators.

## Research Positioning

This project is not positioned as a generic LLM-CAD demonstration, a FreeCAD scripting project, or an FEA automation demo. Prior work already establishes LLM CAD generation, multi-agent parametric CAD generation, physics-in-the-loop CAD, automated FEA agents, LLM-based parametric shape optimization, and LLM-assisted additive-manufacturing workflows.

The research position is narrower: test whether an LLM proposal policy adds measurable value in a deterministic closed loop over bounded parametric mechanical designs with simultaneous structural and FDM/DfAM manufacturability constraints. The LLM proposes structured bounded parameters only; deterministic CAD, CAE, and DfAM validators remain the sources of geometric, physical, and manufacturing evidence.

See:

- `docs/literature_map.md` for the representative prior-work landscape.
- `docs/research_gap.md` for the calibrated research gap and falsifiable hypotheses.
- `docs/research_roadmap.md` for the gated execution plan.

## Hypothesis

An LLM-assisted design agent that proposes strict structured parameters can improve feasible bracket designs across iterations when feedback includes deterministic structural and manufacturability measurements. Its value must be demonstrated against non-LLM baselines, not assumed from qualitative examples.

## Research Questions

- Can an LLM-assisted engineering agent iteratively improve bounded parametric mechanical designs under simultaneous structural and additive-manufacturing constraints using deterministic feedback?
- When does the LLM proposal policy provide value over conventional optimization or search methods under the same evaluation budget?
- Does feedback from deterministic CAD, FEA, and DfAM validators improve design quality over repeated iterations?
- Which feedback fields are most useful for the next design proposal?
- When does the LLM proposal policy fail, produce invalid proposals, or cost more than its measurable benefit?

## Contributions

- A minimal backend-agnostic closed-loop architecture for engineering design agents.
- A reproducible bracket benchmark with bounded parameters and explicit constraints.
- Interface contracts separating LLM proposal, CAD generation, CAE simulation, DfAM validation, and evaluation.
- Baseline comparisons designed to measure the value of LLM guidance over random search, rule-based search, and a stronger conventional optimizer where feasible.
- A research protocol that explicitly permits null or negative results for the LLM proposal policy.

## System Boundary

The first phase uses structured JSON-compatible parameters as the only design-action surface. The LLM does not generate arbitrary CAD scripts in the core workflow. CAD and CAE steps are deterministic adapters, initially FreeCAD and CalculiX, with Gmsh for meshing.

## Design Variables

- `thickness_mm`
- `width_mm`
- `rib_height_mm`
- `fillet_radius_mm`

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

1. Freeze the bracket benchmark, parameter bounds, material, load, boundary conditions, build orientation, objective, and PASS/FAIL evidence.
2. Implement deterministic CAD generation and export.
3. Automate meshing and static FEA.
4. Parse stress, displacement, mass, and failure states into structured records.
5. Add DfAM validators for overhang angle, wall thickness, and support proxy.
6. Implement deterministic closed-loop and baseline methods before adding the LLM agent.
7. Run repeated trials for each method under the same iteration budget.
8. Report convergence curves, feasibility rates, final objectives, failure modes, and LLM cost where useful.

## Risks

- FreeCAD, Gmsh, and CalculiX automation may be platform-sensitive.
- FEA settings may dominate results if not fixed and logged.
- LLM proposals may appear useful because of prompt tuning rather than a robust method.
- Manufacturability proxies may be too coarse to represent real FDM constraints.
- Conventional optimizers may outperform the LLM proposal policy; the experiment must preserve and report that outcome.

## Future Extensions

- Alternative CAD backends such as Onshape.
- Alternative CAE backends such as SimScale, Ansys, or other solvers.
- Richer benchmarks, assemblies, and multi-load cases.
- Bayesian optimization and genetic algorithm baselines.
- Multi-material, slicing-aware, and real-printer feedback loops.
