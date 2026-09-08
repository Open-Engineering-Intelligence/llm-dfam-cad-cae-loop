"""Deterministic CalculiX static analysis for Benchmark Bracket v1."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path


class CalculiXStaticError(RuntimeError):
    """Failure with a stable analysis stage and optional result artifact."""

    def __init__(self, stage: str, message: str, result_path: Path | None = None) -> None:
        self.stage = stage
        self.message = message
        self.result_path = result_path
        super().__init__(f"{stage}: {message}")


@dataclass(frozen=True)
class Tetrahedron:
    """A provenance-preserving first-order volume element."""

    element_id: int
    node_ids: tuple[int, ...]


@dataclass(frozen=True)
class GmshMesh:
    """Subset of an ASCII Gmsh mesh needed by CalculiX."""

    nodes: dict[int, tuple[float, float, float]]
    surface_node_ids: frozenset[int]
    tetrahedra: tuple[Tetrahedron, ...]


@dataclass(frozen=True)
class IntegrationPointStress:
    """One authoritative CalculiX DAT integration-point stress tensor."""

    element_id: int
    integration_point: int
    components: tuple[float, float, float, float, float, float]


@dataclass(frozen=True)
class DisplacementMaximum:
    value: float
    node_id: int
    unit: str = "mm"


@dataclass(frozen=True)
class StressMaximum:
    value: float
    element_id: int
    integration_point: int
    unit: str = "MPa"
    position: str = "integration_point"


@dataclass(frozen=True)
class CalculiXParsedResults:
    """Validated raw fields parsed from observed CalculiX 2.22 output tables."""

    displacements: dict[int, tuple[float, float, float]]
    reaction_forces: dict[int, tuple[float, float, float]]
    integration_point_stresses: tuple[IntegrationPointStress, ...]

    @property
    def reactions(self):
        return self.reaction_forces

    @property
    def stresses(self):
        return {
            (s.element_id, s.integration_point): s.components
            for s in self.integration_point_stresses
        }

    @property
    def max_displacement(self) -> DisplacementMaximum:
        node_id = max(sorted(self.displacements), key=lambda n: math.hypot(*self.displacements[n]))
        return DisplacementMaximum(math.hypot(*self.displacements[node_id]), node_id)

    @property
    def max_von_mises(self) -> StressMaximum:
        stress = max(
            sorted(
                self.integration_point_stresses, key=lambda s: (s.element_id, s.integration_point)
            ),
            key=lambda s: von_mises_stress(*s.components),
        )
        return StressMaximum(
            von_mises_stress(*stress.components), stress.element_id, stress.integration_point
        )


@dataclass(frozen=True)
class CalculiXStaticConfig:
    """Frozen inputs for the first CalculiX linear-static benchmark analysis."""

    target_version: str
    case_name: str
    timeout_seconds: int
    element_type: str
    geometric_nonlinearity: bool
    units: dict[str, str]
    material_name: str
    youngs_modulus_mpa: float
    poissons_ratio: float
    material_scope: str
    fixed_x_mm: float
    coordinate_tolerance_mm: float
    constrained_dofs: tuple[int, int, int]
    load_x_range_mm: tuple[float, float]
    load_y_range_mm: tuple[float, float]
    load_z_mm: float
    total_load_n: tuple[float, float, float]


FAILURE_STAGES = frozenset(
    {
        "mesh_validation",
        "boundary_selection",
        "input_generation",
        "solver_invocation",
        "solver_execution",
        "result_parsing",
        "physics_validation",
    }
)

SANITY_CHECKS = (
    "fixed_nodes_nonempty",
    "load_nodes_nonempty",
    "node_sets_disjoint",
    "tetrahedra_valid",
    "total_load_correct",
    "solver_completed",
    "results_finite",
    "fixed_displacement_near_zero",
    "loaded_region_average_uz_negative",
    "reaction_equilibrium",
    "max_displacement_node_valid",
    "max_stress_element_valid",
)


class CalculiXStaticSolver:
    """MSH + mesh manifest -> deterministic input, retained solver artifacts and JSON.

    Each solve owns a new/empty output directory. Existing evidence is never replaced.
    Errors raise CalculiXStaticError with a failed result path when the directory is writable.
    """

    def __init__(self, config: CalculiXStaticConfig, *, executable: Path | None = None):
        _validate_config(config)
        self.config = config
        self.executable = executable

    def solve(self, mesh_path: Path, mesh_manifest_path: Path, output_dir: Path) -> dict[str, Path]:
        config = self.config
        output_dir = Path(output_dir).resolve()
        if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
            raise CalculiXStaticError(
                "input_generation", "output directory is not empty; use a new run"
            )
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CalculiXStaticError(
                "input_generation", f"cannot create output directory: {exc}"
            ) from exc
        stage = "mesh_validation"
        checks = dict.fromkeys(SANITY_CHECKS)
        result = {
            "solver": "calculix",
            "solver_version": None,
            "invocation_method": "subprocess.run; shell=False",
            "solver_status": "failed",
            "failure_stage": None,
            "failure_reason": None,
            "units": {**config.units, "displacement": "mm"},
            "input_geometry_fingerprint": None,
            "mesh_provenance": None,
            "boundary_condition": dict(analysis_definition(config)["boundary_condition"]),
            "load": dict(analysis_definition(config)["load"]),
            "analysis_definition": analysis_definition(config),
            "analysis_fingerprint": analysis_fingerprint(config),
            "calculix_input_sha256": None,
            "max_displacement": None,
            "max_von_mises_stress": None,
            "reaction_force_n": None,
            "equilibrium_residual_n": None,
            "sanity_checks": checks,
        }
        result_path = output_dir / "physics_result.json"
        artifacts = {
            "result": result_path,
            "stdout": output_dir / "ccx.stdout.log",
            "stderr": output_dir / "ccx.stderr.log",
        }
        try:
            mesh_path, mesh_manifest_path = (
                Path(mesh_path).resolve(),
                Path(mesh_manifest_path).resolve(),
            )
            mesh = parse_gmsh_msh(mesh_path)
            geometry, provenance = _mesh_provenance(mesh_path, mesh_manifest_path, mesh)
            result["input_geometry_fingerprint"] = geometry
            result["mesh_provenance"] = provenance
            result["source_artifacts"] = {
                "mesh": str(mesh_path),
                "manifest": str(mesh_manifest_path),
            }
            checks["tetrahedra_valid"] = True
            volume_nodes = {n for element in mesh.tetrahedra for n in element.node_ids}
            # The generated backend mesh has no disconnected/orphan nodes. Do not send
            # unused nodes to ALL_NODES or allow an orphan node to receive a load.
            if set(mesh.nodes) != volume_nodes or not mesh.surface_node_ids <= volume_nodes:
                raise CalculiXStaticError(
                    "mesh_validation", "mesh contains non-volume or dangling surface nodes"
                )
            stage = "boundary_selection"
            fixed = select_fixed_nodes(mesh, config)
            checks["fixed_nodes_nonempty"] = bool(fixed)
            loaded = select_load_nodes(mesh, config, fixed_node_ids=fixed)
            checks["load_nodes_nonempty"] = bool(loaded)
            checks["node_sets_disjoint"] = not set(fixed).intersection(loaded)
            loads = equivalent_nodal_loads(loaded, config.total_load_n)
            # Check the serialized precision actually sent to ccx, not just Python division.
            applied = tuple(
                math.fsum(float(_format_float(v[i])) for v in loads.values()) for i in range(3)
            )
            checks["total_load_correct"] = math.dist(applied, config.total_load_n) <= 1e-9
            if not checks["total_load_correct"]:
                raise CalculiXStaticError(
                    "input_generation", "nodal loads do not reconstruct total force"
                )
            result["boundary_condition"].update(
                node_set="FIXED_NODES", node_ids=list(fixed), node_count=len(fixed)
            )
            result["load"].update(
                node_set="LOAD_NODES",
                node_ids=list(loaded),
                node_count=len(loaded),
                force_per_node_n=list(next(iter(loads.values()))),
                summed_force_n=list(applied),
            )
            stage = "input_generation"
            artifacts["input"], result["calculix_input_sha256"] = write_calculix_input(
                output_dir, mesh=mesh, config=config, fixed_node_ids=fixed, nodal_loads=loads
            )
            stage = "solver_invocation"
            executable, discovery = discover_calculix_executable(self.executable)
            args = [str(executable), "-i", config.case_name]
            result["invocation"] = {
                "executable": str(executable),
                "discovery": discovery,
                "arguments": args,
                "cwd": str(output_dir),
                "timeout_seconds": config.timeout_seconds,
                "num_threads": 1,
                "return_code": None,
            }
            environment = os.environ.copy()
            environment.update(
                OMP_NUM_THREADS="1",
                CCX_NPROC_RESULTS="1",
                CCX_NPROC_STIFFNESS="1",
                NUMBER_OF_CPUS="1",
            )
            try:
                completed = subprocess.run(
                    args,
                    cwd=output_dir,
                    shell=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=config.timeout_seconds,
                    env=environment,
                )
            except subprocess.TimeoutExpired as exc:
                _write_solver_logs(artifacts, exc.stdout, exc.stderr)
                raise CalculiXStaticError(
                    "solver_execution", "CalculiX execution timed out"
                ) from exc
            _write_solver_logs(artifacts, completed.stdout, completed.stderr)
            stage = "solver_execution"
            result["invocation"]["return_code"] = completed.returncode
            combined = completed.stdout + "\n" + completed.stderr
            version = re.search(r"\bCalculiX\s+Version\s+(\d+\.\d+)\b", combined)
            result["solver_version"] = version[1] if version else None
            for extension in ("dat", "frd", "sta", "cvg"):
                artifacts[extension] = output_dir / f"{config.case_name}.{extension}"
            _validate_completion(
                completed.returncode,
                combined,
                artifacts["sta"],
                result["solver_version"],
                config.target_version,
            )
            checks["solver_completed"] = True
            stage = "result_parsing"
            parsed = parse_calculix_dat(
                artifacts["dat"],
                volume_node_ids=volume_nodes,
                fixed_node_ids=set(fixed),
                volume_element_ids={e.element_id for e in mesh.tetrahedra},
            )
            validate_calculix_frd(artifacts["frd"])
            stage = "physics_validation"
            numerical, physics_checks = _physics_results(parsed, mesh, fixed, loaded, config)
            checks.update(physics_checks)
            result["diagnostics"] = numerical["diagnostics"]
            if not all(checks.values()):
                failed = ", ".join(name for name, passed in checks.items() if not passed)
                raise CalculiXStaticError("physics_validation", f"sanity checks failed: {failed}")
            result.update(numerical)
            result["solver_status"] = "succeeded"
            _write_result(result_path, result)
        except (
            CalculiXStaticError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            OverflowError,
        ) as exc:
            failure_stage = exc.stage if isinstance(exc, CalculiXStaticError) else stage
            reason = exc.message if isinstance(exc, CalculiXStaticError) else str(exc)
            if failure_stage == "solver_execution":
                checks["solver_completed"] = False
            result.update(
                solver_status="failed", failure_stage=failure_stage, failure_reason=reason
            )
            try:
                _write_result(result_path, result)
            except OSError as write_error:
                raise CalculiXStaticError(
                    failure_stage, f"{reason}; cannot write failure JSON: {write_error}"
                ) from exc
            raise CalculiXStaticError(failure_stage, reason, result_path) from exc
        return {name: path for name, path in artifacts.items() if path.is_file()}


def _write_result(path: Path, result: dict) -> None:
    path.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def _write_solver_logs(artifacts: dict[str, Path], stdout, stderr) -> None:
    for key, value in (("stdout", stdout), ("stderr", stderr)):
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        artifacts[key].write_text(value or "", encoding="utf-8")


def _mesh_provenance(mesh_path: Path, manifest_path: Path, mesh: GmshMesh) -> tuple[dict, dict]:
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8"),
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite manifest value: {value}")
        ),
    )
    if not isinstance(manifest, dict):
        raise CalculiXStaticError("mesh_validation", "mesh manifest must be an object")
    # JSON exponents such as 1e999 overflow to Inf without calling parse_constant.
    # Reject them before any manifest fields can contaminate a failure artifact.
    json.dumps(manifest, allow_nan=False)
    expected = {
        "backend": "gmsh",
        "dimension": 3,
        "element_order": 1,
        "node_count": len(mesh.nodes),
        "volume_element_count": len(mesh.tetrahedra),
        "mesh_file": mesh_path.name,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise CalculiXStaticError("mesh_validation", f"mesh manifest {key} mismatch")
    geometry = manifest["source_geometry_fingerprint"]
    if not isinstance(geometry, dict) or not geometry:
        raise CalculiXStaticError("mesh_validation", "missing geometry fingerprint")
    keys = (
        "backend",
        "gmsh_version",
        "invocation_method",
        "dimension",
        "element_order",
        "node_count",
        "element_count",
        "volume_element_count",
        "volume_entity_count",
        "element_types",
        "meshing_parameters",
    )
    identity = {key: manifest[key] for key in keys}
    identity["mesh_sha256"] = hashlib.sha256(mesh_path.read_bytes()).hexdigest()
    # Filesystem locations are recorded separately; they are not mesh identity.
    return geometry, identity


def _validate_completion(
    returncode: int, log: str, sta_path: Path, version: str | None, target_version: str
) -> None:
    if returncode != 0:
        raise CalculiXStaticError(
            "solver_execution", f"CalculiX exit code {returncode}; see ccx logs"
        )
    fatal = re.search(
        r"singular|non[- ]convergence|no convergence|not converg|\*ERROR|"
        r"(?<![a-z])(?:nan|[+-]?inf(?:inity)?)(?![a-z])",
        log,
        re.IGNORECASE,
    )
    if fatal:
        raise CalculiXStaticError("solver_execution", f"CalculiX reported {fatal[0]}; see ccx logs")
    if version != target_version:
        raise CalculiXStaticError(
            "solver_execution", f"expected CalculiX {target_version}, got {version}"
        )
    if "Job finished" not in log:
        raise CalculiXStaticError("solver_execution", "CalculiX did not report Job finished")
    if not sta_path.is_file():
        raise CalculiXStaticError("solver_execution", "CalculiX STA status file missing")
    records = [
        line.split()
        for line in sta_path.read_text(encoding="ascii").splitlines()
        if re.match(r"^\s*\d+\s+\d+\s", line)
    ]
    if (
        not records
        or len(records[-1]) != 7
        or records[-1][0] != "1"
        or float(records[-1][4]) != 1.0
        or float(records[-1][5]) != 1.0
    ):
        raise CalculiXStaticError("solver_execution", "CalculiX did not reach final time 1 in STA")


def _physics_results(
    parsed: CalculiXParsedResults,
    mesh: GmshMesh,
    fixed: tuple[int, ...],
    loaded: tuple[int, ...],
    config: CalculiXStaticConfig,
) -> tuple[dict, dict[str, bool]]:
    displacement, stress = parsed.max_displacement, parsed.max_von_mises
    reaction = tuple(math.fsum(v[i] for v in parsed.reaction_forces.values()) for i in range(3))
    residual = math.hypot(*(reaction[i] + config.total_load_n[i] for i in range(3)))
    tolerance = max(1e-6, 1e-6 * math.hypot(*config.total_load_n))
    fixed_maximum = max(math.hypot(*parsed.displacements[n]) for n in fixed)
    average_uz = math.fsum(parsed.displacements[n][2] for n in loaded) / len(loaded)
    checks = {
        "results_finite": all(
            math.isfinite(v)
            for v in (
                displacement.value,
                stress.value,
                *reaction,
                residual,
                fixed_maximum,
                average_uz,
            )
        ),
        "fixed_displacement_near_zero": fixed_maximum <= 1e-9,
        "loaded_region_average_uz_negative": average_uz < 0,
        "reaction_equilibrium": residual <= tolerance,
        "max_displacement_node_valid": displacement.node_id in mesh.nodes,
        "max_stress_element_valid": stress.element_id in {e.element_id for e in mesh.tetrahedra},
    }
    return {
        "max_displacement": asdict(displacement) if math.isfinite(displacement.value) else None,
        "max_von_mises_stress": asdict(stress) if math.isfinite(stress.value) else None,
        "reaction_force_n": list(reaction) if all(map(math.isfinite, reaction)) else None,
        "equilibrium_residual_n": residual if math.isfinite(residual) else None,
        "diagnostics": {
            "equilibrium_tolerance_n": tolerance,
            "equilibrium_residual_n": residual if math.isfinite(residual) else None,
            "fixed_max_displacement_mm": fixed_maximum if math.isfinite(fixed_maximum) else None,
            "fixed_displacement_tolerance_mm": 1e-9,
            "loaded_region_average_uz_mm": average_uz if math.isfinite(average_uz) else None,
            "stress_source": "DAT integration-point tensor; not FRD nodal stress",
        },
    }, checks


def load_calculix_static_config(config_path: Path) -> CalculiXStaticConfig:
    """Load and validate the Benchmark v1 CalculiX analysis definition."""

    import yaml

    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    solver = raw["solver"]
    analysis = raw["analysis"]
    units = raw["units"]
    material = raw["material"]
    boundary = raw["boundary_condition"]
    load = raw["load"]
    if solver["backend"] != "calculix":
        raise ValueError("solver backend must be 'calculix'")
    if analysis["type"] != "linear_static":
        raise ValueError("analysis type must be 'linear_static'")
    if analysis["element_type"] != "C3D4":
        raise ValueError("CalculiXStaticSolver requires C3D4 elements")
    if analysis["geometric_nonlinearity"]:
        raise ValueError("Benchmark v1 requires geometric_nonlinearity=false")
    if boundary["node_set"] != "FIXED_NODES" or load["node_set"] != "LOAD_NODES":
        raise ValueError("node sets must be FIXED_NODES and LOAD_NODES")
    if load["distribution"] != "equal_equivalent_nodal_loads":
        raise ValueError("only equal_equivalent_nodal_loads is supported")
    config = CalculiXStaticConfig(
        target_version=str(solver["target_version"]),
        case_name=str(solver["case_name"]),
        timeout_seconds=int(solver["timeout_seconds"]),
        element_type=str(analysis["element_type"]),
        geometric_nonlinearity=bool(analysis["geometric_nonlinearity"]),
        units={str(key): str(value) for key, value in units.items()},
        material_name=str(material["name"]),
        youngs_modulus_mpa=float(material["youngs_modulus_mpa"]),
        poissons_ratio=float(material["poissons_ratio"]),
        material_scope=str(material["scope"]),
        fixed_x_mm=float(boundary["fixed_x_mm"]),
        coordinate_tolerance_mm=float(boundary["coordinate_tolerance_mm"]),
        constrained_dofs=tuple(int(value) for value in boundary["constrained_dofs"]),
        load_x_range_mm=tuple(float(value) for value in load["x_range_mm"]),
        load_y_range_mm=tuple(float(value) for value in load["y_range_mm"]),
        load_z_mm=float(load["z_mm"]),
        total_load_n=tuple(float(value) for value in load["total_force_n"]),
    )
    _validate_config(config)
    return config


def _validate_config(config: CalculiXStaticConfig) -> None:
    if config.target_version != "2.22":
        raise ValueError("this backend requires CalculiX 2.22")
    if config.element_type != "C3D4" or config.geometric_nonlinearity:
        raise ValueError("this backend requires C3D4 linear static analysis")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", config.case_name):
        raise ValueError("case_name must be a plain ASCII identifier, not a path")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", config.material_name):
        raise ValueError("material_name must be a plain ASCII identifier")
    numbers = (
        config.timeout_seconds,
        config.youngs_modulus_mpa,
        config.poissons_ratio,
        config.fixed_x_mm,
        config.coordinate_tolerance_mm,
        config.load_z_mm,
        *config.load_x_range_mm,
        *config.load_y_range_mm,
        *config.total_load_n,
    )
    if not all(math.isfinite(value) for value in numbers):
        raise ValueError("config contains NaN or Inf")
    if config.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if config.youngs_modulus_mpa <= 0:
        raise ValueError("youngs_modulus_mpa must be positive")
    if not -1.0 < config.poissons_ratio < 0.5:
        raise ValueError("poissons_ratio must be between -1 and 0.5")
    if config.coordinate_tolerance_mm <= 0:
        raise ValueError("coordinate_tolerance_mm must be positive")
    if config.constrained_dofs != (1, 2, 3):
        raise ValueError("fixed rear face must constrain DOFs 1, 2, and 3")
    if len(config.load_x_range_mm) != 2 or config.load_x_range_mm[0] > config.load_x_range_mm[1]:
        raise ValueError("load x range is invalid")
    if len(config.load_y_range_mm) != 2 or config.load_y_range_mm[0] > config.load_y_range_mm[1]:
        raise ValueError("load y range is invalid")
    if config.total_load_n != (0.0, 0.0, -150.0):
        raise ValueError("Benchmark v1 total load must be (0, 0, -150) N")
    if config.units != {"length": "mm", "force": "N", "stress": "MPa"}:
        raise ValueError("Benchmark v1 units must be mm, N, and MPa")


def parse_gmsh_msh(mesh_path: Path) -> GmshMesh:
    """Parse the nodes, boundary-surface nodes, and C3D4 volumes from MSH 4.1 ASCII."""

    mesh_path = Path(mesh_path)
    if not mesh_path.is_file():
        raise CalculiXStaticError("mesh_validation", "Gmsh mesh does not exist")
    try:
        lines = mesh_path.read_text(encoding="utf-8").splitlines()
        mesh_format = _section(lines, "$MeshFormat", "$EndMeshFormat")
        if not mesh_format or mesh_format[0].split()[:2] != ["4.1", "0"]:
            raise CalculiXStaticError("mesh_validation", "Gmsh mesh must use MSH 4.1 ASCII format")
        nodes = _parse_nodes(_section(lines, "$Nodes", "$EndNodes"))
        surface_node_ids, tetrahedra = _parse_elements(_section(lines, "$Elements", "$EndElements"))
        validate_tetrahedra(nodes, tetrahedra)
        if not surface_node_ids <= nodes.keys():
            raise CalculiXStaticError("mesh_validation", "surface references missing node")
    except CalculiXStaticError:
        raise
    except (
        OSError,
        UnicodeDecodeError,
        ValueError,
        IndexError,
        StopIteration,
        RuntimeError,
    ) as exc:
        raise CalculiXStaticError("mesh_validation", f"invalid Gmsh mesh: {exc}") from exc
    return GmshMesh(
        nodes=nodes,
        surface_node_ids=frozenset(surface_node_ids),
        tetrahedra=tuple(tetrahedra),
    )


def validate_tetrahedra(
    nodes: dict[int, tuple[float, float, float]],
    tetrahedra: Iterable[Tetrahedron],
) -> None:
    """Reject malformed, dangling, repeated-node, or nonpositive-volume tetrahedra."""

    tetrahedra = tuple(tetrahedra)
    if not nodes:
        raise CalculiXStaticError("mesh_validation", "mesh contains no nodes")
    if not tetrahedra:
        raise CalculiXStaticError("mesh_validation", "mesh contains no C3D4 tetrahedra")
    seen_elements: set[int] = set()
    if any(node_id <= 0 for node_id in nodes):
        raise CalculiXStaticError("mesh_validation", "node IDs must be positive")
    for element in tetrahedra:
        if element.element_id <= 0:
            raise CalculiXStaticError("mesh_validation", "element IDs must be positive")
        if element.element_id in seen_elements:
            raise CalculiXStaticError(
                "mesh_validation", f"duplicate element ID {element.element_id}"
            )
        seen_elements.add(element.element_id)
        if len(element.node_ids) != 4:
            raise CalculiXStaticError(
                "mesh_validation",
                f"tetrahedron {element.element_id} must reference exactly four nodes",
            )
        if len(set(element.node_ids)) != 4:
            raise CalculiXStaticError(
                "mesh_validation", f"tetrahedron {element.element_id} repeats a node"
            )
        for node_id in element.node_ids:
            if node_id not in nodes:
                raise CalculiXStaticError(
                    "mesh_validation",
                    f"tetrahedron {element.element_id} references missing node {node_id}",
                )
        volume = _signed_tetrahedron_volume(*(nodes[node_id] for node_id in element.node_ids))
        if not math.isfinite(volume) or volume <= 0.0:
            raise CalculiXStaticError(
                "mesh_validation",
                f"tetrahedron {element.element_id} must have positive volume; got {volume}",
            )


def select_fixed_nodes(mesh: GmshMesh, config: CalculiXStaticConfig) -> tuple[int, ...]:
    """Select the rear boundary face by coordinates, never by fixed node IDs."""

    selected = tuple(
        sorted(
            node_id
            for node_id in mesh.surface_node_ids
            if abs(mesh.nodes[node_id][0] - config.fixed_x_mm) <= config.coordinate_tolerance_mm
        )
    )
    if not selected:
        raise CalculiXStaticError("boundary_selection", "FIXED_NODES is empty")
    if not _contains_noncollinear_points([mesh.nodes[node_id] for node_id in selected]):
        raise CalculiXStaticError(
            "boundary_selection", "FIXED_NODES must contain rear-face nodes that are not collinear"
        )
    return selected


def select_load_nodes(
    mesh: GmshMesh,
    config: CalculiXStaticConfig,
    *,
    fixed_node_ids: Iterable[int],
) -> tuple[int, ...]:
    """Select the top distal load pad from boundary nodes using frozen geometry."""

    tolerance = config.coordinate_tolerance_mm
    xmin, xmax = config.load_x_range_mm
    ymin, ymax = config.load_y_range_mm
    selected = tuple(
        sorted(
            node_id
            for node_id in mesh.surface_node_ids
            if xmin - tolerance <= mesh.nodes[node_id][0] <= xmax + tolerance
            and ymin - tolerance <= mesh.nodes[node_id][1] <= ymax + tolerance
            and abs(mesh.nodes[node_id][2] - config.load_z_mm) <= tolerance
        )
    )
    if not selected:
        raise CalculiXStaticError("boundary_selection", "LOAD_NODES is empty")
    if set(selected).intersection(fixed_node_ids):
        raise CalculiXStaticError(
            "boundary_selection", "FIXED_NODES and LOAD_NODES must be disjoint"
        )
    return selected


def equivalent_nodal_loads(
    node_ids: Iterable[int],
    total_load_n: tuple[float, float, float],
) -> dict[int, tuple[float, float, float]]:
    """Distribute a total force equally and preserve the requested resultant."""

    node_ids = tuple(node_ids)
    if not node_ids:
        raise CalculiXStaticError("boundary_selection", "LOAD_NODES is empty")
    if len(set(node_ids)) != len(node_ids):
        raise CalculiXStaticError("boundary_selection", "LOAD_NODES contains duplicates")
    if not all(math.isfinite(value) for value in total_load_n):
        raise CalculiXStaticError("input_generation", "total load contains non-finite values")
    count = len(node_ids)
    per_node = tuple(component / count for component in total_load_n)
    return {node_id: per_node for node_id in sorted(node_ids)}


def von_mises_stress(
    sxx: float,
    syy: float,
    szz: float,
    sxy: float,
    syz: float,
    szx: float,
) -> float:
    """Calculate 3D von Mises stress from six tensor components."""

    components = (sxx, syy, szz, sxy, syz, szx)
    if not all(math.isfinite(value) for value in components):
        raise CalculiXStaticError("result_parsing", "stress contains NaN or Inf")
    squared = 0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
    squared += 3.0 * (sxy**2 + syz**2 + szx**2)
    return math.sqrt(max(0.0, squared))


def analysis_definition(config: CalculiXStaticConfig) -> dict[str, object]:
    """Return the path-independent analysis identity inputs."""

    return {
        "analysis_type": "linear_static",
        "element_type": config.element_type,
        "geometric_nonlinearity": config.geometric_nonlinearity,
        "solver_settings": {
            "target_version": config.target_version,
            "num_threads": 1,
            "static_step": [1.0, 1.0, 1e-5, 1.0],
            "dat_outputs": ["U:ALL_NODES", "RF:FIXED_NODES", "S:VOLUME_ELEMENTS"],
            "stress_position": "integration_point",
        },
        "material": {
            "name": config.material_name,
            "youngs_modulus_mpa": config.youngs_modulus_mpa,
            "poissons_ratio": config.poissons_ratio,
            "scope": config.material_scope,
        },
        "boundary_condition": {
            "type": "fixed_rear_face",
            "fixed_x_mm": config.fixed_x_mm,
            "coordinate_tolerance_mm": config.coordinate_tolerance_mm,
            "constrained_dofs": list(config.constrained_dofs),
        },
        "load": {
            "type": "equal_equivalent_nodal_loads",
            "x_range_mm": list(config.load_x_range_mm),
            "y_range_mm": list(config.load_y_range_mm),
            "z_mm": config.load_z_mm,
            "total_force_n": list(config.total_load_n),
        },
        "units": {**config.units, "displacement": "mm"},
    }


def analysis_fingerprint(config: CalculiXStaticConfig) -> str:
    """Hash all material, element, boundary, load, unit, and analysis settings."""

    encoded = json.dumps(
        analysis_definition(config),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_failure_result(
    output_dir: Path,
    *,
    config: CalculiXStaticConfig,
    stage: str,
    reason: str,
    geometry_fingerprint: dict[str, object] | None,
    mesh_provenance: dict[str, object] | None,
    invocation_method: str | None,
    solver_version: str | None,
    calculix_input_sha256: str | None,
    sanity_checks: dict[str, bool] | None = None,
) -> Path:
    """Persist an explicit failed physics result without fabricated numerical values."""

    if stage not in FAILURE_STAGES:
        raise ValueError(f"unsupported failure stage: {stage}")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "physics_result.json"
    result = {
        "solver": "calculix",
        "solver_version": solver_version,
        "invocation_method": invocation_method,
        "solver_status": "failed",
        "failure_stage": stage,
        "failure_reason": reason,
        "units": dict(config.units),
        "input_geometry_fingerprint": geometry_fingerprint,
        "mesh_provenance": mesh_provenance,
        "boundary_condition": analysis_definition(config)["boundary_condition"],
        "load": analysis_definition(config)["load"],
        "analysis_definition": analysis_definition(config),
        "analysis_fingerprint": analysis_fingerprint(config),
        "calculix_input_sha256": calculix_input_sha256,
        "max_displacement": None,
        "max_von_mises_stress": None,
        "reaction_force_n": None,
        "sanity_checks": sanity_checks or {},
    }
    content = json.dumps(result, allow_nan=False, indent=2, sort_keys=True) + "\n"
    with result_path.open("x", encoding="utf-8") as stream:
        stream.write(content)
    return result_path


def write_calculix_input(
    output_dir: Path,
    *,
    mesh: GmshMesh,
    config: CalculiXStaticConfig,
    fixed_node_ids: Iterable[int],
    nodal_loads: dict[int, tuple[float, float, float]],
) -> tuple[Path, str]:
    """Write a deterministic CalculiX input deck and return its SHA-256."""

    try:
        _validate_config(config)
    except ValueError as exc:
        raise CalculiXStaticError("input_generation", str(exc)) from exc
    fixed_node_ids = tuple(sorted(set(fixed_node_ids)))
    load_node_ids = tuple(sorted(nodal_loads))
    if not fixed_node_ids or not load_node_ids:
        raise CalculiXStaticError("input_generation", "required node sets are empty")
    if set(fixed_node_ids).intersection(load_node_ids):
        raise CalculiXStaticError("input_generation", "FIXED_NODES and LOAD_NODES must be disjoint")
    validate_tetrahedra(mesh.nodes, mesh.tetrahedra)
    for node_id in (*fixed_node_ids, *load_node_ids):
        if node_id not in mesh.nodes:
            raise CalculiXStaticError(
                "input_generation", f"node set references missing node {node_id}"
            )

    lines = [
        "*HEADING",
        "Benchmark Bracket v1 deterministic CalculiX linear static analysis",
        "*NODE",
    ]
    for node_id, coordinates in sorted(mesh.nodes.items()):
        lines.append(f"{node_id}, " + ", ".join(_format_float(value) for value in coordinates))
    lines.append(f"*ELEMENT, TYPE={config.element_type}, ELSET=VOLUME_ELEMENTS")
    for element in sorted(mesh.tetrahedra, key=lambda item: item.element_id):
        lines.append(
            f"{element.element_id}, " + ", ".join(str(value) for value in element.node_ids)
        )
    lines.extend(["*NSET, NSET=ALL_NODES", *_format_id_set(sorted(mesh.nodes))])
    lines.extend(["*NSET, NSET=FIXED_NODES", *_format_id_set(fixed_node_ids)])
    lines.extend(["*NSET, NSET=LOAD_NODES", *_format_id_set(load_node_ids)])
    lines.extend(
        [
            f"*MATERIAL, NAME={config.material_name}",
            "*ELASTIC",
            f"{_format_float(config.youngs_modulus_mpa)}, {_format_float(config.poissons_ratio)}",
            f"*SOLID SECTION, ELSET=VOLUME_ELEMENTS, MATERIAL={config.material_name}",
            "*STEP, NLGEOM=NO",
            "*STATIC",
            "1, 1, 1e-05, 1",
            "*BOUNDARY",
            "FIXED_NODES, 1, 3, 0",
            "*CLOAD",
        ]
    )
    for node_id, load in sorted(nodal_loads.items()):
        for dof, component in enumerate(load, start=1):
            if component != 0.0:
                lines.append(f"{node_id}, {dof}, {_format_float(component)}")
    lines.extend(
        [
            "*NODE PRINT, NSET=ALL_NODES",
            "U",
            "*NODE PRINT, NSET=FIXED_NODES",
            "RF",
            "*EL PRINT, ELSET=VOLUME_ELEMENTS",
            "S",
            "*NODE FILE, NSET=ALL_NODES",
            "U, RF",
            "*EL FILE",
            "S",
            "*END STEP",
        ]
    )
    content = "\n".join(lines) + "\n"
    try:
        encoded = content.encode("ascii")
    except UnicodeEncodeError as exc:
        raise CalculiXStaticError(
            "input_generation", "CalculiX input contains non-ASCII text"
        ) from exc
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = output_dir / f"{config.case_name}.inp"
    input_path.write_bytes(encoded)
    return input_path, hashlib.sha256(encoded).hexdigest()


def parse_calculix_dat(
    dat_path: Path,
    *,
    volume_node_ids: set[int],
    fixed_node_ids: set[int],
    volume_element_ids: set[int],
) -> CalculiXParsedResults:
    """Parse the final observed CalculiX 2.22 DAT displacement, force, and stress tables."""

    try:
        return _parse_calculix_dat(
            dat_path,
            volume_node_ids=volume_node_ids,
            fixed_node_ids=fixed_node_ids,
            volume_element_ids=volume_element_ids,
        )
    except (ValueError, OSError, OverflowError) as exc:
        raise CalculiXStaticError("result_parsing", f"invalid CalculiX DAT: {exc}") from exc


def _parse_calculix_dat(
    dat_path: Path,
    *,
    volume_node_ids: set[int],
    fixed_node_ids: set[int],
    volume_element_ids: set[int],
) -> CalculiXParsedResults:

    dat_path = Path(dat_path)
    if not dat_path.is_file() or dat_path.stat().st_size == 0:
        raise CalculiXStaticError(
            "result_parsing", "missing displacement output: DAT missing or empty"
        )
    try:
        lines = dat_path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise CalculiXStaticError("result_parsing", f"cannot read CalculiX DAT: {exc}") from exc
    displacement_rows = _last_dat_table(
        lines,
        "displacements (vx,vy,vz) for set ALL_NODES",
        column_count=4,
    )
    displacements: dict[int, tuple[float, float, float]] = {}
    for row in displacement_rows:
        node_id = int(row[0])
        if node_id in displacements:
            raise CalculiXStaticError(
                "result_parsing", f"duplicate displacement row for node {node_id}"
            )
        displacements[node_id] = tuple(float(value) for value in row[1:4])
        if not all(math.isfinite(v) for v in displacements[node_id]):
            raise CalculiXStaticError("result_parsing", "CalculiX DAT contains NaN or Inf")
        if node_id not in volume_node_ids:
            raise CalculiXStaticError("result_parsing", f"unknown node {node_id}")
    _require_exact_ids("displacements for nodes", volume_node_ids, set(displacements))

    reaction_rows = _last_dat_table(lines, "forces (fx,fy,fz) for set FIXED_NODES", column_count=4)

    reaction_forces: dict[int, tuple[float, float, float]] = {}
    for row in reaction_rows:
        node_id = int(row[0])
        if node_id in reaction_forces:
            raise CalculiXStaticError(
                "result_parsing", f"duplicate reaction row for node {node_id}"
            )
        reaction_forces[node_id] = tuple(float(value) for value in row[1:4])

    stress_rows = _last_dat_table(
        lines,
        "stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set VOLUME_ELEMENTS",
        column_count=8,
    )
    stresses: list[IntegrationPointStress] = []
    seen_stresses: set[int] = set()
    for row in stress_rows:
        element_id = int(row[0])
        integration_point = int(row[1])
        if element_id in seen_stresses or integration_point != 1:
            raise CalculiXStaticError(
                "result_parsing", "C3D4 requires exactly one stress row at integration point 1"
            )
        seen_stresses.add(element_id)
        raw_components = tuple(float(value) for value in row[2:8])
        sxx, syy, szz, sxy, sxz, syz = raw_components
        stresses.append(
            IntegrationPointStress(
                element_id=element_id,
                integration_point=integration_point,
                components=(sxx, syy, szz, sxy, syz, sxz),
            )
        )

    _require_exact_ids("displacements for nodes", volume_node_ids, set(displacements))
    _require_exact_ids("reactions for nodes", fixed_node_ids, set(reaction_forces))
    _require_exact_ids(
        "stresses for elements",
        volume_element_ids,
        {stress.element_id for stress in stresses},
    )
    numeric_values = [
        value for values in (*displacements.values(), *reaction_forces.values()) for value in values
    ]
    numeric_values.extend(value for stress in stresses for value in stress.components)
    if not all(math.isfinite(value) for value in numeric_values):
        raise CalculiXStaticError("result_parsing", "CalculiX DAT contains NaN or Inf")
    return CalculiXParsedResults(
        displacements=displacements,
        reaction_forces=reaction_forces,
        integration_point_stresses=tuple(stresses),
    )


def validate_calculix_frd(frd_path: Path) -> None:
    """Require the DISP, STRESS, and FORC datasets requested from CalculiX."""

    frd_path = Path(frd_path)
    if not frd_path.is_file() or frd_path.stat().st_size == 0:
        raise CalculiXStaticError("result_parsing", "CalculiX FRD output is missing or empty")
    try:
        content = frd_path.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise CalculiXStaticError("result_parsing", f"cannot read CalculiX FRD: {exc}") from exc
    datasets = set(re.findall(r"(?m)^\s*-4\s+(DISP|STRESS|FORC)\b", content))
    missing = sorted({"DISP", "STRESS", "FORC"} - datasets)
    if missing:
        raise CalculiXStaticError(
            "result_parsing", f"CalculiX FRD is missing datasets: {', '.join(missing)}"
        )
    if re.search(r"(?i)(?<![a-z])(?:nan|[+-]?inf(?:inity)?)(?![a-z])", content):
        raise CalculiXStaticError("result_parsing", "CalculiX FRD contains NaN or Inf")


def discover_calculix_executable(explicit: Path | None = None) -> tuple[Path, str]:
    """Resolve an injected executable, CALCULIX_CCX, or ccx on PATH."""
    if explicit is not None:
        candidate, source = str(explicit), "explicit_path"
    elif os.environ.get("CALCULIX_CCX"):
        candidate, source = os.environ["CALCULIX_CCX"], "environment"
    else:
        candidate, source = shutil.which("ccx"), "path"
    if not candidate or not Path(candidate).is_file():
        raise CalculiXStaticError(
            "solver_invocation",
            "CalculiX executable unavailable; set CALCULIX_CCX or provide ccx on PATH",
        )
    return Path(candidate).resolve(), source


def _last_dat_table(
    lines: list[str],
    heading: str,
    *,
    column_count: int,
) -> list[list[str]]:
    heading_indexes = [
        index for index, line in enumerate(lines) if line.strip().startswith(heading)
    ]
    if not heading_indexes:
        raise CalculiXStaticError("result_parsing", f"CalculiX DAT is missing table: {heading}")
    time_match = re.fullmatch(
        re.escape(heading) + r"\s+and time\s+(\S+)\s*", lines[heading_indexes[-1]].strip()
    )
    if not time_match or float(time_match[1]) != 1.0:
        raise CalculiXStaticError("result_parsing", f"DAT table not at final time 1: {heading}")
    rows: list[list[str]] = []
    started = False
    for line in lines[heading_indexes[-1] + 1 :]:
        stripped = line.strip()
        if not stripped:
            if started:
                break
            continue
        started = True
        columns = stripped.split()
        if len(columns) != column_count:
            raise CalculiXStaticError(
                "result_parsing",
                f"unexpected DAT row in {heading}: {stripped}",
            )
        rows.append(columns)
    if not rows:
        raise CalculiXStaticError("result_parsing", f"CalculiX DAT table is empty: {heading}")
    return rows


def _require_exact_ids(label: str, expected: set[int], actual: set[int]) -> None:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        raise CalculiXStaticError("result_parsing", f"missing {label} {missing}")
    if extra:
        raise CalculiXStaticError("result_parsing", f"unexpected {label} {extra}")


def _format_id_set(node_ids: Iterable[int], *, per_line: int = 16) -> list[str]:
    node_ids = tuple(node_ids)
    return [
        ", ".join(str(value) for value in node_ids[index : index + per_line])
        for index in range(0, len(node_ids), per_line)
    ]


def _format_float(value: float) -> str:
    value = float(value)
    if not math.isfinite(value):
        raise CalculiXStaticError("input_generation", "input contains NaN or Inf")
    if value == 0.0:
        return "0"
    return format(value, ".12g")


def _contains_noncollinear_points(points: list[tuple[float, float, float]]) -> bool:
    if len(points) < 3:
        return False
    first = points[0]
    tolerance_squared = 1e-24
    for second_index in range(1, len(points) - 1):
        second = points[second_index]
        ax, ay, az = (second[index] - first[index] for index in range(3))
        for third in points[second_index + 1 :]:
            bx, by, bz = (third[index] - first[index] for index in range(3))
            cross = (
                ay * bz - az * by,
                az * bx - ax * bz,
                ax * by - ay * bx,
            )
            if sum(value * value for value in cross) > tolerance_squared:
                return True
    return False


def _section(lines: list[str], start: str, end: str) -> list[str]:
    try:
        start_index = lines.index(start)
        end_index = lines.index(end, start_index + 1)
    except ValueError as exc:
        raise CalculiXStaticError(
            "mesh_validation", f"Gmsh mesh is missing section {start}"
        ) from exc
    return [line.strip() for line in lines[start_index + 1 : end_index] if line.strip()]


def _parse_nodes(lines: list[str]) -> dict[int, tuple[float, float, float]]:
    tokens = iter(" ".join(lines).split())
    block_count = int(next(tokens))
    expected_node_count = int(next(tokens))
    next(tokens)
    next(tokens)
    nodes: dict[int, tuple[float, float, float]] = {}
    for _ in range(block_count):
        entity_dimension = int(next(tokens))
        next(tokens)
        parametric = int(next(tokens))
        block_node_count = int(next(tokens))
        node_ids = [int(next(tokens)) for _ in range(block_node_count)]
        for node_id in node_ids:
            if node_id in nodes:
                raise CalculiXStaticError("mesh_validation", f"duplicate node ID {node_id}")
            coordinates = tuple(float(next(tokens)) for _ in range(3))
            if not all(math.isfinite(value) for value in coordinates):
                raise CalculiXStaticError(
                    "mesh_validation", f"node {node_id} has non-finite coordinates"
                )
            nodes[node_id] = coordinates
            if parametric:
                for _ in range(entity_dimension):
                    next(tokens)
    if len(nodes) != expected_node_count:
        raise CalculiXStaticError(
            "mesh_validation",
            f"Gmsh node count mismatch: expected {expected_node_count}, parsed {len(nodes)}",
        )
    _ensure_consumed(tokens, "node")
    return nodes


def _parse_elements(lines: list[str]) -> tuple[set[int], list[Tetrahedron]]:
    tokens = iter(" ".join(lines).split())
    block_count = int(next(tokens))
    expected_element_count = int(next(tokens))
    next(tokens)
    next(tokens)
    parsed_element_count = 0
    seen_element_ids: set[int] = set()
    surface_node_ids: set[int] = set()
    tetrahedra: list[Tetrahedron] = []
    nodes_per_element = {15: 1, 1: 2, 2: 3, 3: 4, 4: 4}
    for _ in range(block_count):
        entity_dimension = int(next(tokens))
        next(tokens)
        element_type = int(next(tokens))
        block_element_count = int(next(tokens))
        if entity_dimension == 3 and element_type != 4:
            raise CalculiXStaticError(
                "mesh_validation",
                f"unsupported Gmsh volume element type {element_type}; expected type 4",
            )
        if element_type not in nodes_per_element:
            raise CalculiXStaticError(
                "mesh_validation", f"unsupported Gmsh element type {element_type}"
            )
        if entity_dimension != {15: 0, 1: 1, 2: 2, 3: 2, 4: 3}[element_type]:
            raise CalculiXStaticError("mesh_validation", "element type/entity dimension mismatch")
        connectivity_size = nodes_per_element[element_type]
        for _ in range(block_element_count):
            element_id = int(next(tokens))
            if element_id <= 0:
                raise CalculiXStaticError("mesh_validation", "element IDs must be positive")
            if element_id in seen_element_ids:
                raise CalculiXStaticError("mesh_validation", f"duplicate element ID {element_id}")
            seen_element_ids.add(element_id)
            node_ids = tuple(int(next(tokens)) for _ in range(connectivity_size))
            parsed_element_count += 1
            if entity_dimension == 2:
                surface_node_ids.update(node_ids)
            elif entity_dimension == 3:
                tetrahedra.append(Tetrahedron(element_id, node_ids))
    if parsed_element_count != expected_element_count:
        raise CalculiXStaticError(
            "mesh_validation",
            "Gmsh element count mismatch: "
            f"expected {expected_element_count}, parsed {parsed_element_count}",
        )
    _ensure_consumed(tokens, "element")
    return surface_node_ids, tetrahedra


def _ensure_consumed(tokens: Iterable[str], record_type: str) -> None:
    if next(iter(tokens), None) is not None:
        raise CalculiXStaticError(
            "mesh_validation", f"unexpected trailing {record_type} section data"
        )


def _signed_tetrahedron_volume(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    third: tuple[float, float, float],
    fourth: tuple[float, float, float],
) -> float:
    ax, ay, az = (second[index] - first[index] for index in range(3))
    bx, by, bz = (third[index] - first[index] for index in range(3))
    cx, cy, cz = (fourth[index] - first[index] for index in range(3))
    determinant = ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    return determinant / 6.0
