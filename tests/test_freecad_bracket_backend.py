import json
import shutil
import subprocess
from pathlib import Path

import pytest

from open_engineering_intelligence.cad.freecad_backend import (
    BRACKET_V1_DIMENSIONS,
    load_bracket_v1_dimensions,
)


def test_freecad_backend_dimensions_match_bracket_config() -> None:
    assert load_bracket_v1_dimensions(Path("configs/bracket_default.yaml")) == BRACKET_V1_DIMENSIONS


def _freecadcmd() -> str | None:
    exe = shutil.which("FreeCADCmd") or shutil.which("freecadcmd")
    if exe:
        return exe
    candidate = Path(r"C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe")
    if candidate.exists():
        return str(candidate)
    return None


@pytest.mark.integration
def test_freecad_backend_generates_valid_deterministic_step_geometry(tmp_path: Path) -> None:
    freecadcmd = _freecadcmd()
    if freecadcmd is None:
        pytest.skip("FreeCADCmd is not available")

    repo_root = Path(__file__).resolve().parents[1]
    script = tmp_path / "run_freecad_smoke.py"
    script.write_text(
        f"""
import json
import sys
from pathlib import Path

sys.path.insert(0, {str(repo_root / "src")!r})

import Part

from open_engineering_intelligence.cad.freecad_backend import FreeCADBracketBackend
from open_engineering_intelligence.schemas import DesignParameters

backend = FreeCADBracketBackend()
base = Path({str(tmp_path)!r})
params_a = DesignParameters(
    thickness_mm=8.0,
    width_mm=50.0,
    rib_height_mm=18.0,
    fillet_radius_mm=2.0,
)
params_b = DesignParameters(
    thickness_mm=12.0,
    width_mm=70.0,
    rib_height_mm=28.0,
    fillet_radius_mm=3.0,
)

first = backend.generate(params_a, base / "first")
second = backend.generate(params_a, base / "second")
third = backend.generate(params_b, base / "third")

def load_manifest(artifacts):
    return json.loads(Path(artifacts["manifest"]).read_text(encoding="utf-8"))

def step_is_valid(artifacts):
    shape = Part.read(str(artifacts["step"]))
    return shape.isValid() and shape.Volume > 0

print(json.dumps({{
    "first": {{k: str(v) for k, v in first.items()}},
    "second": {{k: str(v) for k, v in second.items()}},
    "third": {{k: str(v) for k, v in third.items()}},
    "first_manifest": load_manifest(first),
    "second_manifest": load_manifest(second),
    "third_manifest": load_manifest(third),
    "first_step_valid": step_is_valid(first),
    "second_step_valid": step_is_valid(second),
    "third_step_valid": step_is_valid(third),
}}, sort_keys=True))
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
    assert json_lines, (
        "FreeCAD smoke script did not emit JSON\n"
        f"{completed.stdout}\n{completed.stderr}"
    )
    result = json.loads(json_lines[-1])

    for run_key in ["first", "second", "third"]:
        artifacts = result[run_key]
        assert Path(artifacts["freecad_document"]).is_file()
        assert Path(artifacts["step"]).is_file()
        assert Path(artifacts["manifest"]).is_file()
        assert Path(artifacts["step"]).stat().st_size > 1000
        assert result[f"{run_key}_manifest"]["shape_valid"] is True
        assert result[f"{run_key}_step_valid"] is True

    assert (
        result["first_manifest"]["geometry_fingerprint"]
        == result["second_manifest"]["geometry_fingerprint"]
    )
    assert (
        result["first_manifest"]["geometry_fingerprint"]
        != result["third_manifest"]["geometry_fingerprint"]
    )
