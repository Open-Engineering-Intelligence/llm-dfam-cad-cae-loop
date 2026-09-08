"""Strict records for the deterministic structural-thinning closed loop."""

from __future__ import annotations

import math
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Literal, TypeAlias

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

SCHEMA_VERSION = "1.0"
CONTROLLER_NAME = "thickness_descent_v1"
EXPERIMENT_NAME = "bracket_v1_structural_thinning_v1"
REFERENCE_DENSITY_G_MM3 = 0.00124
REFERENCE_STRESS_LIMIT_MPA = 25.0
REFERENCE_DISPLACEMENT_LIMIT_MM = 2.0

FiniteNonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
FinitePositive = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class StrictRecord(BaseModel):
    """Immutable JSON-compatible record with no undeclared fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class LoopParameters(StrictRecord):
    """The four parameters understood by the frozen bracket backend."""

    thickness_mm: FinitePositive
    width_mm: FinitePositive
    rib_height_mm: FiniteNonNegative
    fillet_radius_mm: FinitePositive


def _default_parameters() -> LoopParameters:
    return LoopParameters(
        thickness_mm=8.0,
        width_mm=50.0,
        rib_height_mm=18.0,
        fillet_radius_mm=2.0,
    )


class ExperimentConfig(StrictRecord):
    """Effective configuration for the bounded thickness experiment."""

    initial_parameters: LoopParameters = Field(default_factory=_default_parameters)
    min_thickness_mm: FinitePositive = 4.0
    max_thickness_mm: FinitePositive = 14.0
    step_mm: FinitePositive = 1.0
    stress_limit_mpa: FinitePositive = REFERENCE_STRESS_LIMIT_MPA
    displacement_limit_mm: FinitePositive = REFERENCE_DISPLACEMENT_LIMIT_MM
    density_g_mm3: FinitePositive = REFERENCE_DENSITY_G_MM3
    evaluation_budget: int = Field(default=30, gt=0)
    timeout_seconds: int = Field(default=300, gt=0)
    repo_root: Path

    @field_validator("repo_root")
    @classmethod
    def normalize_repo_root(cls, value: Path) -> Path:
        return value.resolve()

    @model_validator(mode="after")
    def validate_search_space(self) -> ExperimentConfig:
        if self.min_thickness_mm > self.max_thickness_mm:
            raise ValueError("min_thickness_mm must not exceed max_thickness_mm")
        if not (
            self.min_thickness_mm
            <= self.initial_parameters.thickness_mm
            <= self.max_thickness_mm
        ):
            raise ValueError("initial thickness must be within configured bounds")
        for name, value in (
            ("min_thickness_mm", self.min_thickness_mm),
            ("max_thickness_mm", self.max_thickness_mm),
            ("step_mm", self.step_mm),
            ("initial thickness", self.initial_parameters.thickness_mm),
        ):
            if not float(value).is_integer():
                raise ValueError(f"{name} must be a whole number of millimeters")
        span_steps = (self.initial_parameters.thickness_mm - self.min_thickness_mm) / self.step_mm
        if not span_steps.is_integer():
            raise ValueError("initial thickness must lie on the configured step lattice")
        frozen_values = {
            "min_thickness_mm": (self.min_thickness_mm, 4.0),
            "max_thickness_mm": (self.max_thickness_mm, 14.0),
            "step_mm": (self.step_mm, 1.0),
            "stress_limit_mpa": (self.stress_limit_mpa, REFERENCE_STRESS_LIMIT_MPA),
            "displacement_limit_mm": (
                self.displacement_limit_mm,
                REFERENCE_DISPLACEMENT_LIMIT_MM,
            ),
            "density_g_mm3": (self.density_g_mm3, REFERENCE_DENSITY_G_MM3),
            "timeout_seconds": (self.timeout_seconds, 300),
        }
        changed = [name for name, (actual, expected) in frozen_values.items() if actual != expected]
        if changed:
            raise ValueError(f"frozen experiment values changed: {', '.join(changed)}")
        if self.initial_parameters != _default_parameters():
            raise ValueError("initial_parameters must match the frozen bracket starting design")
        if self.evaluation_budget > 30:
            raise ValueError("evaluation_budget may not exceed the frozen production budget")
        return self


def validate_parameters(params: LoopParameters, config: ExperimentConfig) -> LoopParameters:
    """Validate a proposed parameter set before invoking a CAD backend."""

    if not config.min_thickness_mm <= params.thickness_mm <= config.max_thickness_mm:
        raise ValueError("thickness_mm is outside configured bounds")
    grid_position = (params.thickness_mm - config.min_thickness_mm) / config.step_mm
    if not grid_position.is_integer():
        raise ValueError("thickness_mm is not on the configured integer grid")
    for name in ("width_mm", "rib_height_mm", "fillet_radius_mm"):
        if getattr(params, name) != getattr(config.initial_parameters, name):
            raise ValueError(f"{name} differs from the frozen starting design")
    return params


def load_experiment_config(repo_root: Path) -> ExperimentConfig:
    """Load the checked-in experiment YAML and attach its absolute repository root."""

    resolved_root = repo_root.resolve()
    config_path = resolved_root / "configs" / "closed_loop_thickness_v1.yaml"
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"experiment config must contain a mapping: {config_path}")
    if "repo_root" in loaded:
        raise ValueError("repo_root is runtime provenance and must not appear in the YAML config")
    if loaded.get("evaluation_budget", 30) != 30:
        raise ValueError("production evaluation_budget must remain frozen at 30")
    return ExperimentConfig.model_validate({**loaded, "repo_root": resolved_root})


class Metrics(StrictRecord):
    """Structural and objective metrics; nulls remain explicit on failed evaluations."""

    max_von_mises_mpa: FiniteNonNegative | None
    max_displacement_mm: FiniteNonNegative | None
    volume_mm3: FinitePositive | None
    mass_g: FinitePositive | None


class ConstraintChecks(StrictRecord):
    """Inclusive checks against the two frozen structural limits."""

    stress_passed: bool | None
    displacement_passed: bool | None


class Failure(StrictRecord):
    """Machine-readable failure with a human-readable explanation."""

    stage: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ArtifactRef(StrictRecord):
    """Content-addressed reference to a file below a run directory."""

    path: str = Field(min_length=1)
    sha256: str

    @field_validator("path")
    @classmethod
    def validate_run_relative_path(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError("artifact path must use POSIX separators")
        posix = PurePosixPath(value)
        windows = PureWindowsPath(value)
        if posix.is_absolute() or windows.is_absolute() or windows.drive:
            raise ValueError("artifact path must be run-relative")
        if any(part in {"", ".", ".."} for part in posix.parts):
            raise ValueError("artifact path must be normalized and may not traverse parents")
        if value.endswith("/") or str(posix) != value:
            raise ValueError("artifact path must be normalized")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value


def _metrics_are_complete(metrics: Metrics) -> bool:
    return all(
        value is not None
        for value in (
            metrics.max_von_mises_mpa,
            metrics.max_displacement_mm,
            metrics.volume_mm3,
            metrics.mass_g,
        )
    )


def _validate_mass(metrics: Metrics) -> None:
    if metrics.volume_mm3 is None or metrics.mass_g is None:
        return
    expected = metrics.volume_mm3 * REFERENCE_DENSITY_G_MM3
    if not math.isclose(metrics.mass_g, expected, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("mass_g must equal volume_mm3 times the frozen reference density")


def _expected_checks(metrics: Metrics) -> ConstraintChecks:
    assert metrics.max_von_mises_mpa is not None
    assert metrics.max_displacement_mm is not None
    return ConstraintChecks(
        stress_passed=metrics.max_von_mises_mpa <= REFERENCE_STRESS_LIMIT_MPA,
        displacement_passed=(
            metrics.max_displacement_mm <= REFERENCE_DISPLACEMENT_LIMIT_MM
        ),
    )


class CandidateEvaluation(StrictRecord):
    """One backend evaluation supplied to the pure controller."""

    iteration: int = Field(ge=0)
    parameters: LoopParameters
    evaluation_status: Literal["completed", "failed"]
    metrics: Metrics
    constraint_checks: ConstraintChecks
    structural_feasible: bool | None
    failure: Failure | None

    @model_validator(mode="after")
    def validate_evaluation_state(self) -> CandidateEvaluation:
        _validate_mass(self.metrics)
        if self.evaluation_status == "failed":
            if self.structural_feasible is not None:
                raise ValueError("failed evaluation must have null structural_feasible")
            if self.failure is None:
                raise ValueError("failed evaluation requires failure details")
            if self.constraint_checks != ConstraintChecks(
                stress_passed=None, displacement_passed=None
            ):
                raise ValueError("failed evaluation must have null constraint checks")
            return self

        if not _metrics_are_complete(self.metrics):
            raise ValueError("completed evaluation requires all finite metrics")
        if self.failure is not None:
            raise ValueError("completed evaluation must not contain failure details")
        expected_checks = _expected_checks(self.metrics)
        if self.constraint_checks != expected_checks:
            raise ValueError("constraint checks do not match completed metrics")
        expected_feasible = bool(
            expected_checks.stress_passed and expected_checks.displacement_passed
        )
        if self.structural_feasible is not expected_feasible:
            raise ValueError("structural_feasible does not match constraint checks")
        return self


def make_completed_evaluation(
    index: int,
    params: LoopParameters,
    volume_mm3: float,
    max_von_mises_mpa: float,
    max_displacement_mm: float,
    *,
    density_g_mm3: float = REFERENCE_DENSITY_G_MM3,
) -> CandidateEvaluation:
    """Build a coherent completed evaluation from raw deterministic outputs."""

    mass_g = volume_mm3 * density_g_mm3
    metrics = Metrics(
        max_von_mises_mpa=max_von_mises_mpa,
        max_displacement_mm=max_displacement_mm,
        volume_mm3=volume_mm3,
        mass_g=mass_g,
    )
    checks = _expected_checks(metrics)
    return CandidateEvaluation(
        iteration=index,
        parameters=params,
        evaluation_status="completed",
        metrics=metrics,
        constraint_checks=checks,
        structural_feasible=bool(checks.stress_passed and checks.displacement_passed),
        failure=None,
    )


def failed_evaluation(
    index: int,
    params: LoopParameters,
    stage: str,
    code: str,
    message: str,
) -> CandidateEvaluation:
    """Build a failed evaluation with explicit null structural values."""

    return CandidateEvaluation(
        iteration=index,
        parameters=params,
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
        failure=Failure(stage=stage, code=code, message=message),
    )


ConstraintName: TypeAlias = Literal["max_von_mises_mpa", "max_displacement_mm"]
DecisionReason: TypeAlias = Literal[
    "feasible_try_thinner",
    "lower_bound_reached",
    "structural_boundary_reached",
    "initial_infeasible",
    "budget_exhausted",
    "evaluation_failed",
    "invalid_proposal",
    "provenance_mismatch",
]


class ControllerDecision(StrictRecord):
    """Persisted output from one invocation of the pure controller."""

    schema_version: Literal["1.0"]
    controller: Literal["thickness_descent_v1"]
    iteration: int = Field(ge=0)
    input_parameters: LoopParameters
    current_evaluation: Literal["feasible", "infeasible", "error"]
    violated_constraints: list[ConstraintName]
    action: Literal["decrease_thickness", "stop"]
    reason: DecisionReason
    next_parameters: LoopParameters | None
    best_feasible_iteration: int | None = Field(ge=0)

    @model_validator(mode="after")
    def validate_decision_shape(self) -> ControllerDecision:
        canonical = ["max_von_mises_mpa", "max_displacement_mm"]
        if self.violated_constraints != [
            item for item in canonical if item in self.violated_constraints
        ]:
            raise ValueError("violated_constraints must be unique and canonically ordered")
        if (
            self.best_feasible_iteration is not None
            and self.best_feasible_iteration > self.iteration
        ):
            raise ValueError("best feasible iteration cannot be in the future")

        if self.action == "decrease_thickness":
            if self.reason != "feasible_try_thinner":
                raise ValueError("decrease_thickness requires feasible_try_thinner")
            if self.current_evaluation != "feasible" or self.violated_constraints:
                raise ValueError("a thickness step requires a feasible current evaluation")
            if self.next_parameters is None:
                raise ValueError("decrease_thickness requires next_parameters")
            if self.best_feasible_iteration is None:
                raise ValueError("a feasible decision requires a best feasible iteration")
            if self.next_parameters.thickness_mm != self.input_parameters.thickness_mm - 1.0:
                raise ValueError("decrease_thickness must take exactly one 1 mm step")
            for name in ("width_mm", "rib_height_mm", "fillet_radius_mm"):
                if getattr(self.next_parameters, name) != getattr(self.input_parameters, name):
                    raise ValueError("decrease_thickness must preserve fixed parameters")
            return self

        if self.next_parameters is not None:
            raise ValueError("stop decision must have null next_parameters")
        allowed_state = {
            "lower_bound_reached": "feasible",
            "structural_boundary_reached": "infeasible",
            "initial_infeasible": "infeasible",
            "budget_exhausted": "feasible",
            "evaluation_failed": "error",
            "invalid_proposal": "error",
            "provenance_mismatch": "error",
        }
        if (
            self.reason == "feasible_try_thinner"
            or allowed_state[self.reason] != self.current_evaluation
        ):
            raise ValueError("stop reason does not match current evaluation state")
        if self.current_evaluation == "feasible" and self.violated_constraints:
            raise ValueError("feasible evaluation cannot have violated constraints")
        if self.current_evaluation == "error" and self.violated_constraints:
            raise ValueError("error decision cannot claim evaluated constraint violations")
        if self.current_evaluation == "infeasible" and not self.violated_constraints:
            raise ValueError("infeasible evaluation requires a violated constraint")
        if self.reason == "initial_infeasible" and self.best_feasible_iteration is not None:
            raise ValueError("initial infeasibility cannot have a best feasible iteration")
        successful_stops = {
            "lower_bound_reached",
            "structural_boundary_reached",
            "budget_exhausted",
        }
        if self.reason in successful_stops:
            if self.best_feasible_iteration is None:
                raise ValueError("successful search history requires a best feasible iteration")
        return self


def _validate_persisted_evaluation(
    status: str,
    metrics: Metrics,
    checks: ConstraintChecks,
    structural_feasible: bool | None,
    failure: Failure | None,
) -> None:
    _validate_mass(metrics)
    if status == "failed":
        if structural_feasible is not None or failure is None:
            raise ValueError("failed manifest requires failure and null structural_feasible")
        if checks != ConstraintChecks(stress_passed=None, displacement_passed=None):
            raise ValueError("failed manifest requires null constraint checks")
        return
    if not _metrics_are_complete(metrics):
        raise ValueError("completed manifest requires all metrics")
    if failure is not None:
        raise ValueError("completed manifest must not contain failure")
    expected_checks = _expected_checks(metrics)
    if checks != expected_checks:
        raise ValueError("manifest checks do not match metrics")
    expected_feasible = bool(expected_checks.stress_passed and expected_checks.displacement_passed)
    if structural_feasible is not expected_feasible:
        raise ValueError("manifest structural feasibility does not match checks")


class IterationManifest(StrictRecord):
    """Content-addressed manifest for a single evaluated iteration."""

    schema_version: Literal["1.0"]
    iteration: int = Field(ge=0)
    previous_iteration_manifest: ArtifactRef | None
    parameters: ArtifactRef
    effective_analysis: ArtifactRef | None
    evaluation_status: Literal["completed", "failed"]
    metrics: Metrics
    constraint_checks: ConstraintChecks
    structural_feasible: bool | None
    dfam_status: Literal["not_evaluated"]
    full_benchmark_feasible: Literal[None]
    cad_manifest: ArtifactRef | None
    mesh_manifest: ArtifactRef | None
    physics_result: ArtifactRef | None
    decision: ArtifactRef
    artifacts: list[ArtifactRef]
    failure: Failure | None
    terminal: bool

    @model_validator(mode="after")
    def validate_manifest(self) -> IterationManifest:
        if (self.iteration == 0) != (self.previous_iteration_manifest is None):
            raise ValueError("only iteration zero may omit the previous manifest")
        artifact_paths = [artifact.path for artifact in self.artifacts]
        if len(artifact_paths) != len(set(artifact_paths)):
            raise ValueError("artifact list contains duplicate paths")
        _validate_persisted_evaluation(
            self.evaluation_status,
            self.metrics,
            self.constraint_checks,
            self.structural_feasible,
            self.failure,
        )
        if self.evaluation_status == "completed":
            completed_refs = (
                self.effective_analysis,
                self.cad_manifest,
                self.mesh_manifest,
                self.physics_result,
            )
            if any(ref is None for ref in completed_refs):
                raise ValueError("completed manifest requires all engineering evidence references")
        elif not self.terminal:
            raise ValueError("failed manifest must be terminal")
        return self


ResultTerminationReason: TypeAlias = Literal[
    "lower_bound_reached",
    "structural_boundary_reached",
    "initial_infeasible",
    "budget_exhausted",
    "evaluation_failed",
    "invalid_proposal",
    "provenance_mismatch",
]


class ClosedLoopResult(StrictRecord):
    """Terminal experiment result; DfAM remains explicitly unevaluated."""

    schema_version: Literal["1.0"]
    experiment: Literal["bracket_v1_structural_thinning_v1"]
    controller: Literal["thickness_descent_v1"]
    status: Literal["accepted", "no_feasible_design", "budget_exhausted", "error"]
    termination_reason: ResultTerminationReason
    experiment_config: ArtifactRef
    environment_manifest: ArtifactRef
    evaluation_count: int = Field(ge=0)
    iteration_manifests: list[ArtifactRef]
    best_feasible_iteration: int | None = Field(ge=0)
    accepted_iteration: int | None = Field(ge=0)
    accepted_parameters: LoopParameters | None
    initial_mass_g: FinitePositive | None
    accepted_mass_g: FinitePositive | None
    mass_reduction_fraction: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None
    dfam_status: Literal["not_evaluated"]
    full_benchmark_feasible: Literal[None]

    @model_validator(mode="after")
    def validate_result(self) -> ClosedLoopResult:
        if len(self.iteration_manifests) != self.evaluation_count:
            raise ValueError("evaluation_count must match iteration manifest count")
        paths = [manifest.path for manifest in self.iteration_manifests]
        if len(paths) != len(set(paths)):
            raise ValueError("iteration manifests must have unique paths")
        for value in (self.best_feasible_iteration, self.accepted_iteration):
            if value is not None and value >= self.evaluation_count:
                raise ValueError("iteration reference must be below evaluation_count")

        expected_reason = {
            "accepted": {"lower_bound_reached", "structural_boundary_reached"},
            "no_feasible_design": {"initial_infeasible"},
            "budget_exhausted": {"budget_exhausted"},
            "error": {"evaluation_failed", "invalid_proposal", "provenance_mismatch"},
        }
        if self.termination_reason not in expected_reason[self.status]:
            raise ValueError("termination reason does not match result status")

        accepted_values = (
            self.accepted_iteration,
            self.accepted_parameters,
            self.accepted_mass_g,
            self.mass_reduction_fraction,
        )
        if self.status == "accepted":
            if self.evaluation_count == 0 or any(value is None for value in accepted_values):
                raise ValueError("accepted result requires accepted design fields")
            if self.initial_mass_g is None or self.best_feasible_iteration is None:
                raise ValueError("accepted result requires initial and best feasible evidence")
            if self.accepted_iteration != self.best_feasible_iteration:
                raise ValueError("accepted iteration must be the best feasible iteration")
            assert self.accepted_iteration is not None
            assert self.accepted_parameters is not None
            expected_parameters = _default_parameters().model_copy(
                update={"thickness_mm": 8.0 - self.accepted_iteration}
            )
            if self.accepted_parameters != expected_parameters:
                raise ValueError("accepted parameters do not match the accepted iteration")
            if (
                self.termination_reason == "structural_boundary_reached"
                and self.accepted_iteration >= self.evaluation_count - 1
            ):
                raise ValueError("structural boundary requires a later infeasible evaluation")
            assert self.accepted_mass_g is not None
            assert self.mass_reduction_fraction is not None
            expected_fraction = (self.initial_mass_g - self.accepted_mass_g) / self.initial_mass_g
            if not math.isclose(
                self.mass_reduction_fraction,
                expected_fraction,
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                raise ValueError("mass reduction fraction does not match recorded masses")
        elif any(value is not None for value in accepted_values):
            raise ValueError("non-accepted result must have null accepted design fields")

        if self.status == "no_feasible_design" and self.best_feasible_iteration is not None:
            raise ValueError("no-feasible-design result cannot identify a feasible iteration")
        if self.status == "no_feasible_design" and self.evaluation_count != 1:
            raise ValueError("initial infeasibility must terminate after one evaluation")
        if self.status == "budget_exhausted" and self.best_feasible_iteration is None:
            raise ValueError("budget exhaustion after feasible descent requires a best iteration")
        return self


PersistedArtifact: TypeAlias = ControllerDecision | IterationManifest | ClosedLoopResult


def schema_document() -> dict[str, object]:
    """Return the JSON Schema union for the three persisted artifact records."""

    return TypeAdapter(PersistedArtifact).json_schema(union_format="any_of")


__all__ = [
    "ArtifactRef",
    "CandidateEvaluation",
    "ClosedLoopResult",
    "ConstraintChecks",
    "ControllerDecision",
    "ExperimentConfig",
    "Failure",
    "IterationManifest",
    "LoopParameters",
    "Metrics",
    "failed_evaluation",
    "load_experiment_config",
    "make_completed_evaluation",
    "schema_document",
    "validate_parameters",
]
