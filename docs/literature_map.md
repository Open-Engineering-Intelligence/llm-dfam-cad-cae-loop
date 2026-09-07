# Literature Map

This document freezes the v0.1 research landscape for the project before CAD, CAE, DfAM, or LLM-agent implementation begins. It is an evidence map, not a claim that the project is globally unique.

## Review Question

Among representative work on LLM-assisted CAD, automated FEA, physics-in-the-loop engineering agents, LLM-based optimization, and DfAM/manufacturing constraints, what remains unresolved for a closed-loop parametric mechanical design benchmark that combines deterministic structural feedback, deterministic FDM/DfAM feedback, and fair comparison against conventional optimizers?

## Scope and Exclusions

Included:

- LLM or agentic systems for CAD, CAE, MDO, or engineering proposal loops.
- Parametric design and shape optimization where the design variables are bounded and machine-readable.
- DfAM/FDM manufacturability constraints, especially overhang, support reduction, self-supporting geometry, minimum feature size, and wall-thickness reasoning.
- Structural or manufacturing-constrained optimization that can serve as a non-LLM baseline or methodological warning.

Excluded for this v0.1 freeze:

- Generic chat-based CAD demos without engineering validation.
- Pure topology optimization work unless it directly informs overhang, support, or structural-manufacturing constraints.
- Printer-control, slicing, and multi-material process papers unless they directly bear on first-phase FDM manufacturability validation.

## Source Base and Verification Status

The six closest AI-engineering works were checked against arXiv, DOI landing pages, and Crossref metadata where available. DfAM and structural-manufacturing references were checked through DOI/Crossref metadata and publisher pages where accessible. Some recent arXiv works may later acquire journal or conference metadata; do not silently replace them without checking the final version.

## Closest Prior Work

### Physics-in-the-Loop: A Hybrid Agentic Architecture for Validated CAD Engineering Design

- Authors: Elias Berger, Muhammad Usama, Jan Mehlstaubl, Bernhard Saske, Kristin Paetzold-Byhain.
- Year: 2026.
- Venue: arXiv preprint; listed as accepted in IJCAI-ECAI 2026 Special Track on AI4Tech.
- DOI / arXiv: arXiv:2605.19717; https://doi.org/10.48550/arXiv.2605.19717.
- Research problem: LLMs can generate CAD but do not by themselves provide reliable physical understanding for engineering design.
- Method: Hybrid agentic-physical architecture with agents that plan, generate, evaluate, and revise designs using knowledge-based physical verification tools.
- CAD involvement: Yes; generative CAD is central.
- CAE / physics involvement: Yes; explicit physical verification is embedded in the loop.
- Iterative feedback: Yes; closed-loop sequential decision making with feedback.
- Optimization method: Agentic revision process; not presented primarily as a conventional optimizer comparison.
- DfAM / manufacturability involvement: Not central in the verified abstract.
- Baselines: Compared against similar agentic CAD methods.
- Main result: Reports more complex physically verified designs and a compile-rate improvement compared with similar agentic methods.
- Limitation relative to this project: Does not make simultaneous FDM/DfAM manufacturability constraints and fair comparison against conventional optimizers the central benchmark.
- Why it matters: It is the closest warning against claiming physics-in-the-loop CAD itself as novelty.

### FeaGPT: an End-to-End agentic-AI for Finite Element Analysis

- Authors: Yupeng Qi, Ran Xu, Xu Chu.
- Year: 2025.
- Venue: arXiv preprint.
- DOI / arXiv: arXiv:2510.21993; https://doi.org/10.48550/arXiv.2510.21993.
- Research problem: Natural-language access to geometry, meshing, simulation, and analysis workflows for FEA.
- Method: Agentic Geometry-Mesh-Simulation-Analysis pipeline that interprets specifications, generates meshes, configures FEA, and analyzes results.
- CAD involvement: Yes; geometry is part of the end-to-end workflow.
- CAE / physics involvement: Yes; FEA automation is central, with CalculiX simulations reported.
- Iterative feedback: Yes; the abstract describes closed-loop iteration and multi-objective analysis.
- Optimization method: Workflow-level iteration and exploration; not primarily a fair baseline comparison of proposal policies.
- DfAM / manufacturability involvement: Not central in the verified abstract.
- Baselines: Not enough verified detail for this freeze; mark as needing full-text review before making baseline claims.
- Main result: Reports successful natural-language-to-validated-CalculiX workflows for industrial rotating machinery cases and 432 NACA airfoil configurations.
- Limitation relative to this project: Focuses on FEA workflow automation rather than constrained parametric bracket redesign under structural plus FDM/DfAM constraints.
- Why it matters: It establishes that automated FEA agent workflows are not our novelty.

### A Multidisciplinary Design and Optimization (MDO) Agent Driven by Large Language Models

- Authors: Bingkun Guo, Wentian Li, Xiaojian Liu, Jiaqi Luo, Zibin Yu, Dalong Dong, Shuyou Zhang, Yiming Zhang.
- Year: 2025.
- Venue: arXiv preprint.
- DOI / arXiv: arXiv:2511.17511; https://doi.org/10.48550/arXiv.2511.17511.
- Research problem: Accelerating mechanical design and improving design quality through LLM-driven multidisciplinary design and optimization.
- Method: Semi-automated agent with natural-language-driven parametric modeling, RAG-supported conceptualization, and engineering-software orchestration.
- CAD involvement: Yes; parametric 3D CAD model construction is central.
- CAE / physics involvement: Yes; FEA is used for verification and optimization.
- Iterative feedback: Yes; iterative optimization through tool calls is described.
- Optimization method: MDO-style orchestration; details require full-text review before judging exact optimizer baselines.
- DfAM / manufacturability involvement: Not central in the verified abstract.
- Baselines: Not enough verified detail for this freeze.
- Main result: Validated on a gas-turbine blade, machine-tool column, and fractal heat sink, reporting reduced manual scripting/setup effort and design exploration benefits.
- Limitation relative to this project: Broader MDO automation rather than a narrow falsifiable benchmark for LLM proposal value under simultaneous structural and FDM/DfAM constraints.
- Why it matters: It overlaps with LLM-driven parametric CAD plus FEA orchestration.

### MEDA: A Multi-Agent System For Parametric CAD Model Creation

- Authors: Nirmal Panta, Saugat Kafley, Rujal Acharya, Sashank Parajuli, Dikshya Parajuli, Prince Panta, Saroj Belbase, Sudikshya Pant, Amit Regmi, Akio Tanaka, Christopher McComb.
- Year: 2025.
- Venue: ASME IDETC-CIE 2025, Volume 3B: 51st Design Automation Conference.
- DOI / arXiv: https://doi.org/10.1115/DETC2025-163946.
- Research problem: Automating parametric CAD model creation without requiring users to master CAD software or scripting libraries.
- Method: Mechanical Engineering Design Agents, a multi-agent framework using multimodal LLM capabilities and zero-shot/one-shot agent roles.
- CAD involvement: Yes; CAD script generation and model creation are central.
- CAE / physics involvement: No verified central physics or FEA loop.
- Iterative feedback: Yes for CAD-generation refinement and visual/model assessment.
- Optimization method: Not primarily an engineering optimizer.
- DfAM / manufacturability involvement: Not central.
- Baselines: Prior CAD-generation methods; verified abstract reports a reduction in median point-cloud distance versus prior work.
- Main result: Reported 99% script execution success on 200 CAD prompts and median point-cloud distance 0.0555, a 56% reduction compared with prior work.
- Limitation relative to this project: Strong on CAD creation, weak for deterministic structural and manufacturability validation with optimizer baselines.
- Why it matters: It makes clear that multi-agent parametric CAD generation is already established nearby work.

### Using Large Language Models for Parametric Shape Optimization / LLM-PSO

- Authors: Xinxin Zhang, Zhuoqun Xu, Guangpu Zhu, Chien Ming Jonathan Tay, Yongdong Cui, Boo Cheong Khoo, Lailai Zhu.
- Year: 2024 arXiv preprint; 2025 journal article.
- Venue: Physics of Fluids 37(8), article 083601.
- DOI / arXiv: arXiv:2412.08072; https://doi.org/10.1063/5.0273363.
- Research problem: Whether LLMs can serve as optimizers for parameterized engineering shapes.
- Method: LLM-PSO uses an LLM in the spirit of evolutionary strategies to choose parametric shapes for flow optimization.
- CAD involvement: Parameterized shapes are central; conventional CAD workflow is not the focus.
- CAE / physics involvement: Yes; flow-optimization benchmarks provide physics-based objective evaluations.
- Iterative feedback: Yes; iterative optimization over candidate shapes.
- Optimization method: LLM-based optimizer compared with classical optimization algorithms.
- DfAM / manufacturability involvement: None in the verified abstract.
- Baselines: Classical optimization algorithms.
- Main result: Reports optimal shapes consistent with benchmark solutions and generally faster convergence than classical optimizers in the studied flow cases.
- Limitation relative to this project: Fluid shape optimization without CAD-CAE-FDM manufacturability coupling.
- Why it matters: It is the closest evidence that LLM proposal policies can be evaluated as optimizers under baseline comparison.

### AutoMEX: Streamlining material extrusion with AI agents powered by large language models and knowledge graphs

- Authors: Haolin Fan, Junlin Huang, Jilong Xu, Yifei Zhou, Jerry Ying Hsi Fuh, Wen Feng Lu, Bingbing Li.
- Year: 2025.
- Venue: Materials & Design 251, article 113644.
- DOI / arXiv: https://doi.org/10.1016/j.matdes.2025.113644.
- Research problem: Material extrusion workflows suffer from limited automation and fragmented domain knowledge.
- Method: AutoMEX integrates LLM-based AI agents with a literature-derived knowledge graph to recommend material selection, process parameters, and design considerations.
- CAD involvement: Design considerations are included, but deterministic parametric CAD generation is not the central verified contribution.
- CAE / physics involvement: Not central in the verified metadata/abstract.
- Iterative feedback: Workflow support and recommendations; not verified as a deterministic CAD-CAE redesign loop.
- Optimization method: Knowledge-graph and LLM recommendation rather than conventional optimizer comparison.
- DfAM / manufacturability involvement: Yes; material extrusion and additive-manufacturing process knowledge are central.
- Baselines: Needs full-text review before recording precise baselines.
- Main result: Reports an LLM/KG framework for improving accessibility and efficiency of MEX workflow recommendations.
- Limitation relative to this project: Does not appear to center a deterministic structural plus FDM manufacturability feedback loop over bounded CAD parameters with optimizer baselines.
- Why it matters: It establishes nearby LLM-assisted additive-manufacturing workflow support.

## DfAM and Manufacturing-Constrained Optimization Anchors

### Design for Additive Manufacturing: Trends, opportunities, considerations, and constraints

- Authors: Mary Kathryn Thompson, Giovanni Moroni, Tom Vaneker, Georges Fadel, R. Ian Campbell, Ian Gibson, Alain Bernard, Joachim Schulz, Patricia Graf, Bhrigu Ahuja, Filomeno Martina.
- Year: 2016.
- Venue: CIRP Annals 65(2), 737-760.
- DOI / arXiv: https://doi.org/10.1016/j.cirp.2016.05.004.
- Research problem: Surveying opportunities, constraints, and design considerations for additive manufacturing.
- Method: Review/synthesis.
- CAD involvement: Design workflow context; not a specific CAD generator.
- CAE / physics involvement: Contextual, not the central contribution.
- Iterative feedback: Not central.
- Optimization method: Review-level discussion rather than an optimizer.
- DfAM / manufacturability involvement: Central.
- Baselines: Not applicable.
- Main result: Establishes DfAM constraints and design-rule framing as a mature topic.
- Limitation relative to this project: Does not evaluate LLM proposal policies.
- Why it matters: Provides broad DfAM grounding and cautions against treating manufacturability rules as new.

### Design for Additive Manufacturing - Element transitions and aggregated structures

- Authors: Guido A. O. Adam, Detmar Zimmer.
- Year: 2014.
- Venue: CIRP Journal of Manufacturing Science and Technology 7(1), 20-28.
- DOI / arXiv: https://doi.org/10.1016/j.cirpj.2013.10.001.
- Research problem: Translating additive-manufacturing design restrictions into usable design principles.
- Method: DfAM rule/principle development for element transitions and aggregated structures.
- CAD involvement: Design-rule application context; not an automated CAD agent.
- CAE / physics involvement: Not central.
- Iterative feedback: Not central.
- Optimization method: Not central.
- DfAM / manufacturability involvement: Central.
- Baselines: Not applicable.
- Main result: Provides design principles that can inform benchmark manufacturability checks.
- Limitation relative to this project: Rule framing only; no closed-loop LLM or structural simulation benchmark.
- Why it matters: Helps define what must be justified before freezing wall/feature assumptions.

### Topology optimization considering overhang constraints: Eliminating sacrificial support material in additive manufacturing through design

- Authors: Andrew T. Gaynor, James K. Guest.
- Year: 2016.
- Venue: Structural and Multidisciplinary Optimization 54(5), 1157-1172.
- DOI / arXiv: https://doi.org/10.1007/s00158-016-1551-x.
- Research problem: Reducing or eliminating support material by embedding self-supporting angle constraints in topology optimization.
- Method: Projection-based topology optimization with minimum length-scale and support-region projections.
- CAD involvement: Produces optimized structures; not a CAD-agent workflow.
- CAE / physics involvement: Yes; standard minimum-compliance structural optimization.
- Iterative feedback: Yes within deterministic optimization.
- Optimization method: Topology optimization, including MMA in the publisher notes.
- DfAM / manufacturability involvement: Central; overhang angle, support, and minimum length scale.
- Baselines: Standard topology-optimization examples and constraint variants.
- Main result: Demonstrates solutions satisfying minimum length scale, overhang angle, and volume constraints.
- Limitation relative to this project: No LLM proposal policy; topology optimization differs from bounded parametric bracket redesign.
- Why it matters: A strong conventional baseline family already integrates structural and AM support constraints.

### Topology optimization of 3D self-supporting structures for additive manufacturing

- Authors: Matthijs Langelaar.
- Year: 2016.
- Venue: Additive Manufacturing 12, 60-70.
- DOI / arXiv: https://doi.org/10.1016/j.addma.2016.06.010.
- Research problem: Designing 3D self-supporting structures for additive manufacturing.
- Method: Deterministic topology optimization with self-supporting constraints.
- CAD involvement: Optimized geometry generation; not parametric CAD-agent generation.
- CAE / physics involvement: Yes; structural optimization.
- Iterative feedback: Yes within the optimizer.
- Optimization method: Topology optimization.
- DfAM / manufacturability involvement: Central; self-supporting geometry.
- Baselines: Needs full-text review for exact baseline setup.
- Main result: Establishes 3D self-supporting AM optimization as prior art.
- Limitation relative to this project: No LLM; no strict parametric CAD proposal loop.
- Why it matters: Prevents overclaiming support-free or self-supporting optimization novelty.

### Structural optimization under overhang constraints imposed by additive manufacturing technologies

- Authors: G. Allaire, C. Dapogny, R. Estevez, A. Faure, G. Michailidis.
- Year: 2017.
- Venue: Journal of Computational Physics 351, 295-328.
- DOI / arXiv: https://doi.org/10.1016/j.jcp.2017.09.041.
- Research problem: Incorporating additive-manufacturing overhang constraints into structural optimization.
- Method: Structural optimization under manufacturability constraints.
- CAD involvement: Optimized geometry context; not CAD-agent generation.
- CAE / physics involvement: Yes; structural optimization.
- Iterative feedback: Yes within deterministic optimization.
- Optimization method: Shape/topology optimization methods.
- DfAM / manufacturability involvement: Central; overhang constraints.
- Baselines: Needs full-text review for exact comparisons.
- Main result: Establishes overhang-constrained structural optimization as mature prior work.
- Limitation relative to this project: No LLM proposal policy and no bracket-specific deterministic CAD-CAE-FDM loop.
- Why it matters: A key prior for simultaneous structural and manufacturability constraints.

### A Design for Additive Manufacturing Ontology to Support Manufacturability Analysis

- Authors: Samyeon Kim, David W. Rosen, Paul Witherell, Hyunwoong Ko.
- Year: 2019.
- Venue: Journal of Computing and Information Science in Engineering 19(4), article 041014.
- DOI / arXiv: https://doi.org/10.1115/1.4043531.
- Research problem: Supporting manufacturability analysis with reusable DfAM knowledge representation.
- Method: DfAM ontology and rule-oriented manufacturability analysis.
- CAD involvement: Manufacturing features and design features are represented; the work includes manufacturability-analysis context rather than a closed CAD-CAE loop.
- CAE / physics involvement: Not central.
- Iterative feedback: Not central.
- Optimization method: Not central.
- DfAM / manufacturability involvement: Central.
- Baselines: Not applicable.
- Main result: Establishes structured DfAM knowledge as a reusable support for manufacturability analysis.
- Limitation relative to this project: Does not test LLM proposal policies or structural simulation feedback.
- Why it matters: Supports the decision that DfAM validity should come from explicit measurable criteria, not subjective LLM judgment.

## Comparison Table

| Work | Parametric CAD | Deterministic Physics | Iterative Redesign | LLM Optimization | DfAM/FDM Constraints | Traditional Optimizer Baseline | Key Gap |
|---|---|---|---|---|---|---|---|
| Physics-in-the-Loop | Yes | Yes | Yes | Agentic proposal/revision | Not central | Not central in verified abstract | Does not center FDM/DfAM plus fair optimizer baseline comparison |
| FeaGPT | Geometry workflow | Yes, FEA | Yes | Workflow agent | Not central | Not verified | Focuses on FEA automation rather than bracket redesign policy comparison |
| MDO Agent | Yes | Yes, through FEA tool calls | Yes | MDO agent | Not central | Not verified | Broad MDO system, not the narrow simultaneous structural/FDM benchmark |
| MEDA | Yes | No | CAD refinement | Multi-agent CAD generation | Not central | Prior CAD-generation methods | No deterministic structural/DfAM feedback loop |
| LLM-PSO | Parameterized shapes | Yes, flow objectives | Yes | Yes | No | Yes | No CAD-CAE-FDM manufacturing loop |
| AutoMEX | Limited/indirect | Not central | Recommendation workflow | Agentic recommendation | Yes, MEX | Not verified | No deterministic structural redesign benchmark |
| Thompson et al. 2016 | Design context | Contextual | No | No | Yes | No | DfAM review, not proposal-policy evaluation |
| Adam and Zimmer 2014 | Design context | No | No | No | Yes | No | Design rules, not closed-loop optimization |
| Gaynor and Guest 2016 | Optimized structures | Yes | Optimizer loop | No | Yes | Conventional topology optimization | Strong non-LLM prior; different design representation |
| Langelaar 2016 | Optimized structures | Yes | Optimizer loop | No | Yes | Conventional topology optimization | Strong non-LLM prior; no LLM proposal policy |
| Allaire et al. 2017 | Optimized structures | Yes | Optimizer loop | No | Yes | Conventional structural optimization | Strong non-LLM prior; no structured LLM loop |
| Kim et al. 2019 | Feature representation | No | No | No | Yes | No | DfAM knowledge representation, not closed-loop design |

## Evidence Clusters

### Cluster 1: Agentic CAD generation

Settled: LLM and multimodal multi-agent systems can generate or refine parametric CAD models in constrained settings.

Contested: Reliability, physical correctness, CAD semantic fidelity, and generalization remain open.

Missing for this project: A benchmark where CAD generation is deterministic and the LLM is judged only as a bounded proposal policy under structural and FDM/DfAM feedback.

Key sources: MEDA; Physics-in-the-Loop; MDO Agent.

### Cluster 2: Automated CAE / physics workflows

Settled: Agentic systems can orchestrate geometry, meshing, simulation, and analysis workflows.

Contested: Robustness of boundary-condition inference, solver setup validity, and reproducible evidence across backends.

Missing for this project: A deliberately narrow experiment that removes CAE automation as novelty and uses deterministic physics feedback to evaluate proposal policies.

Key sources: FeaGPT; MDO Agent; Physics-in-the-Loop.

### Cluster 3: LLMs as optimizers

Settled: LLMs can be evaluated as proposal mechanisms for parameterized engineering shapes, and such work can include classical optimizer baselines.

Contested: Whether gains persist outside specific benchmark distributions, prompts, and model choices.

Missing for this project: Evidence under simultaneous structural and FDM/DfAM constraints with deterministic CAD and FEA adapters.

Key source: LLM-PSO.

### Cluster 4: DfAM and FDM manufacturability constraints

Settled: Overhangs, support requirements, minimum length scale, feature size, build orientation, and process-dependent material assumptions are established DfAM concerns.

Contested: Which proxies are adequate for a first FDM bracket benchmark and how printer/material settings should be frozen.

Missing for this project: A documented Gate 1 benchmark freeze that justifies specific numerical thresholds before implementation consumes them.

Key sources: Thompson et al. 2016; Adam and Zimmer 2014; Kim et al. 2019; AutoMEX.

### Cluster 5: Structural plus manufacturing constrained optimization

Settled: Conventional structural optimization can integrate AM constraints such as self-supporting angles, support regions, and minimum length scale.

Contested: How these topology/shape optimization results translate to low-dimensional parametric CAD variables and fair LLM-agent baselines.

Missing for this project: A conventional optimizer baseline in the same bounded parametric bracket space.

Key sources: Gaynor and Guest 2016; Langelaar 2016; Allaire et al. 2017.

## Contribution Diagnosis

Claimed gap: The project should study whether an LLM-assisted engineering agent, acting only as a structured parameter proposal policy, adds value in a deterministic closed loop over bounded mechanical designs with simultaneous structural and FDM/DfAM constraints.

Verdict: Partly holds. The ingredients are not individually novel: LLM CAD, multi-agent CAD, FEA agents, physics-in-the-loop CAD, LLM parametric optimization, and AM agent workflows already exist. Among the representative works reviewed here, the sharper contribution is the experimental intersection: deterministic CAD-CAE-DfAM evaluation, strict bounded parameter proposals, simultaneous structural and FDM manufacturability constraints, and fair comparison against rule-based, random-search, and stronger conventional optimizers under equal budgets.

Better contribution frame: A reproducible benchmark and experimental protocol for testing when LLM proposal policies help in closed-loop engineering design, rather than a claim that LLMs can generate CAD or automate FEA.

## Sentences the Review Must Earn

- The project must not claim novelty for LLM-generated CAD, multi-agent CAD creation, automated FEA workflows, physics-in-the-loop CAD, or LLM-based parametric optimization.
- The project may claim, if supported by experiments, evidence about when an LLM proposal policy improves or fails to improve bounded parametric mechanical design under deterministic structural and FDM/DfAM feedback.
- The project must allow the LLM method to lose to conventional optimizers.
- Numerical assumptions in `configs/bracket_default.yaml` are provisional until Gate 1 justifies them.

## Sources Needing Full-Text Follow-Up

| Source | Why |
|---|---|
| FeaGPT | Exact baselines, retry/failure handling, and optimization details need full-text review before comparison claims. |
| MDO Agent | Exact optimizer formulation and baseline comparisons need full-text review. |
| AutoMEX | Need full-text review for evaluation design, baseline methods, and whether feedback is iterative or advisory. |
| Langelaar 2016 | Need full-text review for exact constraints and baselines before borrowing evaluation language. |
| Allaire et al. 2017 | Need full-text review before mapping its mathematical overhang formulation into a benchmark proxy. |
