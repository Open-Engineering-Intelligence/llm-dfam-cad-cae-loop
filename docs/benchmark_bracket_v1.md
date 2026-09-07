# Benchmark Bracket v1

This is the normative Gate 1 specification for the first benchmark. It freezes a numerical engineering optimization problem with deterministic FDM/DfAM manufacturability constraints. It does not claim predictive accuracy for real printed parts without later calibration.

Schematic: `docs/figures/bracket_v1_geometry.svg`.

## 1. Benchmark Problem

Primary objective: minimize mass in grams.

Subject to:

- maximum von Mises stress <= 25 MPa;
- maximum displacement magnitude <= 2.0 mm;
- minimum wall/feature thickness >= 2.4 mm;
- unsupported overhang/support proxy passes;
- geometry is valid;
- CAD generation, meshing, or solver failure is recorded as a failed evaluation.

This is a static, single-load, small-deformation numerical benchmark. Nonlinear contact, bolt preload, dynamics, CFD, topology optimization, multi-material slicing, and real printer control are excluded from Benchmark v1.

## 2. Global Coordinate System

- Units: millimeters, newtons, megapascals, grams.
- Origin: center of the fixed rear face at the bottom edge of the arm, point `(0, 0, 0)`.
- X axis: span direction, positive from fixed rear face toward the loaded free end.
- Y axis: bracket width direction, positive to the viewer's left in the top view.
- Z axis: vertical bending direction and FDM build direction, positive upward.
- Build plate: plane `z = 0`.
- Build direction: vector `(0, 0, 1)`.

## 3. Geometry Definition

The bracket is the union of three deterministic solids plus root fillets:

1. Base block:
   - Occupies `0 <= x <= 8`, `-35 <= y <= 35`, `0 <= z <= 70`.
   - Rear mounting face is the plane `x = 0`.
2. Cantilever arm:
   - Occupies `8 <= x <= 108`, `-width_mm / 2 <= y <= width_mm / 2`, `0 <= z <= thickness_mm`.
   - The effective span for analytical sanity checks is `L = 100 mm`, measured from `x = 8` to `x = 108`.
3. Center triangular rib:
   - Centered on `y = 0`.
   - Rib thickness is fixed at `6 mm`, occupying `-3 <= y <= 3`.
   - Rib starts at `x = 8` with height `rib_height_mm` above the arm top.
   - Rib tapers linearly to zero height at `x = 98`, leaving the load pad clear.
   - Rib z-range at position `x` is `thickness_mm <= z <= thickness_mm + rib_height_mm * (98 - x) / 90` for `8 <= x <= 98`.
4. Fillets:
   - `fillet_radius_mm` is applied to the arm/base root junction and rib/arm junction where supported by the CAD backend.
   - The same nominal radius is used for deterministic generation.
   - If a future CAD backend cannot create a requested fillet without invalid geometry, that candidate is a failed evaluation unless the benchmark is amended.

## 4. Mounting and Holes

Benchmark v1 models no bolt holes. The mounting condition is an ideal fixed rear face on `x = 0`.

Reason: bolt holes, bolt preload, washer contact, bearing stress, and horizontal-hole FDM effects introduce additional modeling choices that are not needed for the first closed-loop proposal-policy benchmark.

Rejected alternative: make `hole_diameter_mm` a design variable. This was rejected for v1 because it adds CAD instability, stress-concentration interpretation, and support ambiguity without being necessary for the first 3-5 dimensional benchmark.

## 5. Load and Boundary Conditions

- Fixed surface: the rear face `x = 0` of the base block.
- Load type: static downward tip force.
- Force magnitude: `150 N`.
- Force vector: `(0, 0, -150) N`.
- Load application region: top surface of the arm over `98 <= x <= 108`, full current bracket width in `y`, at `z = thickness_mm`.
- Load distribution: uniformly distributed pressure or equivalent nodal load over the load pad in later FEA.
- Bolt/contact behavior: excluded.
- Dynamics and nonlinear geometry: excluded.

The 150 N load is retained as a benchmark load, not as a universal service load for printed brackets. Gate 6 results must not claim real printed-part load capacity without experimental calibration.

## 6. Fixed Parameters

| Parameter | Frozen Value | Rationale |
|---|---:|---|
| Span length | 100 mm | Small enough for inexpensive FEA and simple beam sanity checks. |
| Base depth | 8 mm | Gives a fixed rear block for stable CAD and boundary-condition application. |
| Base width | 70 mm | Allows the full variable arm-width range while keeping a fixed mounting reference. |
| Base height | 70 mm | Keeps the rib and arm attached to a simple fixed block. |
| Load pad length | 10 mm | Avoids a singular point load in FEA. |
| Rib thickness | 6 mm | Keeps rib generation deterministic without adding another variable. |
| Build direction | `(0, 0, 1)` | Makes DfAM overhang definitions explicit and reproducible. |
| Nozzle diameter assumption | 0.4 mm | Common FDM reference assumption for wall-thickness reasoning. |
| Layer height assumption | 0.2 mm | Common FDM reference assumption; not used for structural prediction. |

## 7. Design Variables

| Variable | Lower Bound | Upper Bound | Units | Rationale | Dependencies and Invalid Combinations |
|---|---:|---:|---|---|---|
| `thickness_mm` | 4.0 | 14.0 | mm | Dominant bending-stiffness and mass variable. | Must exceed minimum wall thickness and support requested fillet radius. |
| `width_mm` | 30.0 | 80.0 | mm | Controls section width, mass, and lateral footprint. | Must remain wider than fixed 6 mm rib. |
| `rib_height_mm` | 0.0 | 35.0 | mm | Adds stiffness without making the whole arm thick. | Zero means no effective rib; high ribs must remain inside base height. |
| `fillet_radius_mm` | 1.0 | 8.0 | mm | Controls root stress concentration and CAD smoothness. | Invalid if CAD backend cannot fit the fillet at root or rib junctions. |

## 8. Material Model

Selected model: PLA-like isotropic reference polymer.

Machine-readable values:

- density: `1240 kg/m3`;
- Young's modulus: `3250 MPa`;
- Poisson's ratio: `0.36`;
- tensile yield reference: `52.5 MPa`;
- allowable von Mises stress: `25 MPa`.

Rationale: the material is a numerical reference intended to keep the first benchmark simple. The Young's modulus and yield reference are close to values reported in UltiMaker PLA technical data for printed specimens; density 1.24 g/cm3 is a common PLA-filament datasheet value. Poisson's ratio is an engineering assumption for the isotropic numerical model and must not be treated as calibrated printed-material evidence.

Claims supported:

- numerical comparisons among proposal policies under the same deterministic material model;
- FEA setup regression checks;
- relative optimization behavior within Benchmark v1.

Claims not supported:

- arbitrary FDM PLA printed-part strength;
- anisotropic layer-bond behavior;
- fatigue, creep, fracture, or environmental durability;
- printer- or slicer-specific predictive accuracy.

Future experimental calibration may replace this model with measured orthotropic or process-specific material properties.

Reference notes:

- UltiMaker PLA technical data reports printed-specimen tensile modulus and yield values close to the selected numerical reference: https://ultimaker.com/materials/pla/
- Prusament PLA datasheets and similar vendor data commonly report density near `1.24 g/cm3`; this supports the density scale but not universal printed-part strength.
- Published studies and vendor datasheets show that FDM/FFF mechanical properties depend on print orientation, process settings, infill, raster, and layer bonding. Benchmark v1 therefore treats the material as an idealized numerical model.

## 9. Structural Constraints

- Stress metric: maximum von Mises stress from the deterministic static FEA result.
- Stress limit: `25 MPa`.
- Interpretation: approximately a factor-of-two numerical design margin relative to the 52.5 MPa tensile yield reference; this is a benchmark safety margin, not a certified printed-part safety factor.
- Displacement metric: maximum displacement magnitude anywhere in the model, with the loaded tip region expected to dominate.
- Displacement limit: `2.0 mm`.
- Interpretation: serviceability-style deflection cap equal to 2% of the 100 mm effective span.

## 10. DfAM/FDM Assumptions

- Process model: single-material FDM/MEX reference process.
- Build direction: `(0, 0, 1)`.
- Nozzle diameter: `0.4 mm`.
- Layer height: `0.2 mm`.
- Minimum wall/feature thickness: `2.4 mm`, equal to six nominal nozzle widths. This is intentionally more conservative than the two-perimeter minimum often used for non-structural prints.
- Bridges: excluded from Benchmark v1.
- Enclosed cavities: excluded from Benchmark v1 geometry.
- Support requirement: the design passes only if the deterministic support proxy reports no support required.

Overhang/support proxy:

For every exterior surface region not touching the build plate, compute an outward unit normal `n`. Let build direction be `b = (0, 0, 1)` and downward direction be `d = -b`.

A surface region is unsupported-risk if:

$$
n \cdot d > \cos(45^\circ)
$$

and its connected area is at least `25 mm2`. Build-plate contact faces on `z = 0` are exempt because they are supported by the print bed. Benchmark v1 passes the support proxy only if no unsupported-risk region is present.

This convention treats the usual 45-degree rule as a deterministic geometry rule. It does not claim all real printers fail above that threshold or succeed below it.

Reference notes:

- Prusa's modeling guidance describes clean-printable overhang ranges as printer/settings dependent, commonly around 45 to 60 degrees: https://help.prusa3d.com/article/modeling-with-3d-printing-in-mind_164135
- Hubs' FDM design guidance describes support use for wall angles above 45 degrees and warns that overhang behavior is process dependent: https://www.hubs.com/knowledge-base/how-design-parts-fdm-3d-printing/
- The `2.4 mm` wall/feature threshold is a conservative benchmark rule, not a minimum printable wall claim. It corresponds to six nominal 0.4 mm nozzle widths for a functional-load benchmark.

Conceptual validator:

```text
manufacturability(candidate)
  -> min_wall_thickness_mm
  -> max_unsupported_downward_normal_alignment
  -> unsupported_region_area_mm2
  -> support_required
  -> PASS/FAIL
```

The LLM must never decide manufacturability subjectively.

## 11. Objective, Feasibility, and Failure

Primary objective:

```text
minimize mass_g
```

A feasible design is a candidate that:

- satisfies all variable bounds;
- produces valid deterministic geometry;
- meshes successfully;
- completes deterministic static FEA;
- has maximum von Mises stress <= 25 MPa;
- has maximum displacement <= 2.0 mm;
- has minimum wall/feature thickness >= 2.4 mm;
- requires no support under the frozen support proxy.

A failed evaluation is any candidate with invalid geometry, CAD generation failure, meshing failure, solver failure, missing required result fields, or DfAM/structural constraint failure. Failed evaluations count against the proposing policy's evaluation budget.

## 12. Evaluation Budget

One expensive evaluation means one valid parameter proposal submitted to the deterministic CAD/CAE/DfAM evaluation pipeline, regardless of whether later CAD, mesh, solver, or validation stages fail.

Gate 1 freezes an initial per-policy evaluation budget of `30` expensive evaluations. This replaces the provisional `20` iteration value because the benchmark must support random search and a conventional optimizer without being so large that early CAD/CAE development becomes slow.

LLM retries that fail schema validation before CAD generation are not expensive evaluations, but they must be logged separately as invalid proposal attempts and count against LLM reliability/cost metrics.

Repeated-trial count is not frozen in Gate 1. It must be justified at Gate 6 after per-evaluation runtime is measured.

## 13. Acceptance Table

| Item | Frozen Value / Definition | Rationale | Evidence | Revisit Condition |
|---|---|---|---|---|
| Geometry family | Fixed rear block, rectangular cantilever arm, centered triangular rib, deterministic fillets | Simple CAD, cheap FEA, meaningful stiffness/mass tradeoff | This spec and config | CAD generation proves unstable or FEA mesh quality is unacceptable |
| Coordinate system | X span, Y width, Z build/up direction, origin at rear-face arm-bottom center | Removes load/build ambiguity | This spec | Only with migration note and config update |
| Mounting | Fixed rear face, no modeled holes or bolt contact | Avoids contact and bolt-preload confounds | This spec | Later benchmark studies bolt/hole effects |
| Load | 150 N downward over 10 mm distal load pad | Static benchmark load with non-singular FEA application | This spec; sanity check | Beam sanity check or FEA pilot shows no feasible region |
| Material | PLA-like isotropic reference polymer | Numerical benchmark, not printed-part prediction | Vendor-like values and documented limitations | Experimental calibration or orthotropic material model is added |
| Variables | `thickness_mm`, `width_mm`, `rib_height_mm`, `fillet_radius_mm` | Four-dimensional space keeps baselines tractable | This spec | Variable proves non-identifiable or CAD-unstable |
| Objective | Minimize mass | Clear primary objective avoids arbitrary weighted score | This spec | Later multi-objective study |
| Stress constraint | max von Mises <= 25 MPa | Numerical margin below yield reference | This spec | Material model or load case changes |
| Displacement constraint | max displacement <= 2.0 mm | 2% of effective span | This spec | Gate 2 FEA sanity indicates wrong scale |
| DfAM wall constraint | min thickness >= 2.4 mm | Six nominal 0.4 mm nozzle widths for functional part conservatism | This spec | Process assumptions change |
| DfAM support proxy | no non-bed exterior region with `n dot -b > cos(45 deg)` and area >= 25 mm2 | Deterministic 45-degree support rule | This spec | Physical print calibration or slicer-based proxy added |
| Evaluation budget | 30 expensive evaluations per policy | Enough for first baseline comparison, still cheap for PoC | This spec | Gate 2 runtime makes budget impractical |

## 14. Gate 1 Status

Gate 1 can be declared PASS only if this document, `configs/bracket_default.yaml`, `docs/benchmark_sanity_check.md`, and the decision log remain consistent after review and CI checks. After Gate 1 PASS, the next implementation task is Issue #2. Until then, Issue #2 must not begin.
