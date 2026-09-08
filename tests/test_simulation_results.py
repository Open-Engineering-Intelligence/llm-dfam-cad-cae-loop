import builtins
import importlib.util
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from open_engineering_intelligence.pipeline.closed_loop_contracts import (
    CandidateEvaluation,
    ConstraintChecks,
    Failure,
    LoopParameters,
    Metrics,
    failed_evaluation,
    make_completed_evaluation,
)
from open_engineering_intelligence.schemas import SimulationResult


def _parameters() -> LoopParameters:
    return LoopParameters(
        thickness_mm=8.0,
        width_mm=50.0,
        rib_height_mm=18.0,
        fillet_radius_mm=2.0,
    )


@pytest.fixture(scope="module")
def fallback_simulation_result_type() -> type:
    """Load the real schema module with Pydantic intentionally unavailable."""

    schema_path = (
        Path(__file__).parents[1]
        / "src"
        / "open_engineering_intelligence"
        / "schemas.py"
    )
    real_import = builtins.__import__

    def import_without_pydantic(name: str, *args: object, **kwargs: object) -> object:
        if name == "pydantic" or name.startswith("pydantic."):
            raise ImportError("Pydantic intentionally unavailable for fallback test")
        return real_import(name, *args, **kwargs)

    spec = importlib.util.spec_from_file_location("_fallback_simulation_schemas", schema_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load schema module from {schema_path}")
    module = importlib.util.module_from_spec(spec)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(builtins, "__import__", import_without_pydantic)
        spec.loader.exec_module(module)
    return module.SimulationResult


@pytest.fixture(params=("pydantic", "fallback"))
def simulation_result_type(
    request: pytest.FixtureRequest,
    fallback_simulation_result_type: type,
) -> type:
    if request.param == "pydantic":
        return SimulationResult
    return fallback_simulation_result_type


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (
            {
                "succeeded": True,
                "max_von_mises_mpa": 20.0,
                "max_displacement_mm": 1.0,
                "mass_g": 12.4,
            },
            {
                "succeeded": True,
                "max_von_mises_mpa": 20.0,
                "max_displacement_mm": 1.0,
                "mass_g": 12.4,
                "failure_reason": None,
            },
        ),
        (
            {"succeeded": False, "failure_reason": "solver failed"},
            {
                "succeeded": False,
                "max_von_mises_mpa": None,
                "max_displacement_mm": None,
                "mass_g": None,
                "failure_reason": "solver failed",
            },
        ),
    ],
    ids=("success", "failure"),
)
def test_implementations_accept_same_valid_results(
    simulation_result_type: type,
    data: dict[str, object],
    expected: dict[str, object],
) -> None:
    assert simulation_result_type(**data).model_dump() == expected


def test_fallback_supports_omitted_optional_defaults(
    fallback_simulation_result_type: type,
) -> None:
    result = fallback_simulation_result_type(
        succeeded=False,
        failure_reason="solver failed",
    )

    assert result.model_dump() == {
        "succeeded": False,
        "max_von_mises_mpa": None,
        "max_displacement_mm": None,
        "mass_g": None,
        "failure_reason": "solver failed",
    }


@pytest.mark.parametrize("succeeded", [0, 1, 2, "false", "true", [], object()])
@pytest.mark.parametrize(
    "state",
    [
        {
            "max_von_mises_mpa": 20.0,
            "max_displacement_mm": 1.0,
            "mass_g": 12.4,
            "failure_reason": None,
        },
        {
            "max_von_mises_mpa": None,
            "max_displacement_mm": None,
            "mass_g": None,
            "failure_reason": "solver failed",
        },
    ],
    ids=("success-shaped", "failure-shaped"),
)
def test_implementations_reject_non_bool_succeeded(
    simulation_result_type: type,
    succeeded: object,
    state: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        simulation_result_type(succeeded=succeeded, **state)


@pytest.mark.parametrize(
    "data",
    [
        {"succeeded": True},
        {
            "succeeded": True,
            "max_von_mises_mpa": 20.0,
            "max_displacement_mm": 1.0,
            "mass_g": 12.4,
            "failure_reason": "unexpected",
        },
        {
            "succeeded": False,
            "max_von_mises_mpa": 20.0,
            "failure_reason": "solver failed",
        },
        {"succeeded": False, "failure_reason": "   "},
    ],
    ids=(
        "success-missing-metrics",
        "success-with-failure-reason",
        "failure-with-metric",
        "failure-with-blank-reason",
    ),
)
def test_implementations_reject_incoherent_states(
    simulation_result_type: type,
    data: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        simulation_result_type(**data)


@pytest.mark.parametrize(
    "missing_field",
    ["max_von_mises_mpa", "max_displacement_mm", "mass_g"],
)
def test_succeeded_result_requires_complete_metrics(missing_field: str) -> None:
    data = {
        "succeeded": True,
        "max_von_mises_mpa": 20.0,
        "max_displacement_mm": 1.0,
        "mass_g": 12.4,
    }
    data.pop(missing_field)

    with pytest.raises(ValidationError, match="requires all finite metrics"):
        SimulationResult.model_validate(data)


@pytest.mark.parametrize("failure_reason", [None, "", "   "])
def test_failed_result_requires_failure_reason(failure_reason: str | None) -> None:
    with pytest.raises(ValidationError, match="requires a failure_reason"):
        SimulationResult(succeeded=False, failure_reason=failure_reason)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize(
    "field",
    ["max_von_mises_mpa", "max_displacement_mm", "mass_g"],
)
def test_result_rejects_nonfinite_metrics(
    simulation_result_type: type,
    field: str,
    value: float,
) -> None:
    data = {
        "succeeded": True,
        "max_von_mises_mpa": 20.0,
        "max_displacement_mm": 1.0,
        "mass_g": 12.4,
    }
    data[field] = value

    with pytest.raises((TypeError, ValueError)):
        simulation_result_type(**data)


def test_succeeded_result_rejects_failure_reason() -> None:
    with pytest.raises(ValidationError, match="must not contain a failure_reason"):
        SimulationResult(
            succeeded=True,
            max_von_mises_mpa=20.0,
            max_displacement_mm=1.0,
            mass_g=12.4,
            failure_reason="unexpected",
        )


@pytest.mark.parametrize("mass_g", [0.0, -1.0, "not-a-number"])
def test_succeeded_result_requires_valid_positive_mass(
    simulation_result_type: type,
    mass_g: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        simulation_result_type(
            succeeded=True,
            max_von_mises_mpa=20.0,
            max_displacement_mm=1.0,
            mass_g=mass_g,
        )


@pytest.mark.parametrize("field", ["max_von_mises_mpa", "max_displacement_mm"])
def test_succeeded_result_accepts_zero_stress_or_displacement(
    simulation_result_type: type,
    field: str,
) -> None:
    data = {
        "succeeded": True,
        "max_von_mises_mpa": 20.0,
        "max_displacement_mm": 1.0,
        "mass_g": 12.4,
    }
    data[field] = 0.0

    result = simulation_result_type(**data)

    assert getattr(result, field) == 0.0


def test_failed_result_rejects_available_metrics() -> None:
    with pytest.raises(ValidationError, match="must have null metrics"):
        SimulationResult(
            succeeded=False,
            max_von_mises_mpa=20.0,
            failure_reason="solver failed",
        )


def test_normalizes_successful_evaluation() -> None:
    from open_engineering_intelligence.pipeline.simulation_results import (
        normalize_simulation_result,
    )

    evaluation = make_completed_evaluation(
        0,
        _parameters(),
        volume_mm3=10_000.0,
        max_von_mises_mpa=20.0,
        max_displacement_mm=1.0,
    )

    assert normalize_simulation_result(evaluation) == SimulationResult(
        succeeded=True,
        max_von_mises_mpa=20.0,
        max_displacement_mm=1.0,
        mass_g=12.4,
        failure_reason=None,
    )


def test_normalizes_failed_evaluation_with_unavailable_metrics() -> None:
    from open_engineering_intelligence.pipeline.simulation_results import (
        normalize_simulation_result,
    )

    failed = failed_evaluation(
        0,
        _parameters(),
        stage="solver",
        code="solver_failed",
        message="  linear solve failed  ",
    )
    data = failed.model_dump()
    data["metrics"].update(volume_mm3=10_000.0, mass_g=12.4)
    evaluation = CandidateEvaluation.model_validate(data)

    assert normalize_simulation_result(evaluation) == SimulationResult(
        succeeded=False,
        max_von_mises_mpa=None,
        max_displacement_mm=None,
        mass_g=None,
        failure_reason="linear solve failed",
    )


def test_whitespace_failure_message_uses_code_and_stage_without_mutation() -> None:
    from open_engineering_intelligence.pipeline.simulation_results import (
        normalize_simulation_result,
    )

    evaluation = failed_evaluation(
        0,
        _parameters(),
        stage="solver",
        code="solver_failed",
        message="   ",
    )
    before = evaluation.model_dump()

    result = normalize_simulation_result(evaluation)

    assert result.failure_reason == "solver_failed: solver"
    assert evaluation.model_dump() == before


def test_all_whitespace_failure_fields_use_escaped_raw_evidence() -> None:
    from open_engineering_intelligence.pipeline.simulation_results import (
        normalize_simulation_result,
    )

    evaluation = CandidateEvaluation(
        iteration=0,
        parameters=_parameters(),
        evaluation_status="failed",
        metrics=Metrics(
            max_von_mises_mpa=None,
            max_displacement_mm=None,
            volume_mm3=None,
            mass_g=None,
        ),
        constraint_checks=ConstraintChecks(
            stress_passed=None,
            displacement_passed=None,
        ),
        structural_feasible=None,
        failure=Failure(stage="   ", code="   ", message="   "),
    )
    before = evaluation.model_dump()

    result = normalize_simulation_result(evaluation)

    assert result.succeeded is False
    assert result.max_von_mises_mpa is None
    assert result.max_displacement_mm is None
    assert result.mass_g is None
    assert result.failure_reason == "code='   '; stage='   '; message='   '"
    assert result.failure_reason.strip()
    assert normalize_simulation_result(evaluation).failure_reason == result.failure_reason
    assert evaluation.model_dump() == before


def test_normalization_uses_canonical_cad_volume_mass_derivation() -> None:
    from open_engineering_intelligence.pipeline.simulation_results import (
        normalize_simulation_result,
    )

    evaluation = make_completed_evaluation(
        0,
        _parameters(),
        volume_mm3=12_345.0,
        max_von_mises_mpa=20.0,
        max_displacement_mm=1.0,
    )

    assert normalize_simulation_result(evaluation).mass_g == pytest.approx(15.3078)


def test_normalization_preserves_candidate_evaluation_behavior() -> None:
    from open_engineering_intelligence.pipeline.simulation_results import (
        normalize_simulation_result,
    )

    evaluation = make_completed_evaluation(
        0,
        _parameters(),
        volume_mm3=10_000.0,
        max_von_mises_mpa=20.0,
        max_displacement_mm=1.0,
    )
    before = evaluation.model_dump()

    normalize_simulation_result(evaluation)

    assert evaluation.model_dump() == before
    assert CandidateEvaluation.model_validate(before) == evaluation
