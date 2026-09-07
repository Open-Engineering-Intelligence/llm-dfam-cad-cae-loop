"""Pydantic data structures for reproducible closed-loop experiments."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictRecord(BaseModel):
    """Base model that rejects undeclared fields in experiment records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DesignParameters(StrictRecord):
    """Structured parameter proposal accepted by deterministic CAD generators."""

    thickness_mm: float = Field(gt=0)
    width_mm: float = Field(gt=0)
    rib_height_mm: float = Field(ge=0)
    fillet_radius_mm: float = Field(gt=0)
    hole_diameter_mm: float = Field(gt=0)


class SimulationResult(StrictRecord):
    """Physics result parsed from deterministic CAE execution."""

    succeeded: bool
    max_von_mises_mpa: float | None = Field(default=None, ge=0)
    max_displacement_mm: float | None = Field(default=None, ge=0)
    mass_g: float | None = Field(default=None, ge=0)
    failure_reason: str | None = None


class ManufacturabilityResult(StrictRecord):
    """DfAM validation result for FDM-oriented manufacturability checks."""

    passed: bool
    min_wall_thickness_mm: float | None = Field(default=None, ge=0)
    max_overhang_angle_deg: float | None = Field(default=None, ge=0)
    support_required: bool | None = None
    score: float = Field(ge=0, le=1)
    failure_reason: str | None = None


class EvaluationResult(StrictRecord):
    """Unified evaluation result used as feedback for later design proposals."""

    feasible: bool
    score: float = Field(ge=0, le=1)
    constraint_violations: list[str] = Field(default_factory=list)
    feedback: dict[str, Any] = Field(default_factory=dict)


class IterationRecord(StrictRecord):
    """Single closed-loop iteration record for CSV/JSON experiment outputs."""

    method: str
    trial_id: str
    iteration: int = Field(ge=0)
    parameters: DesignParameters
    simulation: SimulationResult
    manufacturability: ManufacturabilityResult
    evaluation: EvaluationResult
