import math

import pytest

from open_engineering_intelligence.sanity.beam import rectangular_cantilever_reference


def test_rectangular_cantilever_reference_matches_hand_checked_values() -> None:
    result = rectangular_cantilever_reference(
        force_n=150.0,
        length_mm=100.0,
        width_mm=60.0,
        thickness_mm=12.0,
        youngs_modulus_mpa=3250.0,
        density_kg_m3=1240.0,
    )

    assert result.max_bending_stress_mpa == pytest.approx(10.4166666667)
    assert result.tip_displacement_mm == pytest.approx(1.7806267806)
    assert result.beam_mass_g == pytest.approx(89.28)
    assert result.max_bending_stress_mpa < 25.0
    assert result.tip_displacement_mm < 2.0


def test_rectangular_cantilever_reference_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValueError, match="positive"):
        rectangular_cantilever_reference(
            force_n=150.0,
            length_mm=100.0,
            width_mm=0.0,
            thickness_mm=12.0,
            youngs_modulus_mpa=3250.0,
            density_kg_m3=1240.0,
        )


def test_rectangular_cantilever_reference_uses_downward_load_magnitude() -> None:
    positive = rectangular_cantilever_reference(
        force_n=150.0,
        length_mm=100.0,
        width_mm=60.0,
        thickness_mm=12.0,
        youngs_modulus_mpa=3250.0,
        density_kg_m3=1240.0,
    )
    negative = rectangular_cantilever_reference(
        force_n=-150.0,
        length_mm=100.0,
        width_mm=60.0,
        thickness_mm=12.0,
        youngs_modulus_mpa=3250.0,
        density_kg_m3=1240.0,
    )

    assert math.isclose(positive.max_bending_stress_mpa, negative.max_bending_stress_mpa)
    assert math.isclose(positive.tip_displacement_mm, negative.tip_displacement_mm)
