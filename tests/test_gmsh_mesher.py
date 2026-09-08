import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _freecadcmd() -> str | None:
    executable = shutil.which("FreeCADCmd") or shutil.which("freecadcmd")
    if executable:
        return executable
    candidate = Path(r"C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe")
    if candidate.exists():
        return str(candidate)
    return None


def _read_mesh_statistics(mesh_path: Path) -> tuple[int, int, int]:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(mesh_path))
        node_count = len(gmsh.model.mesh.getNodes()[0])
        element_types, element_tags, _ = gmsh.model.mesh.getElements()
        element_count = sum(len(tags) for tags in element_tags)
        volume_element_count = sum(
            len(tags)
            for element_type, tags in zip(element_types, element_tags, strict=True)
            if gmsh.model.mesh.getElementProperties(element_type)[1] == 3
        )
        return node_count, element_count, volume_element_count
    finally:
        gmsh.finalize()


def test_gmsh_mesher_rejects_missing_step_with_stage(tmp_path: Path) -> None:
    from open_engineering_intelligence.cae.gmsh_mesher import (
        GmshMesher,
        GmshMeshingError,
        load_gmsh_meshing_config,
    )

    mesher = GmshMesher(load_gmsh_meshing_config(Path("configs/gmsh_bracket_v1.yaml")))

    with pytest.raises(GmshMeshingError) as error:
        mesher.mesh(
            tmp_path / "missing.step",
            tmp_path / "missing_manifest.json",
            tmp_path / "mesh",
        )

    assert error.value.stage == "step_validation"
    assert "STEP artifact does not exist" in str(error.value)


def test_gmsh_meshing_config_is_explicit() -> None:
    from open_engineering_intelligence.cae.gmsh_mesher import load_gmsh_meshing_config

    config = load_gmsh_meshing_config(Path("configs/gmsh_bracket_v1.yaml"))

    assert config.dimension == 3
    assert config.element_order == 1
    assert config.algorithm_2d == 1
    assert config.algorithm_3d == 1
    assert config.characteristic_length_min_mm == 4.0
    assert config.characteristic_length_max_mm == 8.0
    assert config.num_threads == 1
    assert config.random_factor == 1e-9
    assert config.msh_file_version == 4.1
    assert config.binary is False


@pytest.mark.integration
def test_freecad_step_to_gmsh_volume_mesh_is_repeatable(tmp_path: Path) -> None:
    if importlib.util.find_spec("gmsh") is None:
        pytest.skip("Gmsh Python API is not available; install the 'cae' extra")
    freecadcmd = _freecadcmd()
    if freecadcmd is None:
        pytest.skip("FreeCADCmd is not available")

    from open_engineering_intelligence.cae.gmsh_mesher import (
        GmshMesher,
        load_gmsh_meshing_config,
    )

    repo_root = Path(__file__).resolve().parents[1]
    cad_root = tmp_path / "cad"
    script = tmp_path / "generate_cad.py"
    script.write_text(
        f"""
import json
import sys
from pathlib import Path

sys.path.insert(0, {str(repo_root / "src")!r})

from open_engineering_intelligence.cad import FreeCADBracketBackend
from open_engineering_intelligence.schemas import DesignParameters

backend = FreeCADBracketBackend()
base = Path({str(cad_root)!r})
designs = {{
    "first": DesignParameters(
        thickness_mm=8.0,
        width_mm=50.0,
        rib_height_mm=18.0,
        fillet_radius_mm=2.0,
    ),
    "second": DesignParameters(
        thickness_mm=12.0,
        width_mm=70.0,
        rib_height_mm=28.0,
        fillet_radius_mm=3.0,
    ),
}}
artifacts = {{
    name: {{key: str(path) for key, path in backend.generate(params, base / name).items()}}
    for name, params in designs.items()
}}
print(json.dumps(artifacts, sort_keys=True))
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [freecadcmd, "-c", str(script)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    json_lines = [line for line in completed.stdout.splitlines() if line.startswith("{")]
    assert json_lines, f"FreeCAD did not emit artifact JSON\n{completed.stdout}\n{completed.stderr}"
    cad_artifacts = json.loads(json_lines[-1])

    config = load_gmsh_meshing_config(repo_root / "configs" / "gmsh_bracket_v1.yaml")
    mesher = GmshMesher(config)
    first = mesher.mesh(
        Path(cad_artifacts["first"]["step"]),
        Path(cad_artifacts["first"]["manifest"]),
        tmp_path / "mesh_first",
    )
    repeated = mesher.mesh(
        Path(cad_artifacts["first"]["step"]),
        Path(cad_artifacts["first"]["manifest"]),
        tmp_path / "mesh_repeated",
    )
    second = mesher.mesh(
        Path(cad_artifacts["second"]["step"]),
        Path(cad_artifacts["second"]["manifest"]),
        tmp_path / "mesh_second",
    )

    manifests = [
        json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        for result in (first, repeated, second)
    ]
    for result, manifest in zip((first, repeated, second), manifests, strict=True):
        mesh_path = Path(result["mesh"])
        assert mesh_path.is_file()
        assert mesh_path.stat().st_size > 1000
        assert Path(result["manifest"]).is_file()
        assert manifest["backend"] == "gmsh"
        assert manifest["invocation_method"] == "python_api"
        assert manifest["dimension"] == 3
        assert manifest["element_order"] == 1
        assert manifest["volume_entity_count"] > 0
        assert manifest["node_count"] > 0
        assert manifest["element_count"] > 0
        assert manifest["volume_element_count"] > 0
        assert any(details["dimension"] == 3 for details in manifest["element_types"].values())
        assert manifest["mesh_file"] == "bracket_v1.msh"
        assert _read_mesh_statistics(mesh_path) == (
            manifest["node_count"],
            manifest["element_count"],
            manifest["volume_element_count"],
        )

    first_manifest, repeated_manifest, second_manifest = manifests
    assert first_manifest["source_geometry_fingerprint"] == repeated_manifest[
        "source_geometry_fingerprint"
    ]
    assert first_manifest["meshing_parameters"] == repeated_manifest["meshing_parameters"]
    assert (
        first_manifest["node_count"],
        first_manifest["element_count"],
        first_manifest["volume_element_count"],
        first_manifest["element_types"],
    ) == (
        repeated_manifest["node_count"],
        repeated_manifest["element_count"],
        repeated_manifest["volume_element_count"],
        repeated_manifest["element_types"],
    )
    assert first_manifest["source_geometry_fingerprint"] != second_manifest[
        "source_geometry_fingerprint"
    ]
