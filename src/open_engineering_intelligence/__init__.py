"""Open Engineering Intelligence research contracts."""

from typing import Any

__version__ = "0.1.0"

__all__ = [
    "DesignParameters",
    "EvaluationResult",
    "IterationRecord",
    "ManufacturabilityResult",
    "SimulationResult",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from open_engineering_intelligence import schemas

        return getattr(schemas, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
