# Research Gap

This document defines what the project is, what it is not, and what would count as meaningful evidence.

## 1. Established Capabilities

Prior work has already established several capabilities close to this project:

- LLM CAD generation exists. Recent systems generate or repair CAD scripts and parametric models from text, sketches, or multimodal prompts.
- Multi-agent CAD generation exists. MEDA and related systems show that specialized agent roles can improve parametric CAD generation.
- Automated FEA agent workflows exist. FeaGPT demonstrates end-to-end geometry, meshing, simulation, and analysis automation through an agentic interface.
- Physics-in-the-loop CAD exists. Physics-in-the-Loop explicitly embeds physical verification tools into an agentic CAD design loop.
- LLM parametric optimization exists. LLM-PSO evaluates an LLM as an optimizer for parameterized engineering shapes and compares against classical algorithms.
- LLM-assisted additive-manufacturing workflows exist. AutoMEX uses LLM agents and a knowledge graph for material extrusion workflow support.
- Non-LLM structural optimization can already incorporate AM constraints such as overhang, self-supporting geometry, support reduction, and minimum length scales.

## 2. What Is NOT Our Novelty

The project must not claim novelty for:

- Generating CAD from natural language.
- Scripting FreeCAD.
- Connecting CAD to meshing or FEA.
- Automating CalculiX or any other solver.
- Letting an LLM generate arbitrary Python CAD code.
- Using an LLM as a general engineering assistant.
- Adding a single overhang or wall-thickness check to a design loop.
- Showing one visually plausible bracket.
- Showing that an LLM can sometimes produce a feasible design.

FreeCAD, Gmsh, and CalculiX are first experimental backends. They are implementation choices, not the research contribution.

## 3. Remaining Research Gap

The intended gap is the intersection of:

- Bounded parametric mechanical design.
- Deterministic parametric CAD.
- Deterministic structural simulation.
- Deterministic FDM/DfAM manufacturability constraints.
- Closed-loop feedback from measured validation outputs.
- An LLM proposal policy that outputs only strict bounded parameters.
- Fair comparison against conventional optimization and search methods under the same evaluation budget.

The LLM is a decision/proposal component. It is not the geometry kernel, FEA solver, manufacturability oracle, or source of physical truth.

Among the representative works reviewed in `literature_map.md`, this intersection appears only partly covered. That is enough to motivate a careful benchmark, but not enough to claim global uniqueness.

## 4. Primary Research Question

Can an LLM-assisted engineering agent iteratively improve bounded parametric mechanical designs under simultaneous structural and additive-manufacturing constraints using deterministic feedback, and when does it provide value over conventional optimization or search methods?

## 5. Secondary Research Questions

RQ2: Does adding deterministic structural feedback improve feasibility and reduce structural constraint violations?

RQ3: Does adding deterministic DfAM/FDM feedback improve manufacturability without excessive structural or mass cost?

RQ4: Does an LLM proposal policy outperform rule-based, random-search, or stronger conventional optimizers under equal evaluation budgets?

RQ5: Which feedback signals contribute most to LLM performance?

RQ6: Under what conditions does the LLM proposal policy fail, produce invalid proposals, or cost more than its measurable benefit?

## 6. Falsifiable Hypotheses

H1: A structured LLM proposal policy will reach the first feasible design in fewer evaluations than random search for the frozen bracket benchmark.

H2: Adding structural feedback will increase feasible-design rate compared with no-feedback or minimal-feedback LLM proposals.

H3: Adding DfAM/FDM feedback will improve manufacturability metrics compared with physics-only feedback, but may increase mass or reduce structural margin.

H4: Under equal evaluation budgets, the LLM proposal policy may fail to outperform a rule-based or stronger conventional optimizer. This outcome is valid and must be reported, not treated as an implementation failure.

H5: Invalid proposal rate, CAD failure rate, meshing failure rate, FEA failure rate, and token/API cost can offset any apparent optimization benefit.

## 7. Novelty Risks

### Physics-in-the-Loop

Risk: The project could be mistaken for another physics-in-the-loop CAD agent.

Distinction required: Treat physics-in-the-loop as established prior work. The experiment must emphasize strict bounded parametric proposals, deterministic structural plus FDM/DfAM feedback, and baseline comparison.

### FeaGPT

Risk: The project could be mistaken for FEA workflow automation.

Distinction required: Do not claim FEA automation as novelty. The deterministic CAE path is infrastructure for evaluating proposal policies.

### MDO Agent

Risk: Broad LLM-driven MDO systems already combine parametric modeling, engineering software, and iterative optimization.

Distinction required: Keep the first paper narrower and more falsifiable: one bracket family, frozen benchmark assumptions, explicit failure rates, and conventional baselines.

### MEDA

Risk: Multi-agent CAD generation is close to the surface story of this project.

Distinction required: The core workflow must not rely on arbitrary LLM-generated CAD code. The CAD generator should be deterministic once parameters are chosen.

### LLM-PSO

Risk: LLM-as-optimizer has already been evaluated for parametric shape optimization with classical baselines.

Distinction required: Evaluate the LLM proposal policy in a different regime: deterministic CAD, structural FEA, FDM/DfAM constraints, invalid-proposal accounting, and bracket-specific manufacturability metrics.

### AutoMEX

Risk: LLM-assisted material extrusion workflows already exist.

Distinction required: Treat LLM/MEX workflow support as established. The project must test deterministic manufacturability metrics inside a closed parametric design loop, not only provide recommendations.
