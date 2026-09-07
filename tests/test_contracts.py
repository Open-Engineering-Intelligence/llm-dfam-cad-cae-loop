from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from open_engineering_intelligence.interfaces import (
    CADBackend,
    CAEBackend,
    DesignAgent,
    GeometryValidator,
    ManufacturabilityValidator,
    Optimizer,
    PhysicsValidator,
)
from open_engineering_intelligence.schemas import (
    DesignParameters,
    EvaluationResult,
    IterationRecord,
    ManufacturabilityResult,
    SimulationResult,
)


def test_design_parameters_are_numeric_and_positive() -> None:
    params = DesignParameters(
        thickness_mm=6.0,
        width_mm=42.0,
        rib_height_mm=18.0,
        fillet_radius_mm=3.0,
        hole_diameter_mm=8.0,
    )

    assert params.model_dump() == {
        "thickness_mm": 6.0,
        "width_mm": 42.0,
        "rib_height_mm": 18.0,
        "fillet_radius_mm": 3.0,
        "hole_diameter_mm": 8.0,
    }


def test_design_parameters_reject_non_positive_core_dimensions() -> None:
    with pytest.raises(ValidationError):
        DesignParameters(
            thickness_mm=0.0,
            width_mm=42.0,
            rib_height_mm=18.0,
            fillet_radius_mm=3.0,
            hole_diameter_mm=8.0,
        )


def test_iteration_record_preserves_structured_feedback() -> None:
    params = DesignParameters(
        thickness_mm=6.0,
        width_mm=42.0,
        rib_height_mm=18.0,
        fillet_radius_mm=3.0,
        hole_diameter_mm=8.0,
    )
    simulation = SimulationResult(
        succeeded=True,
        max_von_mises_mpa=31.2,
        max_displacement_mm=1.4,
        mass_g=74.5,
    )
    manufacturability = ManufacturabilityResult(
        passed=True,
        min_wall_thickness_mm=3.2,
        max_overhang_angle_deg=41.0,
        support_required=False,
        score=0.84,
    )
    evaluation = EvaluationResult(
        feasible=True,
        score=0.76,
        constraint_violations=[],
        feedback={"next_focus": "reduce_mass"},
    )

    record = IterationRecord(
        method="rule_based",
        trial_id="trial-001",
        iteration=3,
        parameters=params,
        simulation=simulation,
        manufacturability=manufacturability,
        evaluation=evaluation,
    )

    assert record.evaluation.feedback["next_focus"] == "reduce_mass"
    assert record.parameters.thickness_mm == 6.0


def test_backend_interfaces_define_minimal_contracts() -> None:
    assert CADBackend.__abstractmethods__ == {"generate"}
    assert CAEBackend.__abstractmethods__ == {"simulate"}
    assert DesignAgent.__abstractmethods__ == {"propose"}
    assert GeometryValidator.__abstractmethods__ == {"validate"}
    assert PhysicsValidator.__abstractmethods__ == {"validate"}
    assert ManufacturabilityValidator.__abstractmethods__ == {"validate"}
    assert Optimizer.__abstractmethods__ == {"suggest"}


def test_default_bracket_config_contains_first_phase_constraints() -> None:
    config_path = Path("configs/bracket_default.yaml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert config["benchmark"]["name"] == "bracket_v1"
    assert "thickness_mm" in config["parameter_bounds"]
    assert config["constraints"]["max_von_mises_mpa"] > 0
    assert config["constraints"]["min_wall_thickness_mm"] > 0
