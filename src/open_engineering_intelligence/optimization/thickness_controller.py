"""Pure deterministic controller for the bounded structural-thinning experiment."""

from __future__ import annotations

from collections.abc import Sequence

from open_engineering_intelligence.pipeline.closed_loop_contracts import (
    CONTROLLER_NAME,
    SCHEMA_VERSION,
    CandidateEvaluation,
    ControllerDecision,
    ExperimentConfig,
    LoopParameters,
    validate_parameters,
)


def _best_feasible_iteration(history: Sequence[CandidateEvaluation]) -> int | None:
    feasible = [
        evaluation
        for evaluation in history
        if evaluation.evaluation_status == "completed" and evaluation.structural_feasible is True
    ]
    if not feasible:
        return None
    best = min(
        feasible,
        key=lambda evaluation: (
            evaluation.metrics.mass_g,
            evaluation.parameters.thickness_mm,
            evaluation.iteration,
        ),
    )
    return best.iteration


def _error_decision(
    config: ExperimentConfig,
    history: Sequence[CandidateEvaluation],
    reason: str,
    valid_history_length: int,
) -> ControllerDecision:
    current = history[-1] if history else None
    return ControllerDecision(
        schema_version=SCHEMA_VERSION,
        controller=CONTROLLER_NAME,
        iteration=current.iteration if current is not None else 0,
        input_parameters=(
            current.parameters if current is not None else config.initial_parameters
        ),
        current_evaluation="error",
        violated_constraints=[],
        action="stop",
        reason=reason,
        next_parameters=None,
        best_feasible_iteration=_best_feasible_iteration(history[:valid_history_length]),
    )


def _fixed_parameters_match(left: LoopParameters, right: LoopParameters) -> bool:
    return all(
        getattr(left, field) == getattr(right, field)
        for field in ("width_mm", "rib_height_mm", "fillet_radius_mm")
    )


def _trajectory_error(
    config: ExperimentConfig,
    history: Sequence[CandidateEvaluation],
) -> tuple[str, int] | None:
    if not history:
        return "invalid_proposal", 0
    if not _fixed_parameters_match(history[0].parameters, config.initial_parameters):
        return "provenance_mismatch", 0
    if history[0].parameters.thickness_mm != config.initial_parameters.thickness_mm:
        return "provenance_mismatch", 0

    for position, evaluation in enumerate(history):
        if evaluation.iteration != position:
            return "invalid_proposal", position
        if not _fixed_parameters_match(evaluation.parameters, config.initial_parameters):
            return "provenance_mismatch", position
        expected_thickness = config.initial_parameters.thickness_mm - position * config.step_mm
        if evaluation.parameters.thickness_mm != expected_thickness:
            return "invalid_proposal", position
        try:
            validate_parameters(evaluation.parameters, config)
        except ValueError:
            return "invalid_proposal", position
        if position < len(history) - 1 and (
            evaluation.evaluation_status == "failed"
            or evaluation.structural_feasible is not True
            or position + 1 >= config.evaluation_budget
            or evaluation.parameters.thickness_mm <= config.min_thickness_mm
        ):
            return "invalid_proposal", position + 1
    return None


def _violated_constraints(evaluation: CandidateEvaluation) -> list[str]:
    violated: list[str] = []
    if evaluation.constraint_checks.stress_passed is False:
        violated.append("max_von_mises_mpa")
    if evaluation.constraint_checks.displacement_passed is False:
        violated.append("max_displacement_mm")
    return violated


def decide(
    config: ExperimentConfig,
    ordered_evaluation_history: Sequence[CandidateEvaluation],
) -> ControllerDecision:
    """Return the next one-millimeter descent step or a deterministic stop record."""

    history = tuple(ordered_evaluation_history)
    trajectory_error = _trajectory_error(config, history)
    if trajectory_error is not None:
        reason, valid_history_length = trajectory_error
        return _error_decision(config, history, reason, valid_history_length)

    current = history[-1]
    best_iteration = _best_feasible_iteration(history)
    common = {
        "schema_version": SCHEMA_VERSION,
        "controller": CONTROLLER_NAME,
        "iteration": current.iteration,
        "input_parameters": current.parameters,
        "best_feasible_iteration": best_iteration,
    }

    if current.evaluation_status == "failed":
        failure_reason = (
            current.failure.code
            if current.failure is not None
            and current.failure.code in {"invalid_proposal", "provenance_mismatch"}
            else "evaluation_failed"
        )
        return ControllerDecision(
            **common,
            current_evaluation="error",
            violated_constraints=[],
            action="stop",
            reason=failure_reason,
            next_parameters=None,
        )

    violated = _violated_constraints(current)
    if current.structural_feasible is False:
        return ControllerDecision(
            **common,
            current_evaluation="infeasible",
            violated_constraints=violated,
            action="stop",
            reason=(
                "initial_infeasible"
                if current.iteration == 0
                else "structural_boundary_reached"
            ),
            next_parameters=None,
        )

    if current.parameters.thickness_mm <= config.min_thickness_mm:
        return ControllerDecision(
            **common,
            current_evaluation="feasible",
            violated_constraints=[],
            action="stop",
            reason="lower_bound_reached",
            next_parameters=None,
        )

    if len(history) >= config.evaluation_budget:
        return ControllerDecision(
            **common,
            current_evaluation="feasible",
            violated_constraints=[],
            action="stop",
            reason="budget_exhausted",
            next_parameters=None,
        )

    next_parameters = current.parameters.model_copy(
        update={"thickness_mm": current.parameters.thickness_mm - config.step_mm}
    )
    if next_parameters.thickness_mm < config.min_thickness_mm:
        return _error_decision(config, history, "invalid_proposal", len(history))
    return ControllerDecision(
        **common,
        current_evaluation="feasible",
        violated_constraints=[],
        action="decrease_thickness",
        reason="feasible_try_thinner",
        next_parameters=next_parameters,
    )


__all__ = ["decide"]
