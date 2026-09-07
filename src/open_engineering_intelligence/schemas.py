"""Data structures for reproducible closed-loop experiments."""

from __future__ import annotations

from typing import Any

try:
    from pydantic import BaseModel, ConfigDict, Field
except ImportError:  # pragma: no cover - exercised by FreeCAD's bundled Python.
    _PYDANTIC_AVAILABLE = False
else:
    _PYDANTIC_AVAILABLE = True


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
