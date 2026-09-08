"""Execution contract tests; synthetic solver output is not physical evidence."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from open_engineering_intelligence.cae import calculix_solver as ccx


@pytest.fixture
def config():
    return ccx.load_calculix_static_config(Path("configs/calculix_bracket_v1.yaml"))


@pytest.fixture
def inputs(tmp_path):
    mesh = tmp_path / "tetra.msh"
    mesh.write_text(
        """$MeshFormat
4.1 0 8
$EndMeshFormat
$Nodes
1 4 10 40
3 1 0 4
10 20 30 40
0 -35 0
0 35 0
0 0 70
103 0 8
$EndNodes
$Elements
2 5 1 100
2 1 2 4
1 10 20 30
2 10 20 40
3 10 30 40
4 20 30 40
3 1 4 1
100 10 20 30 40
$EndElements
""",
        encoding="ascii",
    )
    manifest = tmp_path / "mesh_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "backend": "gmsh",
                "dimension": 3,
                "element_order": 1,
                "node_count": 4,
                "volume_element_count": 1,
                "element_count": 5,
                "volume_entity_count": 1,
                "gmsh_version": "4.15.2",
                "invocation_method": "python_api",
                "mesh_file": mesh.name,
                "meshing_parameters": {"num_threads": 1},
                "element_types": {"4": {"dimension": 3, "order": 1, "count": 1}},
                "source_geometry_fingerprint": {"volume_mm3": 84116.666667},
                "source_step": "synthetic.step",
            }
        ),
        encoding="utf-8",
    )
    executable = tmp_path / "ccx"
    executable.write_bytes(b"test-double; never executed")
    return mesh, manifest, executable


DAT = """ displacements (vx,vy,vz) for set ALL_NODES and time 1

10 0 0 0
20 0 0 0
30 0 0 0
40 0.1 0 -0.5

 forces (fx,fy,fz) for set FIXED_NODES and time 1

10 0 0 50
20 0 0 50
30 0 0 50

 stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set VOLUME_ELEMENTS and time 1

100 1 10 0 0 0 2 3

"""


def fake_run(
    monkeypatch,
    *,
    dat=DAT,
    stdout="CalculiX Version 2.22\nJob finished\n",
    stderr="",
    returncode=0,
    sta="1 1 1 1 1.0 1.0 1.0\n",
):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        directory = Path(kwargs["cwd"])
        case = args[-1]
        (directory / f"{case}.dat").write_text(dat, encoding="ascii")
        (directory / f"{case}.frd").write_text(
            " -4 DISP 4 1\n -4 STRESS 6 1\n -4 FORC 4 1\n", encoding="ascii"
        )
        (directory / f"{case}.sta").write_text(sta, encoding="ascii")
        return subprocess.CompletedProcess(args, returncode, stdout, stderr)

    monkeypatch.setattr("subprocess.run", run)
    return calls


def solve(config, inputs, output_dir):
    mesh, manifest, executable = inputs
    return ccx.CalculiXStaticSolver(config, executable=executable).solve(mesh, manifest, output_dir)


def test_solver_writes_complete_result_and_invokes_without_shell(
    config, inputs, tmp_path, monkeypatch
):
    calls = fake_run(monkeypatch)
    artifacts = solve(config, inputs, tmp_path / "solve")
    result = json.loads(artifacts["result"].read_text())
    assert result["solver_status"] == "succeeded"
    assert result["solver_version"] == "2.22"
    assert result["failure_stage"] is None and result["failure_reason"] is None
    assert all(result["sanity_checks"].values())
    assert result["max_displacement"]["value"] == pytest.approx(0.26**0.5)
    assert result["max_displacement"]["node_id"] == 40
    assert result["max_von_mises_stress"]["value"] == pytest.approx(139**0.5)
    assert result["max_von_mises_stress"]["position"] == "integration_point"
    assert result["reaction_force_n"] == [0, 0, 150]
    assert result["equilibrium_residual_n"] == 0
    assert result["boundary_condition"]["node_ids"] == [10, 20, 30]
    assert result["load"]["node_ids"] == [40]
    assert result["load"]["summed_force_n"] == [0, 0, -150]
    assert result["units"]["displacement"] == "mm"
    assert (
        result["mesh_provenance"]["mesh_sha256"]
        == hashlib.sha256(inputs[0].read_bytes()).hexdigest()
    )
    assert result["input_geometry_fingerprint"] == {"volume_mm3": 84116.666667}
    assert (
        result["calculix_input_sha256"]
        == hashlib.sha256(artifacts["input"].read_bytes()).hexdigest()
    )
    args, kwargs = calls[0]
    assert args == [str(inputs[2].resolve()), "-i", config.case_name]
    assert kwargs["cwd"] == (tmp_path / "solve").resolve()
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == config.timeout_seconds
    assert kwargs["env"]["OMP_NUM_THREADS"] == "1"
    assert artifacts["stdout"].read_text() == "CalculiX Version 2.22\nJob finished\n"
    assert artifacts["stderr"].read_text() == ""


@pytest.mark.parametrize(
    ("change", "stage", "message"),
    [
        ({"returncode": 1, "stderr": "process error"}, "solver_execution", "exit code 1"),
        (
            {"stdout": "CalculiX Version 2.22\nsingular matrix\nJob finished"},
            "solver_execution",
            "singular",
        ),
        ({"stderr": "non-convergence"}, "solver_execution", "non-convergence"),
        ({"stdout": "CalculiX Version 2.22\nNaN\nJob finished"}, "solver_execution", "NaN"),
        ({"stdout": "CalculiX Version 2.22\nInf\nJob finished"}, "solver_execution", "Inf"),
        ({"stdout": "CalculiX Version 2.22"}, "solver_execution", "Job finished"),
        ({"stdout": "CalculiX Version 2.21\nJob finished"}, "solver_execution", "2.22"),
        ({"sta": "1 1 1 1 0.5 0.5 0.5\n"}, "solver_execution", "final time"),
        ({"dat": DAT.replace("40 0.1 0 -0.5", "40 0.1 0 nan")}, "result_parsing", "NaN or Inf"),
        (
            {"dat": DAT.replace("40 0.1 0 -0.5", "40 0.1 0 0.5")},
            "physics_validation",
            "loaded_region_average_uz_negative",
        ),
        (
            {"dat": DAT.replace("10 0 0 0", "10 0 0 0.01", 1)},
            "physics_validation",
            "fixed_displacement_near_zero",
        ),
        (
            {"dat": DAT.replace("30 0 0 50", "30 0 0 40")},
            "physics_validation",
            "reaction_equilibrium",
        ),
        ({"dat": ""}, "result_parsing", "missing displacement"),
    ],
)
def test_solver_failure_is_staged_and_persisted(
    config, inputs, tmp_path, monkeypatch, change, stage, message
):
    fake_run(monkeypatch, **change)
    with pytest.raises(ccx.CalculiXStaticError, match=message) as error:
        solve(config, inputs, tmp_path / "solve")
    assert error.value.stage == stage
    result = json.loads(error.value.result_path.read_text())
    assert result["solver_status"] == "failed"
    assert result["failure_stage"] == stage
    assert result["failure_reason"]
    assert result["max_displacement"] is None
    assert result["max_von_mises_stress"] is None
    assert result["reaction_force_n"] is None


@pytest.mark.parametrize(
    "kind",
    ["missing_mesh", "manifest_mismatch", "empty_fixed", "no_executable", "timeout", "oserror"],
)
def test_pre_execution_and_timeout_failures(config, inputs, tmp_path, monkeypatch, kind):
    mesh, manifest, executable = inputs
    expected_stage = "mesh_validation"
    if kind == "missing_mesh":
        mesh = tmp_path / "absent.msh"
    elif kind == "manifest_mismatch":
        manifest.write_text(manifest.read_text().replace('"node_count": 4', '"node_count": 99'))
    elif kind == "empty_fixed":
        mesh.write_text(
            mesh.read_text()
            .replace("0 -35 0", "1 -35 0")
            .replace("0 35 0", "1 35 0")
            .replace("0 0 70", "1 0 70")
        )
        expected_stage = "boundary_selection"
    elif kind == "no_executable":
        executable = tmp_path / "absent-ccx"
        expected_stage = "solver_invocation"
    else:
        expected_stage = "solver_execution" if kind == "timeout" else "solver_invocation"

    def run(args, **kwargs):
        if kind == "timeout":
            raise subprocess.TimeoutExpired(args, 120, output=b"partial stdout", stderr=b"detail")
        if kind == "oserror":
            raise OSError("cannot launch")
        pytest.fail("solver must not be invoked after failed preflight")

    monkeypatch.setattr("subprocess.run", run)
    with pytest.raises(ccx.CalculiXStaticError) as error:
        solve(config, (mesh, manifest, executable), tmp_path / "solve")
    assert error.value.stage == expected_stage
    result = json.loads(error.value.result_path.read_text())
    assert result["failure_stage"] == expected_stage
    assert result["max_displacement"] is None
    if kind == "timeout":
        assert (tmp_path / "solve/ccx.stdout.log").read_text() == "partial stdout"
        assert (tmp_path / "solve/ccx.stderr.log").read_text() == "detail"


def test_solver_refuses_to_overwrite_prior_artifacts(config, inputs, tmp_path, monkeypatch):
    output = tmp_path / "prior"
    output.mkdir()
    evidence = output / "physics_result.json"
    evidence.write_text("preserve existing evidence")
    calls = fake_run(monkeypatch)
    with pytest.raises(ccx.CalculiXStaticError, match="not empty"):
        solve(config, inputs, output)
    assert evidence.read_text() == "preserve existing evidence"
    assert not calls


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace("100 1 10 0 0 0 2 3", "100 1 10 0 0 0 2 3\n100 1 10 0 0 0 2 3"),
        lambda s: s.replace("100 1 10 0 0 0 2 3", "100 2 10 0 0 0 2 3"),
        lambda s: s.replace("and time 1", "and time 0.5", 1),
        lambda s: s.replace("40 0.1 0 -0.5", "40 malformed 0 -0.5"),
    ],
)
def test_parser_rejects_duplicate_wrong_point_partial_time_and_malformed_values(tmp_path, change):
    dat = tmp_path / "bad.dat"
    dat.write_text(change(DAT))
    with pytest.raises(ccx.CalculiXStaticError) as error:
        ccx.parse_calculix_dat(
            dat,
            volume_node_ids={10, 20, 30, 40},
            fixed_node_ids={10, 20, 30},
            volume_element_ids={100},
        )
    assert error.value.stage == "result_parsing"


def test_truncated_mesh_has_mesh_validation_stage(inputs):
    mesh = inputs[0]
    mesh.write_text(mesh.read_text().replace("100 10 20 30 40", "100 10"))
    with pytest.raises(ccx.CalculiXStaticError) as error:
        ccx.parse_gmsh_msh(mesh)
    assert error.value.stage == "mesh_validation"


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("solver", "case_name", "../outside"),
        ("solver", "target_version", "2.21"),
        ("material", "name", "material\n*BOUNDARY"),
        ("material", "youngs_modulus_mpa", float("nan")),
        ("boundary_condition", "coordinate_tolerance_mm", float("inf")),
        ("boundary_condition", "node_set", "IGNORED"),
        ("load", "distribution", "ignored_distribution"),
        ("load", "z_mm", float("nan")),
    ],
)
def test_config_rejects_unsafe_nonfinite_or_ignored_settings(tmp_path, section, key, value):
    raw = yaml.safe_load(Path("configs/calculix_bracket_v1.yaml").read_text())
    raw[section][key] = value
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        ccx.load_calculix_static_config(path)


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace("10 20 30 40", "-10 20 30 40"),
        lambda s: s.replace("100 10 20 30 40", "0 10 20 30 40"),
        lambda s: s.replace("1 10 20 30", "1 999 20 30"),
        lambda s: s.replace("2 1 2 4", "1 1 2 4"),
        lambda s: s.replace("100 10 20 30 40", "100 10 20 30 30"),
    ],
)
def test_mesh_rejects_invalid_ids_surface_references_dimensions_and_repeated_nodes(inputs, change):
    mesh = inputs[0]
    mesh.write_text(change(mesh.read_text()))
    with pytest.raises(ccx.CalculiXStaticError) as error:
        ccx.parse_gmsh_msh(mesh)
    assert error.value.stage == "mesh_validation"


def test_fingerprint_covers_boundary_and_analysis_settings(config):
    from dataclasses import replace

    original = ccx.analysis_fingerprint(config)
    for changed in (
        replace(config, fixed_x_mm=1.0),
        replace(config, target_version="2.23"),
        replace(config, load_z_mm=9.0),
        replace(config, geometric_nonlinearity=True),
    ):
        assert ccx.analysis_fingerprint(changed) != original


def test_physics_failure_retains_check_values(config, inputs, tmp_path, monkeypatch):
    fake_run(monkeypatch, dat=DAT.replace("30 0 0 50", "30 0 0 40"))
    with pytest.raises(ccx.CalculiXStaticError) as error:
        solve(config, inputs, tmp_path / "failed_physics")
    result = json.loads(error.value.result_path.read_text())
    assert result["sanity_checks"]["reaction_equilibrium"] is False
    assert result["sanity_checks"]["solver_completed"] is True
    assert result["diagnostics"]["equilibrium_residual_n"] == 10


def test_nonfinite_derived_displacement_persists_standards_compliant_failure(
    config, inputs, tmp_path, monkeypatch
):
    dat = DAT.replace("10 0 0 0", "10 1.5e308 1.5e308 1.5e308", 1)
    fake_run(monkeypatch, dat=dat)
    output = tmp_path / "overflowed_displacement"

    with pytest.raises(ccx.CalculiXStaticError, match="results_finite") as error:
        solve(config, inputs, output)

    assert error.value.stage == "physics_validation"
    assert error.value.result_path == output / "physics_result.json"
    raw_result = error.value.result_path.read_text(encoding="utf-8")
    result = json.loads(
        raw_result,
        parse_constant=lambda value: pytest.fail(f"non-standard JSON number: {value}"),
    )
    assert result["solver_status"] == "failed"
    assert result["failure_stage"] == "physics_validation"
    assert "results_finite" in result["failure_reason"]
    assert result["max_displacement"] is None
    assert result["diagnostics"]["fixed_max_displacement_mm"] is None
    assert result["sanity_checks"]["results_finite"] is False


def test_nonfinite_manifest_cannot_break_failure_json(config, inputs, tmp_path, monkeypatch):
    mesh, manifest, _ = inputs
    manifest.write_text(manifest.read_text().replace("84116.666667", "1e999"))
    calls = fake_run(monkeypatch)
    with pytest.raises(ccx.CalculiXStaticError) as error:
        solve(config, inputs, tmp_path / "bad_manifest")
    result = json.loads(error.value.result_path.read_text())
    assert result["solver_status"] == "failed"
    assert result["failure_stage"] == "mesh_validation"
    assert not calls


def test_failed_result_write_never_recovers_as_succeeded(config, inputs, tmp_path, monkeypatch):
    fake_run(monkeypatch)
    real_write = ccx._write_result
    calls = []

    def write_once_failing(path, result):
        calls.append(result["solver_status"])
        if len(calls) == 1:
            raise OSError("transient result write failure")
        real_write(path, result)

    monkeypatch.setattr(ccx, "_write_result", write_once_failing)
    with pytest.raises(ccx.CalculiXStaticError) as error:
        solve(config, inputs, tmp_path / "failed_result_write")
    result = json.loads(error.value.result_path.read_text())
    assert result["solver_status"] == "failed"
    assert result["failure_reason"] == "transient result write failure"
