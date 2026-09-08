"""Data structures for reproducible closed-loop experiments."""

from __future__ import annotations

import math
from typing import Any

try:
    from pydantic import BaseModel, ConfigDict, Field, model_validator
except ImportError:  # pragma: no cover - exercised by FreeCAD's bundled Python.
    _PYDANTIC_AVAILABLE = False
else:
    _PYDANTIC_AVAILABLE = True


def _validate_simulation_state(
    succeeded: bool,
    max_von_mises_mpa: float | None,
    max_displacement_mm: float | None,
    mass_g: float | None,
    failure_reason: str | None,
) -> None:
    metrics = (max_von_mises_mpa, max_displacement_mm, mass_g)
    for value in metrics:
        if value is not None and not math.isfinite(value):
            raise ValueError("simulation metrics must be finite")
    if max_von_mises_mpa is not None and max_von_mises_mpa < 0:
        raise ValueError("max_von_mises_mpa must be non-negative")
    if max_displacement_mm is not None and max_displacement_mm < 0:
        raise ValueError("max_displacement_mm must be non-negative")
    if mass_g is not None and mass_g <= 0:
        raise ValueError("mass_g must be positive")

    if succeeded:
        if any(value is None for value in metrics):
            raise ValueError("succeeded simulation requires all finite metrics")
        if failure_reason is not None:
            raise ValueError("succeeded simulation must not contain a failure_reason")
        return

    if any(value is not None for value in metrics):
        raise ValueError("failed simulation must have null metrics")
    if failure_reason is None or not failure_reason.strip():
        raise ValueError("failed simulation requires a failure_reason")


if _PYDANTIC_AVAILABLE:

    class StrictRecord(BaseModel):
        """Base model that rejects undeclared fields in experiment records."""

        model_config = ConfigDict(extra="forbid", frozen=True)


    class DesignParameters(StrictRecord):
        """Structured parameter proposal accepted by deterministic CAD generators."""

        thickness_mm: float = Field(gt=0)
        width_mm: float = Field(gt=0)
        rib_height_mm: float = Field(ge=0)
        fillet_radius_mm: float = Field(gt=0)


    class SimulationResult(StrictRecord):
        """Physics result parsed from deterministic CAE execution."""

        succeeded: bool = Field(strict=True)
        max_von_mises_mpa: float | None = Field(default=None, ge=0, allow_inf_nan=False)
        max_displacement_mm: float | None = Field(default=None, ge=0, allow_inf_nan=False)
        mass_g: float | None = Field(default=None, gt=0, allow_inf_nan=False)
        failure_reason: str | None = None

        @model_validator(mode="after")
        def validate_result_state(self) -> SimulationResult:
            _validate_simulation_state(
                self.succeeded,
                self.max_von_mises_mpa,
                self.max_displacement_mm,
                self.mass_g,
                self.failure_reason,
            )
            return self


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

else:

    class StrictRecord:
        """Small fallback record for constrained Python runtimes such as FreeCADCmd."""

        _fields: tuple[str, ...] = ()
        _frozen = False

        def __init__(self, **data: Any) -> None:
            expected = set(self._fields)
            extra = set(data) - expected
            missing = expected - set(data)
            if extra:
                raise TypeError(f"unexpected fields: {sorted(extra)}")
            if missing:
                raise TypeError(f"missing fields: {sorted(missing)}")
            for name in self._fields:
                object.__setattr__(self, name, data[name])
            object.__setattr__(self, "_frozen", True)
            self._validate()

        def __setattr__(self, name: str, value: Any) -> None:
            if self._frozen:
                raise TypeError(f"{self.__class__.__name__} is frozen")
            object.__setattr__(self, name, value)

        def _validate(self) -> None:
            return None

        def model_dump(self) -> dict[str, Any]:
            return {name: getattr(self, name) for name in self._fields}


    class DesignParameters(StrictRecord):
        """Structured parameter proposal accepted by deterministic CAD generators."""

        _fields = ("thickness_mm", "width_mm", "rib_height_mm", "fillet_radius_mm")

        def _validate(self) -> None:
            for name in self._fields:
                object.__setattr__(self, name, float(getattr(self, name)))
            if self.thickness_mm <= 0:
                raise ValueError("thickness_mm must be greater than 0")
            if self.width_mm <= 0:
                raise ValueError("width_mm must be greater than 0")
            if self.rib_height_mm < 0:
                raise ValueError("rib_height_mm must be greater than or equal to 0")
            if self.fillet_radius_mm <= 0:
                raise ValueError("fillet_radius_mm must be greater than 0")


    class SimulationResult(StrictRecord):
        """Physics result parsed from deterministic CAE execution."""

        _fields = (
            "succeeded",
            "max_von_mises_mpa",
            "max_displacement_mm",
            "mass_g",
            "failure_reason",
        )

        def __init__(
            self,
            *,
            succeeded: bool,
            max_von_mises_mpa: float | None = None,
            max_displacement_mm: float | None = None,
            mass_g: float | None = None,
            failure_reason: str | None = None,
        ) -> None:
            super().__init__(
                succeeded=succeeded,
                max_von_mises_mpa=max_von_mises_mpa,
                max_displacement_mm=max_displacement_mm,
                mass_g=mass_g,
                failure_reason=failure_reason,
            )

        def _validate(self) -> None:
            if not isinstance(self.succeeded, bool):
                raise TypeError("succeeded must be a bool")
            for name in ("max_von_mises_mpa", "max_displacement_mm", "mass_g"):
                value = getattr(self, name)
                if value is not None:
                    object.__setattr__(self, name, float(value))
            _validate_simulation_state(
                self.succeeded,
                self.max_von_mises_mpa,
                self.max_displacement_mm,
                self.mass_g,
                self.failure_reason,
            )


    class ManufacturabilityResult(StrictRecord):
        """DfAM validation result for FDM-oriented manufacturability checks."""

        _fields = (
            "passed",
            "min_wall_thickness_mm",
            "max_overhang_angle_deg",
            "support_required",
            "score",
            "failure_reason",
        )


    class EvaluationResult(StrictRecord):
        """Unified evaluation result used as feedback for later design proposals."""

        _fields = ("feasible", "score", "constraint_violations", "feedback")


    class IterationRecord(StrictRecord):
        """Single closed-loop iteration record for CSV/JSON experiment outputs."""

        _fields = (
            "method",
            "trial_id",
            "iteration",
            "parameters",
            "simulation",
            "manufacturability",
            "evaluation",
        )
