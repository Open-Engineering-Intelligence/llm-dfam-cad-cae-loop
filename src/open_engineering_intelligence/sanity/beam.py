"""Simple beam equations used only as CAD/FEA sanity checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BeamReferenceResult:
    """Reference result for a rectangular cantilever beam approximation."""

    max_bending_stress_mpa: float
    tip_displacement_mm: float
    beam_mass_g: float


def rectangular_cantilever_reference(
    *,
    force_n: float,
    length_mm: float,
    width_mm: float,
    thickness_mm: float,
    youngs_modulus_mpa: float,
    density_kg_m3: float,
) -> BeamReferenceResult:
    """Return Euler-Bernoulli reference values for a rectangular cantilever.

    The approximation ignores ribs, fillets, the base block, stress concentrations,
    shear deformation, and printed-material anisotropy. It is a unit and setup
    check for later FEA, not the benchmark evaluator.
    """

    for name, value in {
        "length_mm": length_mm,
        "width_mm": width_mm,
        "thickness_mm": thickness_mm,
        "youngs_modulus_mpa": youngs_modulus_mpa,
        "density_kg_m3": density_kg_m3,
    }.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")

    load_n = abs(force_n)
    max_bending_stress_mpa = 6.0 * load_n * length_mm / (width_mm * thickness_mm**2)
    tip_displacement_mm = (
        4.0 * load_n * length_mm**3 / (youngs_modulus_mpa * width_mm * thickness_mm**3)
    )
    beam_mass_g = length_mm * width_mm * thickness_mm * density_kg_m3 * 1e-6

    return BeamReferenceResult(
        max_bending_stress_mpa=max_bending_stress_mpa,
        tip_displacement_mm=tip_displacement_mm,
        beam_mass_g=beam_mass_g,
    )
