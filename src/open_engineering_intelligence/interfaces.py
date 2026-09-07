"""Abstract contracts for backend-agnostic engineering design loops."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from open_engineering_intelligence.schemas import (
    DesignParameters,
    EvaluationResult,
    ManufacturabilityResult,
    SimulationResult,
)


class CADBackend(ABC):
    """Deterministically converts structured parameters into CAD artifacts."""

    @abstractmethod
    def generate(self, parameters: DesignParameters, output_dir: Path) -> dict[str, Path]:
        """Generate CAD artifacts and return named artifact paths."""


class CAEBackend(ABC):
    """Runs deterministic meshing and simulation for a generated design."""

    @abstractmethod
    def simulate(self, cad_artifacts: dict[str, Path], output_dir: Path) -> SimulationResult:
        """Run simulation and return structured physics results."""


class DesignAgent(ABC):
    """Proposes strict structured design parameters from requirement and feedback."""

    @abstractmethod
    def propose(
        self,
        requirement: str,
        feedback: dict[str, Any] | None = None,
    ) -> DesignParameters:
        """Return the next parameter proposal."""


class GeometryValidator(ABC):
    """Validates generated geometry before meshing and simulation."""

    @abstractmethod
    def validate(self, cad_artifacts: dict[str, Path]) -> EvaluationResult:
        """Return geometry validation evidence."""


class PhysicsValidator(ABC):
    """Checks simulation results against structural constraints."""

    @abstractmethod
    def validate(self, simulation: SimulationResult) -> EvaluationResult:
        """Return structural validation evidence."""


class ManufacturabilityValidator(ABC):
    """Checks additive-manufacturing constraints for a generated design."""

    @abstractmethod
    def validate(
        self,
        parameters: DesignParameters,
        cad_artifacts: dict[str, Path],
    ) -> ManufacturabilityResult:
        """Return DfAM validation evidence."""


class Optimizer(ABC):
    """Non-LLM optimizer contract for baseline comparisons."""

    @abstractmethod
    def suggest(
        self,
        history: list[EvaluationResult],
        bounds: dict[str, tuple[float, float]],
    ) -> DesignParameters:
        """Suggest the next parameter set under the same evaluation budget."""
