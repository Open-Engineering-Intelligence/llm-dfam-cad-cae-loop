"""Boundary tests: malformed evidence must never become engineering acceptance."""

import json
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("raw", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}'])
def test_json_reader_rejects_ambiguous_or_nonfinite_evidence(tmp_path, raw):
    from open_engineering_intelligence.pipeline.artifact_io import read_json

    path = tmp_path / "bad.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        read_json(path)


def test_artifact_verification_rejects_changed_bytes_and_path_escape(tmp_path):
    from open_engineering_intelligence.pipeline.artifact_io import artifact_ref, verify_ref

    path = tmp_path / "input.json"
    path.write_text("{}")
    ref = artifact_ref(path, tmp_path)
    assert verify_ref(ref, tmp_path) == path
    path.write_text('{"changed":true}')
    with pytest.raises(ValueError, match="hash"):
        verify_ref(ref, tmp_path)
    with pytest.raises(ValueError):
        verify_ref({"path": "../outside", "sha256": "0" * 64}, tmp_path)


def test_effective_analysis_moves_load_with_candidate_without_mutating_reference():
    from open_engineering_intelligence.pipeline.closed_loop_contracts import LoopParameters
    from open_engineering_intelligence.pipeline.structural_evaluator import effective_config

    repo = Path(__file__).resolve().parents[1]
    path = repo / "configs/calculix_bracket_v1.yaml"
    before = path.read_bytes()
    config = effective_config(
        LoopParameters(thickness_mm=7.0, width_mm=50.0, rib_height_mm=18.0, fillet_radius_mm=2.0),
        repo,
    )
    assert config.load_z_mm == 7.0
    assert config.load_y_range_mm == (-25.0, 25.0)
    assert config.total_load_n == (0.0, 0.0, -150.0)
    assert path.read_bytes() == before


def test_process_timeout_retains_logs_and_terminates_worker(tmp_path):
    from open_engineering_intelligence.pipeline.artifact_io import run_process

    with pytest.raises(TimeoutError):
        run_process(
            [sys.executable, "-u", "-c", "import time; print('started'); time.sleep(60)"],
            tmp_path,
            "worker",
            0.5,
        )
    assert "started" in (tmp_path / "worker.stdout.log").read_text()


def test_normalized_result_rejects_wrong_units_and_failed_sanity(tmp_path):
    from open_engineering_intelligence.pipeline.structural_evaluator import physics_metrics

    result = {
        "solver_status": "succeeded",
        "solver_version": "2.22",
        "max_displacement": {"unit": "mm", "value": 1.0},
        "max_von_mises_stress": {"unit": "MPa", "value": 20.0, "position": "integration_point"},
        "sanity_checks": {},
    }
    with pytest.raises(ValueError, match="sanity"):
        physics_metrics(result)
    from open_engineering_intelligence.cae.calculix_solver import SANITY_CHECKS

    result["sanity_checks"] = dict.fromkeys(SANITY_CHECKS, True)
    assert physics_metrics(result) == (20.0, 1.0)
    result["max_von_mises_stress"]["unit"] = "Pa"
    with pytest.raises(ValueError, match="unit"):
        physics_metrics(result)


def test_atomic_json_is_strict_and_has_trailing_newline(tmp_path):
    from open_engineering_intelligence.pipeline.artifact_io import write_json

    path = tmp_path / "record.json"
    write_json(path, {"z": 1, "a": 2})
    assert path.read_text().endswith("\n")
    assert json.loads(path.read_text()) == {"a": 2, "z": 1}
    with pytest.raises(ValueError):
        write_json(path, {"bad": float("nan")})
    assert json.loads(path.read_text()) == {"a": 2, "z": 1}


def _linked_evidence(root):
    from dataclasses import asdict

    from open_engineering_intelligence.cae.calculix_solver import (
        SANITY_CHECKS,
        analysis_definition,
        analysis_fingerprint,
    )
    from open_engineering_intelligence.cae.gmsh_mesher import load_gmsh_meshing_config
    from open_engineering_intelligence.pipeline.artifact_io import sha256, write_json
    from open_engineering_intelligence.pipeline.closed_loop_contracts import (
        ExperimentConfig,
        LoopParameters,
    )
    from open_engineering_intelligence.pipeline.structural_evaluator import effective_config

    directory = root / "000"
    for name in ("cad", "mesh", "fea"):
        (directory / name).mkdir(parents=True)
    parameters = LoopParameters(
        thickness_mm=8.0, width_mm=50.0, rib_height_mm=18.0, fillet_radius_mm=2.0
    )
    config = ExperimentConfig(repo_root=Path(__file__).resolve().parents[1])
    analysis = effective_config(parameters, config.repo_root)
    geometry = {"volume_mm3": 10000.0}
    cad = {
        "parameters": parameters.model_dump(),
        "shape_valid": True,
        "cad_fingerprint": geometry,
        "geometry_fingerprint": geometry,
    }
    for name in ("bracket_v1.FCStd", "bracket_v1.step", "bracket_v1.stl"):
        (directory / "cad" / name).write_text("synthetic CAD artifact")
    cad["artifact_paths"] = {
        "freecad_document": "bracket_v1.FCStd",
        "step": "bracket_v1.step",
        "stl": "bracket_v1.stl",
    }
    cad["artifact_file_sizes_bytes"] = {
        key: (directory / "cad" / name).stat().st_size
        for key, name in cad["artifact_paths"].items()
    }
    write_json(directory / "cad/bracket_v1_manifest.json", cad)
    (directory / "mesh/bracket_v1.msh").write_text(
        "$MeshFormat\n4.1 0 8\n$EndMeshFormat\n$Nodes\n1 4 1 4\n3 1 0 4\n"
        "1\n2\n3\n4\n0 -35 0\n0 35 0\n0 0 70\n103 0 8\n$EndNodes\n"
        "$Elements\n2 3 1 100\n2 1 2 2\n1 1 2 3\n2 2 3 4\n"
        "3 1 4 1\n100 1 2 3 4\n$EndElements\n"
    )
    (directory / "fea/bracket_v1_static.inp").write_text("synthetic input")
    provenance = {
        "backend": "gmsh",
        "gmsh_version": "4.15.2",
        "invocation_method": "python_api",
        "dimension": 3,
        "element_order": 1,
        "node_count": 4,
        "element_count": 3,
        "volume_element_count": 1,
        "volume_entity_count": 1,
        "element_types": {
            "2": {"name": "Triangle 3", "dimension": 2, "order": 1, "count": 2},
            "4": {"name": "Tetrahedron 4", "dimension": 3, "order": 1, "count": 1},
        },
        "meshing_parameters": asdict(
            load_gmsh_meshing_config(config.repo_root / "configs/gmsh_bracket_v1.yaml")
        ),
    }
    write_json(
        directory / "mesh/bracket_v1_mesh_manifest.json",
        {
            "source_geometry_fingerprint": geometry,
            "mesh_file": "bracket_v1.msh",
            **provenance,
        },
    )
    definition = analysis_definition(analysis)
    write_json(directory / "effective_analysis.json", definition)
    write_json(
        directory / "cad_backend.json",
        {"freecad_version": ["1", "1", "0"], "opencascade_version": "7.8.1"},
    )
    result = {
        "solver_status": "succeeded",
        "solver_version": "2.22",
        "invocation": {
            "executable": str(Path(sys.executable).resolve()),
            "arguments": [str(Path(sys.executable).resolve()), "-i", "bracket_v1_static"],
            "cwd": str(directory / "fea"),
            "timeout_seconds": 120,
            "return_code": 0,
            "num_threads": 1,
            "discovery": "explicit_path",
        },
        "sanity_checks": dict.fromkeys(SANITY_CHECKS, True),
        "input_geometry_fingerprint": geometry,
        "mesh_provenance": {
            **provenance,
            "mesh_sha256": sha256(directory / "mesh/bracket_v1.msh"),
        },
        "analysis_definition": definition,
        "analysis_fingerprint": analysis_fingerprint(analysis),
        "calculix_input_sha256": sha256(directory / "fea/bracket_v1_static.inp"),
        "units": {"length": "mm", "force": "N", "stress": "MPa", "displacement": "mm"},
        "boundary_condition": {"node_ids": [1, 2, 3]},
        "load": {**definition["load"], "node_ids": [4], "summed_force_n": [0, 0, -150]},
        "max_displacement": {"value": 1.0, "unit": "mm", "node_id": 4},
        "max_von_mises_stress": {
            "value": 20.0,
            "unit": "MPa",
            "position": "integration_point",
        },
    }
    write_json(directory / "fea/physics_result.json", result)
    return parameters, config, directory


@pytest.mark.parametrize("field", ["analysis_fingerprint", "calculix_input_sha256"])
def test_collect_rejects_stale_analysis_and_input_identity(tmp_path, field):
    from open_engineering_intelligence.pipeline.artifact_io import read_json, write_json
    from open_engineering_intelligence.pipeline.structural_evaluator import collect_evaluation

    params, config, directory = _linked_evidence(tmp_path)
    assert collect_evaluation(params, config, directory).metrics.mass_g == 12.4
    path = directory / "fea/physics_result.json"
    value = read_json(path)
    value[field] = "0" * 64
    write_json(path, value)
    with pytest.raises(ValueError, match="mismatch"):
        collect_evaluation(params, config, directory)


def test_collect_cannot_accept_missing_cad_exports(tmp_path):
    from open_engineering_intelligence.pipeline.structural_evaluator import collect_evaluation

    params, config, directory = _linked_evidence(tmp_path)
    (directory / "cad/bracket_v1.step").unlink()
    with pytest.raises(ValueError, match="CAD artifact"):
        collect_evaluation(params, config, directory)


def test_collect_cannot_accept_missing_backend_version_evidence(tmp_path):
    from open_engineering_intelligence.pipeline.structural_evaluator import collect_evaluation

    params, config, directory = _linked_evidence(tmp_path)
    (directory / "cad_backend.json").unlink()
    with pytest.raises((ValueError, OSError)):
        collect_evaluation(params, config, directory)


def test_evaluator_refuses_stale_partial_evidence(tmp_path):
    from open_engineering_intelligence.pipeline.closed_loop_contracts import ExperimentConfig
    from open_engineering_intelligence.pipeline.structural_evaluator import evaluate_candidate

    config = ExperimentConfig(repo_root=Path(__file__).resolve().parents[1])
    directory = tmp_path / "000"
    directory.mkdir()
    (directory / "cad_backend.json").write_text("{}")
    with pytest.raises(ValueError, match="evidence"):
        evaluate_candidate(config.initial_parameters, config, directory)


def test_worker_normal_exit_also_cleans_up_descendant_processes(tmp_path):
    import time

    from open_engineering_intelligence.pipeline.artifact_io import run_process

    child_code = (
        "import time; from pathlib import Path; time.sleep(1); Path('leak').write_text('bad')"
    )
    parent_code = (
        "import subprocess, sys; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "import time; time.sleep(0.1)"
    )
    assert run_process([sys.executable, "-c", parent_code], tmp_path, "parent", 5) == 0
    time.sleep(1.2)
    assert not (tmp_path / "leak").exists(), "worker left a child writing after finalization"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object launch ordering")
def test_worker_is_suspended_until_assigned_to_its_job(tmp_path, monkeypatch):
    import time

    from open_engineering_intelligence.pipeline.artifact_io import _WindowsJob, run_process

    assign = _WindowsJob.assign

    def delayed_assignment(job, process):
        time.sleep(0.2)
        assert not (tmp_path / "started").exists()
        assign(job, process)

    monkeypatch.setattr(_WindowsJob, "assign", delayed_assignment)
    code = "from pathlib import Path; Path('started').write_text('yes')"
    assert run_process([sys.executable, "-c", code], tmp_path, "suspended", 5) == 0
    assert (tmp_path / "started").read_text() == "yes"


def test_collect_rejects_incomplete_mesh_provenance(tmp_path):
    from open_engineering_intelligence.pipeline.artifact_io import read_json, write_json
    from open_engineering_intelligence.pipeline.structural_evaluator import collect_evaluation

    params, config, directory = _linked_evidence(tmp_path)
    path = directory / "fea/physics_result.json"
    value = read_json(path)
    value["mesh_provenance"].pop("backend")
    write_json(path, value)
    with pytest.raises((ValueError, KeyError)):
        collect_evaluation(params, config, directory)
