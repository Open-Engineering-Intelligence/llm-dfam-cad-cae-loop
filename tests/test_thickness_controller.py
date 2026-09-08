from pathlib import Path

from open_engineering_intelligence.optimization.thickness_controller import decide
from open_engineering_intelligence.pipeline.closed_loop_contracts import (
    CandidateEvaluation,
    ExperimentConfig,
    LoopParameters,
    failed_evaluation,
    make_completed_evaluation,
)


def _config(tmp_path: Path, *, budget: int = 30) -> ExperimentConfig:
    return ExperimentConfig(repo_root=tmp_path, evaluation_budget=budget)


def _parameters(thickness_mm: float, *, width_mm: float = 50.0) -> LoopParameters:
    return LoopParameters(
        thickness_mm=thickness_mm,
        width_mm=width_mm,
        rib_height_mm=18.0,
        fillet_radius_mm=2.0,
    )


def _evaluation(
    iteration: int,
    thickness_mm: float,
    *,
    stress: float = 20.0,
    displacement: float = 1.0,
    volume: float | None = None,
    width_mm: float = 50.0,
) -> CandidateEvaluation:
    return make_completed_evaluation(
        iteration,
        _parameters(thickness_mm, width_mm=width_mm),
        volume_mm3=volume if volume is not None else thickness_mm * 1_000.0,
        max_von_mises_mpa=stress,
        max_displacement_mm=displacement,
    )


def test_feasible_candidate_descends_exactly_one_millimeter(tmp_path: Path) -> None:
    decision = decide(_config(tmp_path), [_evaluation(0, 8.0)])

    assert decision.model_dump() == {
        "schema_version": "1.0",
        "controller": "thickness_descent_v1",
        "iteration": 0,
        "input_parameters": _parameters(8.0).model_dump(),
        "current_evaluation": "feasible",
        "violated_constraints": [],
        "action": "decrease_thickness",
        "reason": "feasible_try_thinner",
        "next_parameters": _parameters(7.0).model_dump(),
        "best_feasible_iteration": 0,
    }


def test_lower_bound_is_accepted_without_out_of_bounds_proposal(tmp_path: Path) -> None:
    history = [_evaluation(i, 8.0 - i) for i in range(5)]

    decision = decide(_config(tmp_path), history)

    assert decision.action == "stop"
    assert decision.reason == "lower_bound_reached"
    assert decision.next_parameters is None
    assert decision.best_feasible_iteration == 4


def test_first_structural_failure_stops_at_prior_best(tmp_path: Path) -> None:
    history = [
        _evaluation(0, 8.0, volume=8_000.0),
        _evaluation(1, 7.0, volume=7_000.0),
        _evaluation(2, 6.0, stress=25.1, displacement=2.1, volume=6_000.0),
    ]

    decision = decide(_config(tmp_path), history)

    assert decision.current_evaluation == "infeasible"
    assert decision.violated_constraints == [
        "max_von_mises_mpa",
        "max_displacement_mm",
    ]
    assert decision.action == "stop"
    assert decision.reason == "structural_boundary_reached"
    assert decision.best_feasible_iteration == 1


def test_initial_structural_failure_reports_no_feasible_design(tmp_path: Path) -> None:
    decision = decide(_config(tmp_path), [_evaluation(0, 8.0, stress=26.0)])

    assert decision.current_evaluation == "infeasible"
    assert decision.violated_constraints == ["max_von_mises_mpa"]
    assert decision.reason == "initial_infeasible"
    assert decision.best_feasible_iteration is None


def test_backend_failure_is_error_even_after_prior_feasible_candidate(tmp_path: Path) -> None:
    history = [
        _evaluation(0, 8.0),
        failed_evaluation(1, _parameters(7.0), "solver", "timeout", "timed out"),
    ]

    decision = decide(_config(tmp_path), history)

    assert decision.current_evaluation == "error"
    assert decision.action == "stop"
    assert decision.reason == "evaluation_failed"
    assert decision.best_feasible_iteration == 0


def test_budget_exhaustion_stops_a_feasible_search(tmp_path: Path) -> None:
    decision = decide(_config(tmp_path, budget=2), [_evaluation(0, 8.0), _evaluation(1, 7.0)])

    assert decision.current_evaluation == "feasible"
    assert decision.reason == "budget_exhausted"
    assert decision.action == "stop"
    assert decision.next_parameters is None


def test_lower_bound_takes_precedence_when_budget_is_also_exhausted(tmp_path: Path) -> None:
    history = [_evaluation(i, 8.0 - i) for i in range(5)]

    decision = decide(_config(tmp_path, budget=5), history)

    assert decision.reason == "lower_bound_reached"


def test_best_candidate_is_selected_by_mass_then_thickness_then_iteration(tmp_path: Path) -> None:
    history = [
        _evaluation(0, 8.0, volume=6_000.0),
        _evaluation(1, 7.0, volume=6_000.0),
        _evaluation(2, 6.0, stress=26.0, volume=5_000.0),
    ]

    decision = decide(_config(tmp_path), history)

    assert decision.best_feasible_iteration == 1


def test_duplicate_or_skipped_thickness_is_an_invalid_proposal(tmp_path: Path) -> None:
    duplicate = [_evaluation(0, 8.0), _evaluation(1, 8.0)]
    skipped = [_evaluation(0, 8.0), _evaluation(1, 6.0)]

    for history in (duplicate, skipped):
        decision = decide(_config(tmp_path), history)
        assert decision.current_evaluation == "error"
        assert decision.reason == "invalid_proposal"
        assert decision.action == "stop"


def test_changed_fixed_parameter_is_a_provenance_mismatch(tmp_path: Path) -> None:
    history = [_evaluation(0, 8.0), _evaluation(1, 7.0, width_mm=51.0)]

    decision = decide(_config(tmp_path), history)

    assert decision.current_evaluation == "error"
    assert decision.reason == "provenance_mismatch"
    assert decision.best_feasible_iteration == 0


def test_non_contiguous_iteration_index_is_an_invalid_proposal(tmp_path: Path) -> None:
    history = [_evaluation(0, 8.0), _evaluation(2, 7.0)]

    decision = decide(_config(tmp_path), history)

    assert decision.current_evaluation == "error"
    assert decision.reason == "invalid_proposal"
    assert decision.iteration == 2


def test_almost_on_grid_thickness_is_an_invalid_proposal(tmp_path: Path) -> None:
    history = [_evaluation(0, 8.0), _evaluation(1, 7.0000000001)]

    decision = decide(_config(tmp_path), history)

    assert decision.current_evaluation == "error"
    assert decision.reason == "invalid_proposal"


def test_validation_failure_code_preserves_specific_terminal_reason(tmp_path: Path) -> None:
    for code in ("invalid_proposal", "provenance_mismatch"):
        failed = failed_evaluation(0, _parameters(8.0), "validation", code, "rejected")

        decision = decide(_config(tmp_path), [failed])

        assert decision.current_evaluation == "error"
        assert decision.reason == code


def test_history_after_terminal_evaluation_is_an_invalid_proposal(tmp_path: Path) -> None:
    history = [
        _evaluation(0, 8.0, stress=26.0),
        _evaluation(1, 7.0),
    ]

    decision = decide(_config(tmp_path), history)

    assert decision.current_evaluation == "error"
    assert decision.reason == "invalid_proposal"


def test_empty_history_returns_an_invalid_proposal_record(tmp_path: Path) -> None:
    decision = decide(_config(tmp_path), [])

    assert decision.iteration == 0
    assert decision.input_parameters == _parameters(8.0)
    assert decision.current_evaluation == "error"
    assert decision.reason == "invalid_proposal"
    assert decision.best_feasible_iteration is None
