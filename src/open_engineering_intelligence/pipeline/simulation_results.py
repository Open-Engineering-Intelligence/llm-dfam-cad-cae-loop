"""Normalize validated structural evidence into public simulation records."""

from __future__ import annotations

from open_engineering_intelligence.pipeline.closed_loop_contracts import CandidateEvaluation
from open_engineering_intelligence.schemas import SimulationResult


def normalize_simulation_result(evaluation: CandidateEvaluation) -> SimulationResult:
    """Create a SimulationResult from a validated candidate evaluation."""

    if evaluation.evaluation_status == "completed":
        return SimulationResult(
            succeeded=True,
            max_von_mises_mpa=evaluation.metrics.max_von_mises_mpa,
            max_displacement_mm=evaluation.metrics.max_displacement_mm,
            mass_g=evaluation.metrics.mass_g,
            failure_reason=None,
        )

    assert evaluation.failure is not None
    failure_reason = evaluation.failure.message.strip()
    if not failure_reason:
        failure_reason = ": ".join(
            part
            for part in (
                evaluation.failure.code.strip(),
                evaluation.failure.stage.strip(),
            )
            if part
        )
    if not failure_reason:
        failure_reason = (
            f"code={evaluation.failure.code!r}; "
            f"stage={evaluation.failure.stage!r}; "
            f"message={evaluation.failure.message!r}"
        )
    return SimulationResult(
        succeeded=False,
        max_von_mises_mpa=None,
        max_displacement_mm=None,
        mass_g=None,
        failure_reason=failure_reason,
    )


__all__ = ["normalize_simulation_result"]
