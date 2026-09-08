"""Minimal Gmsh volume mesher for validated STEP artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GmshMeshingConfig:
    """Explicit first-order tetrahedral meshing settings."""

    dimension: int
    element_order: int
    algorithm_2d: int
    algorithm_3d: int
    characteristic_length_min_mm: float
    characteristic_length_max_mm: float
    num_threads: int
    random_factor: float
    msh_file_version: float
    binary: bool


class GmshMeshingError(RuntimeError):
    """Failure with the meshing stage preserved for later evaluation records."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        self.message = message
        super().__init__(f"{stage}: {message}")


def load_gmsh_meshing_config(config_path: Path) -> GmshMeshingConfig:
    """Load the frozen Benchmark v1 Gmsh settings."""

    import yaml

    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))["meshing"]
    if raw["backend"] != "gmsh":
        raise ValueError("meshing backend must be 'gmsh'")
    config = GmshMeshingConfig(
        dimension=int(raw["dimension"]),
        element_order=int(raw["element_order"]),
        algorithm_2d=int(raw["algorithm_2d"]),
        algorithm_3d=int(raw["algorithm_3d"]),
        characteristic_length_min_mm=float(raw["characteristic_length_min_mm"]),
        characteristic_length_max_mm=float(raw["characteristic_length_max_mm"]),
        num_threads=int(raw["num_threads"]),
        random_factor=float(raw["random_factor"]),
        msh_file_version=float(raw["msh_file_version"]),
        binary=bool(raw["binary"]),
    )
    if config.dimension != 3:
        raise ValueError("GmshMesher requires dimension=3")
    if config.element_order != 1:
        raise ValueError("GmshMesher requires element_order=1")
    if config.num_threads != 1:
        raise ValueError("GmshMesher requires num_threads=1")
    if config.characteristic_length_min_mm <= 0:
        raise ValueError("characteristic_length_min_mm must be positive")
    if config.characteristic_length_max_mm < config.characteristic_length_min_mm:
        raise ValueError("characteristic_length_max_mm must be at least the minimum")
    return config


class GmshMesher:
    """Import STEP geometry and generate a checked 3D Gmsh mesh."""

    def __init__(self, config: GmshMeshingConfig) -> None:
        self.config = config

    def mesh(
        self,
        step_path: Path,
        cad_manifest_path: Path,
        output_dir: Path,
    ) -> dict[str, Path]:
        step_path = Path(step_path)
        cad_manifest_path = Path(cad_manifest_path)
        output_dir = Path(output_dir)
        self._validate_step(step_path)
        source_fingerprint = self._load_source_fingerprint(cad_manifest_path)

        try:
            import gmsh
        except ImportError as exc:  # pragma: no cover - depends on local tooling.
            raise GmshMeshingError(
                "dependency_import",
                "Gmsh Python API is unavailable; install the 'cae' optional dependency",
            ) from exc

        output_dir.mkdir(parents=True, exist_ok=True)
        mesh_path = output_dir / "bracket_v1.msh"
        manifest_path = output_dir / "bracket_v1_mesh_manifest.json"
        initialized = False
        try:
            gmsh.initialize()
            initialized = True
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.model.add("bracket_v1")
            self._set_options(gmsh)

            try:
                imported_entities = gmsh.model.occ.importShapes(str(step_path.resolve()))
                gmsh.model.occ.synchronize()
            except Exception as exc:
                raise GmshMeshingError("step_import", str(exc)) from exc
            if not imported_entities:
                raise GmshMeshingError("step_import", "Gmsh imported no STEP entities")

            volume_entities = gmsh.model.getEntities(3)
            if not volume_entities:
                raise GmshMeshingError("volume_detection", "STEP contains no volume entity")

            try:
                gmsh.model.mesh.generate(self.config.dimension)
            except Exception as exc:
                raise GmshMeshingError("mesh_generation", str(exc)) from exc

            statistics = _mesh_statistics(gmsh)
            if statistics["node_count"] <= 0 or statistics["element_count"] <= 0:
                raise GmshMeshingError("mesh_validation", "generated mesh is empty")
            if statistics["volume_element_count"] <= 0:
                raise GmshMeshingError("mesh_validation", "generated mesh has no 3D elements")

            try:
                gmsh.write(str(mesh_path))
            except Exception as exc:
                raise GmshMeshingError("mesh_write", str(exc)) from exc
            if not mesh_path.is_file() or mesh_path.stat().st_size == 0:
                raise GmshMeshingError("mesh_write", "Gmsh did not write a non-empty mesh")

            manifest = {
                "backend": "gmsh",
                "gmsh_version": str(gmsh.__version__),
                "invocation_method": "python_api",
                "source_step": str(step_path.resolve()),
                "source_geometry_fingerprint": source_fingerprint,
                "dimension": self.config.dimension,
                "element_order": self.config.element_order,
                "volume_entity_count": len(volume_entities),
                **statistics,
                "meshing_parameters": asdict(self.config),
                "mesh_file": mesh_path.name,
            }
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        finally:
            if initialized:
                gmsh.finalize()

        return {"mesh": mesh_path, "manifest": manifest_path}

    @staticmethod
    def _validate_step(step_path: Path) -> None:
        if not step_path.is_file():
            raise GmshMeshingError("step_validation", "STEP artifact does not exist")
        if step_path.stat().st_size == 0:
            raise GmshMeshingError("step_validation", "STEP artifact is empty")

    @staticmethod
    def _load_source_fingerprint(cad_manifest_path: Path) -> dict[str, Any]:
        if not cad_manifest_path.is_file():
            raise GmshMeshingError("manifest_validation", "CAD manifest does not exist")
        try:
            manifest = json.loads(cad_manifest_path.read_text(encoding="utf-8"))
            fingerprint = manifest["cad_fingerprint"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise GmshMeshingError(
                "manifest_validation", "CAD manifest has no valid cad_fingerprint"
            ) from exc
        if not isinstance(fingerprint, dict) or not fingerprint:
            raise GmshMeshingError(
                "manifest_validation", "CAD manifest has no valid cad_fingerprint"
            )
        return fingerprint

    def _set_options(self, gmsh: Any) -> None:
        options = {
            "General.NumThreads": self.config.num_threads,
            "Mesh.MaxNumThreads1D": self.config.num_threads,
            "Mesh.MaxNumThreads2D": self.config.num_threads,
            "Mesh.MaxNumThreads3D": self.config.num_threads,
            "Mesh.ElementOrder": self.config.element_order,
            "Mesh.Algorithm": self.config.algorithm_2d,
            "Mesh.Algorithm3D": self.config.algorithm_3d,
            "Mesh.MeshSizeMin": self.config.characteristic_length_min_mm,
            "Mesh.MeshSizeMax": self.config.characteristic_length_max_mm,
            "Mesh.RandomFactor": self.config.random_factor,
            "Mesh.MshFileVersion": self.config.msh_file_version,
            "Mesh.Binary": int(self.config.binary),
        }
        for name, value in options.items():
            gmsh.option.setNumber(name, value)


def _mesh_statistics(gmsh: Any) -> dict[str, Any]:
    node_tags, _, _ = gmsh.model.mesh.getNodes()
    element_types, element_tags, _ = gmsh.model.mesh.getElements()
    element_count = 0
    volume_element_count = 0
    element_type_counts: dict[str, dict[str, Any]] = {}
    for element_type, tags in zip(element_types, element_tags, strict=True):
        name, dimension, order, _, _, _ = gmsh.model.mesh.getElementProperties(element_type)
        count = len(tags)
        element_count += count
        if dimension == 3:
            volume_element_count += count
        element_type_counts[str(element_type)] = {
            "name": name,
            "dimension": dimension,
            "order": order,
            "count": count,
        }
    return {
        "node_count": len(node_tags),
        "element_count": element_count,
        "volume_element_count": volume_element_count,
        "element_types": element_type_counts,
    }
