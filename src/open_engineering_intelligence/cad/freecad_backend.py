"""FreeCAD adapter for Benchmark Bracket v1.

This module intentionally lazy-loads FreeCAD so the ordinary Python package can
be imported on machines that do not have FreeCAD installed.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BracketV1Dimensions:
    """Frozen dimensions from `configs/bracket_default.yaml`."""

    span_length: float = 100.0
    base_depth_x: float = 8.0
    base_width_y: float = 70.0
    base_height_z: float = 70.0
    load_pad_length_x: float = 10.0
    rib_thickness_y: float = 6.0


BRACKET_V1_DIMENSIONS = BracketV1Dimensions()


def load_bracket_v1_dimensions(config_path: Path) -> BracketV1Dimensions:
    """Load the frozen bracket dimensions from `configs/bracket_default.yaml`."""

    import yaml

    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    fixed = config["geometry"]["fixed_dimensions_mm"]
    return BracketV1Dimensions(
        span_length=float(fixed["span_length"]),
        base_depth_x=float(fixed["base_depth_x"]),
        base_width_y=float(fixed["base_width_y"]),
        base_height_z=float(fixed["base_height_z"]),
        load_pad_length_x=float(fixed["load_pad_length_x"]),
        rib_thickness_y=float(fixed["rib_thickness_y"]),
    )


class FreeCADBracketBackend:
    """Generate Benchmark Bracket v1 CAD artifacts from structured parameters."""

    def __init__(self, dimensions: BracketV1Dimensions = BRACKET_V1_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def generate(self, parameters: Any, output_dir: Path) -> dict[str, Path]:
        freecad, part = _freecad_modules()
        params = _coerce_parameters(parameters)
        _validate_against_benchmark(params, self.dimensions)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        doc_path = output_dir / "bracket_v1.FCStd"
        step_path = output_dir / "bracket_v1.step"
        manifest_path = output_dir / "bracket_v1_manifest.json"

        doc = freecad.newDocument("BracketV1")
        try:
            shape = _build_shape(part, freecad, params, self.dimensions)
            if not shape.isValid():
                raise ValueError("generated bracket shape is invalid")

            obj = doc.addObject("Part::Feature", "BracketV1")
            obj.Shape = shape
            doc.recompute()
            doc.saveAs(str(doc_path))
            part.export([obj], str(step_path))

            manifest = _manifest(shape, params, self.dimensions)
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        finally:
            freecad.closeDocument(doc.Name)

        return {
            "freecad_document": doc_path,
            "step": step_path,
            "manifest": manifest_path,
        }


def _freecad_modules() -> tuple[Any, Any]:
    try:
        import FreeCAD  # type: ignore[import-not-found]
        import Part  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "FreeCAD Python modules are required. Run this backend with FreeCADCmd."
        ) from exc
    return FreeCAD, Part


def _coerce_parameters(parameters: Any) -> dict[str, float]:
    if hasattr(parameters, "model_dump"):
        raw = parameters.model_dump()
    elif isinstance(parameters, dict):
        raw = parameters
    else:
        raw = {name: getattr(parameters, name) for name in _PARAMETER_BOUNDS}

    values = {name: float(raw[name]) for name in _PARAMETER_BOUNDS}
    for name, value in values.items():
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    return values


_PARAMETER_BOUNDS: dict[str, tuple[float, float]] = {
    "thickness_mm": (4.0, 14.0),
    "width_mm": (30.0, 80.0),
    "rib_height_mm": (0.0, 35.0),
    "fillet_radius_mm": (1.0, 8.0),
}


def _validate_against_benchmark(
    params: dict[str, float],
    dimensions: BracketV1Dimensions,
) -> None:
    for name, (lower, upper) in _PARAMETER_BOUNDS.items():
        value = params[name]
        if value < lower or value > upper:
            raise ValueError(f"{name}={value} is outside [{lower}, {upper}]")
    if params["width_mm"] <= dimensions.rib_thickness_y:
        raise ValueError("width_mm must exceed fixed rib thickness")
    if params["fillet_radius_mm"] > params["thickness_mm"]:
        raise ValueError("fillet_radius_mm must not exceed thickness_mm")


def _build_shape(
    part: Any,
    freecad: Any,
    params: dict[str, float],
    dimensions: BracketV1Dimensions,
) -> Any:
    vector = freecad.Vector
    thickness = params["thickness_mm"]
    width = params["width_mm"]
    rib_height = params["rib_height_mm"]
    base = part.makeBox(
        dimensions.base_depth_x,
        dimensions.base_width_y,
        dimensions.base_height_z,
        vector(0, -dimensions.base_width_y / 2, 0),
    )
    arm = part.makeBox(
        dimensions.span_length,
        width,
        thickness,
        vector(dimensions.base_depth_x, -width / 2, 0),
    )
    solids = [base, arm]

    if rib_height > 0:
        solids.append(_make_triangular_rib(part, vector, params, dimensions))

    shape = solids[0]
    for solid in solids[1:]:
        shape = shape.fuse(solid)
    shape = shape.removeSplitter()
    return _apply_fillets(shape, params, dimensions)


def _make_triangular_rib(
    part: Any,
    vector: Any,
    params: dict[str, float],
    dimensions: BracketV1Dimensions,
) -> Any:
    thickness = params["thickness_mm"]
    rib_height = params["rib_height_mm"]
    y0 = -dimensions.rib_thickness_y / 2
    rib_end_x = dimensions.base_depth_x + dimensions.span_length - dimensions.load_pad_length_x
    points = [
        vector(dimensions.base_depth_x, y0, thickness),
        vector(dimensions.base_depth_x, y0, thickness + rib_height),
        vector(rib_end_x, y0, thickness),
        vector(dimensions.base_depth_x, y0, thickness),
    ]
    face = part.Face(part.makePolygon(points))
    return face.extrude(vector(0, dimensions.rib_thickness_y, 0))


def _apply_fillets(
    shape: Any,
    params: dict[str, float],
    dimensions: BracketV1Dimensions,
) -> Any:
    radius = params["fillet_radius_mm"]
    thickness = params["thickness_mm"]
    rib_y = dimensions.rib_thickness_y / 2
    rib_end_x = dimensions.base_depth_x + dimensions.span_length - dimensions.load_pad_length_x
    fillet_edges = []

    for edge in shape.Edges:
        center = edge.CenterOfMass
        if not _near(center.z, thickness) or edge.Length <= 1:
            continue
        if _near(center.x, dimensions.base_depth_x):
            fillet_edges.append(edge)
            continue
        if (
            params["rib_height_mm"] > 0
            and _near(abs(center.y), rib_y)
            and dimensions.base_depth_x < center.x < rib_end_x
        ):
            fillet_edges.append(edge)

    if not fillet_edges:
        raise ValueError("no deterministic root or rib fillet edges were found")
    filleted = shape.makeFillet(radius, fillet_edges).removeSplitter()
    if not filleted.isValid():
        raise ValueError("requested fillet radius produced invalid geometry")
    return filleted


def _manifest(
    shape: Any,
    params: dict[str, float],
    dimensions: BracketV1Dimensions,
) -> dict[str, Any]:
    bbox = shape.BoundBox
    center = _center_point(shape)
    fingerprint = {
        "volume_mm3": _rounded(shape.Volume),
        "area_mm2": _rounded(shape.Area),
        "center_of_mass_mm": [_rounded(center.x), _rounded(center.y), _rounded(center.z)],
        "bounding_box_mm": {
            "xmin": _rounded(bbox.XMin),
            "xmax": _rounded(bbox.XMax),
            "ymin": _rounded(bbox.YMin),
            "ymax": _rounded(bbox.YMax),
            "zmin": _rounded(bbox.ZMin),
            "zmax": _rounded(bbox.ZMax),
        },
        "topology": {
            "vertices": len(shape.Vertexes),
            "edges": len(shape.Edges),
            "faces": len(shape.Faces),
        },
    }
    return {
        "benchmark": "bracket_v1",
        "shape_valid": bool(shape.isValid()),
        "parameters": {key: _rounded(value) for key, value in params.items()},
        "dimensions": asdict(dimensions),
        "geometry_fingerprint": fingerprint,
        "artifacts": ["bracket_v1.FCStd", "bracket_v1.step"],
        "notes": [
            "FreeCAD PoC applies deterministic root and rib junction fillets.",
            "No Gmsh, CalculiX, FEA, DfAM evaluation, LLM, or optimization is run.",
        ],
    }


def _rounded(value: float) -> float:
    return round(float(value), 6)


def _near(left: float, right: float, *, tolerance: float = 1e-6) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def _center_point(shape: Any) -> Any:
    solids = getattr(shape, "Solids", [])
    if solids:
        total_volume = sum(float(solid.Volume) for solid in solids)
        if total_volume > 0:
            return type(shape.BoundBox.Center)(
                sum(float(solid.Volume) * solid.CenterOfMass.x for solid in solids) / total_volume,
                sum(float(solid.Volume) * solid.CenterOfMass.y for solid in solids) / total_volume,
                sum(float(solid.Volume) * solid.CenterOfMass.z for solid in solids) / total_volume,
            )
    return shape.BoundBox.Center
