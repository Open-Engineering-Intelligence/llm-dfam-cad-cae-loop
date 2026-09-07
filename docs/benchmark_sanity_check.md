# Benchmark Sanity Check

This document defines a simple analytical reference model for Benchmark Bracket v1. It is not the final evaluator and must not replace deterministic CAD/CAE validation.

## Purpose

The sanity model exists to catch unit mistakes, load-direction mistakes, boundary-condition errors, and gross FEA setup failures once the CalculiX pipeline is implemented.

## Simplified Model

Approximate the bracket arm as a rectangular Euler-Bernoulli cantilever beam:

- fixed at the arm root;
- loaded by a downward tip force;
- effective length `L`;
- rectangular cross-section width `b` and thickness `h`;
- Young's modulus `E`.

The model ignores:

- the base block;
- triangular rib stiffness;
- fillets;
- stress concentrations;
- shear deformation;
- 3D load-pad distribution;
- printed-material anisotropy.

## Equations

Maximum bending moment at the fixed root:

$$
M_\mathrm{max} = F L
$$

Second moment of area for the rectangular arm section:

$$
I = \frac{b h^3}{12}
$$

Maximum bending stress:

$$
\sigma_\mathrm{max} = \frac{M_\mathrm{max} h / 2}{I} = \frac{6 F L}{b h^2}
$$

Tip displacement:

$$
\delta_\mathrm{tip} = \frac{F L^3}{3 E I} = \frac{4 F L^3}{E b h^3}
$$

Rectangular beam mass:

$$
m = L b h \rho
$$

with `rho` converted from `kg/m3` to `g/mm3` inside the reference calculation.

## Reference Candidate

Reference parameters:

- force: `150 N`;
- effective length: `100 mm`;
- width: `60 mm`;
- thickness: `12 mm`;
- Young's modulus: `3250 MPa`;
- density: `1240 kg/m3`;
- rib height: ignored by the beam approximation;
- fillet radius: ignored by the beam approximation.

Expected rectangular-beam reference output:

| Quantity | Value |
|---|---:|
| maximum bending stress | `10.4167 MPa` |
| tip displacement | `1.7806 mm` |
| rectangular arm mass | `89.28 g` |

The reference candidate passes the analytical stress and displacement checks against the frozen limits of `25 MPa` and `2.0 mm`. This does not prove that the full bracket passes FEA; it only establishes a rough scale check for the later solver pipeline.

## Code Reference

The pure-Python reference function is `open_engineering_intelligence.sanity.beam.rectangular_cantilever_reference`. Tests live in `tests/test_sanity_beam.py`.
