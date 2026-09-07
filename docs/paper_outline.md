# Paper Outline

## Working Title

Closed-Loop LLM-Assisted Parametric Mechanical Design under Structural and Additive Manufacturing Constraints

## Abstract

To be written after benchmark results exist.

## 1. Introduction

- Motivation: engineering agents need deterministic validation, reproducible evidence, and fair comparison against non-LLM methods.
- Problem: prior work already shows LLM CAD generation, FEA automation, and physics-in-the-loop agents; the unresolved question is when an LLM proposal policy helps in a bounded engineering design loop.
- Framing: closed-loop parametric design under simultaneous structural and additive-manufacturing constraints.
- Approach: strict structured design proposals, deterministic CAD/CAE/DfAM validation, explicit feedback, and equal-budget baseline comparison.
- Claim discipline: do not claim novelty for CAD scripting, solver automation, or arbitrary LLM-generated CAD code.

## 2. Related Work

- LLM for CAD and multi-agent CAD generation.
- Automated FEA agents and CAD-CAE orchestration.
- Physics-in-the-loop engineering agents.
- LLMs as optimizers for parameterized engineering designs.
- DfAM/FDM constraints, including overhangs, support reduction, wall/feature thickness, build orientation, and manufacturability knowledge representation.
- Structural and manufacturing-constrained optimization as non-LLM prior art.

## 3. Method

- Backend-agnostic architecture
- Structured design parameter schema
- Deterministic CAD and CAE adapters
- Feedback representation
- Deterministic DfAM/FDM validators
- Baseline proposal policies

## Contributions

- A falsifiable benchmark for LLM proposal policies in bounded parametric mechanical design.
- A deterministic validation loop that separates proposal generation from physical and manufacturability evidence.
- Equal-budget comparison against random search, rule-based search, and a stronger conventional optimizer where feasible.
- Failure accounting for invalid proposals, CAD failures, meshing failures, FEA failures, and LLM cost.

## 4. Benchmark

- Bracket geometry
- Design variables
- Constraints
- Metrics

## 5. Experiments

- Trial setup
- Equal-budget baseline comparison
- Feasible-design rate and evaluations to first feasible design
- Best feasible objective and final mass
- Stress, displacement, and manufacturability metrics
- Invalid proposal, CAD failure, meshing failure, and FEA failure rates
- Token/API cost if useful

## Ablation

- No feedback or minimal feedback
- Physics feedback only
- DfAM/FDM feedback only
- Physics plus DfAM/FDM feedback
- Optional model-choice sensitivity if budget allows
- Failure analysis

## 6. Results

To be populated only after reproducible runs. Negative or null LLM results are valid outcomes.

## 7. Limitations

- Benchmark narrowness
- Backend sensitivity
- Proxy manufacturability limits
- LLM prompt sensitivity
- Possible conventional-optimizer advantage
- Dependence on frozen load, material, build-orientation, and threshold assumptions
- Limited generalization from one bracket family

## 8. Conclusion

To be written after results exist.
