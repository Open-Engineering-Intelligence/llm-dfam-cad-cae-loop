import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from open_engineering_intelligence.pipeline.closed_loop_contracts import (
    ArtifactRef,
    CandidateEvaluation,
    ClosedLoopResult,
    ConstraintChecks,
    ControllerDecision,
    ExperimentConfig,
    Failure,
    IterationManifest,
    LoopParameters,
    Metrics,
    failed_evaluation,
    load_experiment_config,
    make_completed_evaluation,
    schema_document,
    validate_parameters,
)


def _parameters(thickness_mm: float = 8.0) -> LoopParameters:
    return LoopParameters(
        thickness_mm=thickness_mm,
        width_mm=50.0,
        rib_height_mm=18.0,
        fillet_radius_mm=2.0,
    )


def _ref(path: str) -> ArtifactRef:
    return ArtifactRef(path=path, sha256="a" * 64)


def _completed(iteration: int = 0, thickness_mm: float = 8.0) -> CandidateEvaluation:
    return make_completed_evaluation(
        iteration,
        _parameters(thickness_mm),
        volume_mm3=50_000.0,
        max_von_mises_mpa=25.0,
        max_displacement_mm=2.0,
    )


def test_default_config_loads_frozen_thickness_experiment(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "closed_loop_thickness_v1.yaml").write_text(
        "initial_parameters:\n"
        "  thickness_mm: 8.0\n"
        "  width_mm: 50.0\n"
        "  rib_height_mm: 18.0\n"
        "  fillet_radius_mm: 2.0\n"
        "evaluation_budget: 30\n",
        encoding="utf-8",
    )

    config = load_experiment_config(tmp_path)

    assert config.repo_root == tmp_path.resolve()
    assert config.initial_parameters == _parameters()
    assert config.min_thickness_mm == 4.0
    assert config.max_thickness_mm == 14.0
    assert config.step_mm == 1.0
    assert config.stress_limit_mpa == 25.0
    assert config.displacement_limit_mm == 2.0
    assert config.density_g_mm3 == 0.00124
    assert config.evaluation_budget == 30
    assert config.timeout_seconds == 300
    with pytest.raises(ValidationError):
        config.model_copy(update={"step_mm": 0.5}).model_validate(
            {**config.model_dump(), "step_mm": 0.5}
        )


def test_config_rejects_invalid_bounds_and_initial_fixed_values(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ExperimentConfig(repo_root=tmp_path, min_thickness_mm=8.0, max_thickness_mm=4.0)
    with pytest.raises(ValidationError):
        ExperimentConfig(repo_root=tmp_path, initial_parameters=_parameters(15.0))
    with pytest.raises(ValidationError):
        ExperimentConfig(repo_root=tmp_path, evaluation_budget=0)
    with pytest.raises(ValidationError):
        ExperimentConfig(repo_root=tmp_path, min_thickness_mm=5.0)
    with pytest.raises(ValidationError):
        ExperimentConfig(
            repo_root=tmp_path,
            initial_parameters=LoopParameters(
                thickness_mm=8.0,
                width_mm=51.0,
                rib_height_mm=18.0,
                fillet_radius_mm=2.0,
            ),
        )


def test_loader_rejects_retuning_the_frozen_production_budget(tmp_path: Path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "closed_loop_thickness_v1.yaml").write_text(
        "evaluation_budget: 5\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="evaluation_budget"):
        load_experiment_config(tmp_path)


def test_parameter_validation_enforces_bounds_fixed_values_and_integer_grid(tmp_path: Path) -> None:
    config = ExperimentConfig(repo_root=tmp_path)

    assert validate_parameters(_parameters(7.0), config) == _parameters(7.0)
    for invalid in (
        _parameters(3.0),
        _parameters(14.0).model_copy(update={"thickness_mm": 7.0000000001}),
        _parameters(7.0).model_copy(update={"width_mm": 51.0}),
    ):
        with pytest.raises(ValueError):
            validate_parameters(invalid, config)


def test_completed_evaluation_derives_mass_and_inclusive_constraint_checks() -> None:
    evaluation = _completed()

    assert evaluation.metrics.mass_g == pytest.approx(62.0)
    assert evaluation.constraint_checks == ConstraintChecks(
        stress_passed=True,
        displacement_passed=True,
    )
    assert evaluation.structural_feasible is True
    assert evaluation.failure is None


def test_completed_evaluation_rejects_incomplete_nonfinite_or_incoherent_metrics() -> None:
    base = _completed().model_dump()

    for field, value in (
        ("max_von_mises_mpa", None),
        ("max_displacement_mm", math.inf),
        ("volume_mm3", 0.0),
        ("mass_g", 99.0),
    ):
        invalid = {**base, "metrics": {**base["metrics"], field: value}}
        with pytest.raises(ValidationError):
            CandidateEvaluation.model_validate(invalid)

    invalid_checks = {
        **base,
        "constraint_checks": {"stress_passed": False, "displacement_passed": True},
    }
    with pytest.raises(ValidationError):
        CandidateEvaluation.model_validate(invalid_checks)


def test_failed_evaluation_requires_failure_and_allows_available_mass() -> None:
    evaluation = failed_evaluation(2, _parameters(6.0), "solver", "timeout", "timed out")
    payload = evaluation.model_dump()
    payload["metrics"] = {
        "max_von_mises_mpa": None,
        "max_displacement_mm": None,
        "volume_mm3": 10_000.0,
        "mass_g": 12.4,
    }

    with_mass = CandidateEvaluation.model_validate(payload)

    assert with_mass.evaluation_status == "failed"
    assert with_mass.structural_feasible is None
    assert with_mass.metrics.mass_g == 12.4
    assert with_mass.failure == Failure(stage="solver", code="timeout", message="timed out")
    del payload["failure"]
    with pytest.raises(ValidationError):
        CandidateEvaluation.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        "/absolute/result.json",
        "C:/run/result.json",
        "../result.json",
        "a/../result.json",
        "a\\b.json",
    ],
)
def test_artifact_reference_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        ArtifactRef(path=path, sha256="a" * 64)


def test_artifact_reference_requires_canonical_digest_and_json_dump_is_portable() -> None:
    ref = _ref("iterations/000/evaluation.json")

    assert ref.model_dump(mode="json") == {
        "path": "iterations/000/evaluation.json",
        "sha256": "a" * 64,
    }
    with pytest.raises(ValidationError):
        ArtifactRef(path="result.json", sha256="A" * 64)
    with pytest.raises(ValidationError):
        ArtifactRef(path="result.json", sha256="a" * 63)


def test_models_forbid_extra_fields_and_require_nullable_fields() -> None:
    with pytest.raises(ValidationError):
        Metrics(
            max_von_mises_mpa=None,
            max_displacement_mm=None,
            volume_mm3=None,
            mass_g=None,
            undocumented=1,
        )
    with pytest.raises(ValidationError):
        Metrics(
            max_von_mises_mpa=None,
            max_displacement_mm=None,
            volume_mm3=None,
        )


def test_controller_decision_enforces_stop_and_step_shapes() -> None:
    common = {
        "schema_version": "1.0",
        "controller": "thickness_descent_v1",
        "iteration": 0,
        "input_parameters": _parameters(),
        "current_evaluation": "feasible",
        "violated_constraints": [],
        "best_feasible_iteration": 0,
    }

    step = ControllerDecision(
        **common,
        action="decrease_thickness",
        reason="feasible_try_thinner",
        next_parameters=_parameters(7.0),
    )
    assert step.next_parameters == _parameters(7.0)

    with pytest.raises(ValidationError):
        ControllerDecision(
            **common,
            action="stop",
            reason="lower_bound_reached",
            next_parameters=_parameters(7.0),
        )
    with pytest.raises(ValidationError):
        ControllerDecision(
            **common,
            action="decrease_thickness",
            reason="feasible_try_thinner",
            next_parameters=None,
        )


def test_iteration_manifest_enforces_status_and_chain_coherence() -> None:
    completed = _completed()
    manifest = IterationManifest(
        schema_version="1.0",
        iteration=0,
        previous_iteration_manifest=None,
        parameters=_ref("iterations/000/parameters.json"),
        effective_analysis=_ref("iterations/000/effective_analysis.json"),
        evaluation_status="completed",
        metrics=completed.metrics,
        constraint_checks=completed.constraint_checks,
        structural_feasible=True,
        dfam_status="not_evaluated",
        full_benchmark_feasible=None,
        cad_manifest=_ref("iterations/000/cad_manifest.json"),
        mesh_manifest=_ref("iterations/000/mesh_manifest.json"),
        physics_result=_ref("iterations/000/physics_result.json"),
        decision=_ref("iterations/000/decision.json"),
        artifacts=[_ref("iterations/000/bracket.step")],
        failure=None,
        terminal=False,
    )

    assert manifest.evaluation_status == "completed"
    payload = manifest.model_dump()
    payload["failure"] = Failure(stage="solver", code="failed", message="bad")
    with pytest.raises(ValidationError):
        IterationManifest.model_validate(payload)
    payload = manifest.model_dump()
    payload["previous_iteration_manifest"] = _ref("iterations/previous.json")
    with pytest.raises(ValidationError):
        IterationManifest.model_validate(payload)
    payload = manifest.model_dump()
    payload["physics_result"] = None
    with pytest.raises(ValidationError):
        IterationManifest.model_validate(payload)


def test_failed_iteration_manifest_must_be_terminal() -> None:
    failed = failed_evaluation(1, _parameters(7.0), "solver", "timeout", "timed out")

    with pytest.raises(ValidationError):
        IterationManifest(
            schema_version="1.0",
            iteration=1,
            previous_iteration_manifest=_ref("iterations/000/iteration_manifest.json"),
            parameters=_ref("iterations/001/parameters.json"),
            effective_analysis=_ref("iterations/001/effective_analysis.json"),
            evaluation_status="failed",
            metrics=failed.metrics,
            constraint_checks=failed.constraint_checks,
            structural_feasible=None,
            dfam_status="not_evaluated",
            full_benchmark_feasible=None,
            cad_manifest=None,
            mesh_manifest=None,
            physics_result=None,
            decision=_ref("iterations/001/decision.json"),
            artifacts=[],
            failure=failed.failure,
            terminal=False,
        )


def test_closed_loop_result_enforces_accepted_result_coherence() -> None:
    result = ClosedLoopResult(
        schema_version="1.0",
        experiment="bracket_v1_structural_thinning_v1",
        controller="thickness_descent_v1",
        status="accepted",
        termination_reason="lower_bound_reached",
        experiment_config=_ref("experiment_config.json"),
        environment_manifest=_ref("environment_manifest.json"),
        evaluation_count=5,
        iteration_manifests=[_ref(f"iterations/{i:03d}/manifest.json") for i in range(5)],
        best_feasible_iteration=4,
        accepted_iteration=4,
        accepted_parameters=_parameters(4.0),
        initial_mass_g=100.0,
        accepted_mass_g=75.0,
        mass_reduction_fraction=0.25,
        dfam_status="not_evaluated",
        full_benchmark_feasible=None,
    )

    assert result.model_dump(mode="json")["accepted_parameters"]["thickness_mm"] == 4.0
    inconsistent = result.model_dump()
    inconsistent["mass_reduction_fraction"] = 0.5
    with pytest.raises(ValidationError):
        ClosedLoopResult.model_validate(inconsistent)
    inconsistent = result.model_dump()
    inconsistent["iteration_manifests"] = inconsistent["iteration_manifests"][:-1]
    with pytest.raises(ValidationError):
        ClosedLoopResult.model_validate(inconsistent)


def test_terminal_result_statuses_reject_accepted_fields_when_not_accepted() -> None:
    base = {
        "schema_version": "1.0",
        "experiment": "bracket_v1_structural_thinning_v1",
        "controller": "thickness_descent_v1",
        "termination_reason": "initial_infeasible",
        "experiment_config": _ref("experiment_config.json"),
        "environment_manifest": _ref("environment_manifest.json"),
        "evaluation_count": 1,
        "iteration_manifests": [_ref("iterations/000/manifest.json")],
        "best_feasible_iteration": None,
        "accepted_iteration": None,
        "accepted_parameters": None,
        "initial_mass_g": 100.0,
        "accepted_mass_g": None,
        "mass_reduction_fraction": None,
        "dfam_status": "not_evaluated",
        "full_benchmark_feasible": None,
    }
    no_design = ClosedLoopResult(status="no_feasible_design", **base)
    assert no_design.status == "no_feasible_design"

    with pytest.raises(ValidationError):
        ClosedLoopResult(
            status="no_feasible_design",
            **{**base, "accepted_iteration": 0},
        )
    with pytest.raises(ValidationError):
        ClosedLoopResult(
            status="no_feasible_design",
            **{
                **base,
                "evaluation_count": 2,
                "iteration_manifests": [
                    _ref("iterations/000/manifest.json"),
                    _ref("iterations/001/manifest.json"),
                ],
            },
        )


def test_accepted_parameters_match_the_accepted_iteration() -> None:
    payload = {
        "schema_version": "1.0",
        "experiment": "bracket_v1_structural_thinning_v1",
        "controller": "thickness_descent_v1",
        "status": "accepted",
        "termination_reason": "structural_boundary_reached",
        "experiment_config": _ref("experiment_config.json"),
        "environment_manifest": _ref("environment_manifest.json"),
        "evaluation_count": 3,
        "iteration_manifests": [
            _ref(f"iterations/{i:03d}/manifest.json") for i in range(3)
        ],
        "best_feasible_iteration": 1,
        "accepted_iteration": 1,
        "accepted_parameters": _parameters(8.0),
        "initial_mass_g": 100.0,
        "accepted_mass_g": 90.0,
        "mass_reduction_fraction": 0.1,
        "dfam_status": "not_evaluated",
        "full_benchmark_feasible": None,
    }

    with pytest.raises(ValidationError):
        ClosedLoopResult.model_validate(payload)


def test_schema_document_is_a_union_of_the_three_persisted_artifacts() -> None:
    schema = schema_document()

    assert len(schema["anyOf"]) == 3
    definitions = schema["$defs"]
    assert {"ControllerDecision", "IterationManifest", "ClosedLoopResult"} <= definitions.keys()
    json.dumps(schema, allow_nan=False)
