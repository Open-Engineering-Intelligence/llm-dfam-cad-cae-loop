"""Optional real FreeCAD -> Gmsh -> CalculiX evidence, with immutable run directories.

Set FREECAD_CMD and CALCULIX_CCX if the tools are not on PATH. Set
CALCULIX_TEST_OUTPUT_ROOT to a new directory to retain an explicitly located run.
"""

import importlib.util
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from open_engineering_intelligence.cae.calculix_solver import (
    CalculiXStaticError,
    CalculiXStaticSolver,
    discover_calculix_executable,
    load_calculix_static_config,
)
from open_engineering_intelligence.cae.gmsh_mesher import GmshMesher, load_gmsh_meshing_config


def _numeric_leaves(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _numeric_leaves(child)
    elif isinstance(value, list):
        for child in value:
            yield from _numeric_leaves(child)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield value


@pytest.mark.integration
def test_reference_freecad_gmsh_calculix_twice(tmp_path: Path) -> None:
    if importlib.util.find_spec("gmsh") is None:
        pytest.skip("Gmsh Python API missing; install the project 'cae' extra")
    freecad = os.environ.get("FREECAD_CMD") or shutil.which("FreeCADCmd")
    if not freecad or not Path(freecad).is_file():
        pytest.skip("FreeCADCmd missing; set FREECAD_CMD or add the existing tool to PATH")
    try:
        executable, _ = discover_calculix_executable()
    except CalculiXStaticError as exc:
        pytest.skip(str(exc))

    root = Path(os.environ.get("CALCULIX_TEST_OUTPUT_ROOT", str(tmp_path / "reference"))).resolve()
    root.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[1]
    solver = CalculiXStaticSolver(
        load_calculix_static_config(repo / "configs/calculix_bracket_v1.yaml"),
        executable=executable,
    )
    results = []
    result_paths = []
    for label in ("first", "repeated"):
        run_dir = root / label
        run_dir.mkdir()
        script = run_dir / "generate_reference.py"
        script.write_text(
            f"""
import json
import sys
from pathlib import Path
sys.path.insert(0, {str(repo / "src")!r})
from open_engineering_intelligence.cad import FreeCADBracketBackend
from open_engineering_intelligence.schemas import DesignParameters
artifacts = FreeCADBracketBackend().generate(
    DesignParameters(thickness_mm=8.0, width_mm=50.0, rib_height_mm=18.0, fillet_radius_mm=2.0),
    Path({str(run_dir / "cad")!r}),
)
print(json.dumps({{key: str(value) for key, value in artifacts.items()}}, sort_keys=True))
""",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [freecad, "-c", str(script)],
            cwd=run_dir,
            shell=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        (run_dir / "freecad.stdout.log").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "freecad.stderr.log").write_text(completed.stderr, encoding="utf-8")
        assert completed.returncode == 0, completed.stderr
        records = [line for line in completed.stdout.splitlines() if line.startswith("{")]
        assert records, completed.stdout + completed.stderr
        cad = json.loads(records[-1])
        mesher = GmshMesher(load_gmsh_meshing_config(repo / "configs/gmsh_bracket_v1.yaml"))
        mesh = mesher.mesh(Path(cad["step"]), Path(cad["manifest"]), run_dir / "mesh")
        artifacts = solver.solve(mesh["mesh"], mesh["manifest"], run_dir / "fea")
        result = json.loads(artifacts["result"].read_text(encoding="utf-8"))
        assert result["solver_status"] == "succeeded"
        assert result["solver_version"] == "2.22"
        assert all(result["sanity_checks"].values())
        assert result["mesh_provenance"]["node_count"] == 594
        assert result["mesh_provenance"]["volume_element_count"] == 1656
        assert result["boundary_condition"]["node_count"] == 121
        assert result["load"]["node_count"] == 23
        assert math.dist(result["load"]["summed_force_n"], [0, 0, -150]) <= 1e-9
        assert result["max_displacement"]["value"] > 0
        assert result["max_von_mises_stress"]["value"] > 0
        assert result["equilibrium_residual_n"] <= 1.5e-4
        for name in ("input", "dat", "frd", "sta", "stdout"):
            assert artifacts[name].stat().st_size > 0
        assert "Job finished" in artifacts["stdout"].read_text()
        # A successful solve must not hide ignored output cards or warnings.
        assert "*WARNING" not in artifacts["stdout"].read_text()
        result_paths.append(str(artifacts["result"]))
        results.append(result)

    first, repeated = results
    identities = (
        "solver_status",
        "solver_version",
        "input_geometry_fingerprint",
        "mesh_provenance",
        "analysis_fingerprint",
        "calculix_input_sha256",
        "boundary_condition",
        "load",
    )
    for key in identities:
        assert first[key] == repeated[key], f"repeat identity mismatch: {key}"
    numerical_keys = (
        "max_displacement",
        "max_von_mises_stress",
        "reaction_force_n",
        "equilibrium_residual_n",
        "diagnostics",
    )
    max_delta = 0.0
    for key in numerical_keys:
        pairs = zip(
            list(_numeric_leaves(first[key])), list(_numeric_leaves(repeated[key])), strict=True
        )
        for a, b in pairs:
            tolerance = max(1e-9, 1e-8 * max(abs(a), abs(b)))
            assert abs(a - b) <= tolerance, (key, a, b, tolerance)
            max_delta = max(max_delta, abs(a - b))
    report = {
        "status": "passed",
        "result_paths": result_paths,
        "identity_fields": list(identities),
        "numerical_fields": list(numerical_keys),
        "tolerance": "abs(a-b) <= max(1e-9, 1e-8 * max(abs(a), abs(b)))",
        "maximum_absolute_difference": max_delta,
    }
    (root / "repeatability.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"CalculiX evidence: {root}")
