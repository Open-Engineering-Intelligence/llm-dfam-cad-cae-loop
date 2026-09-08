"""Opt-in real evidence; skips are not milestone acceptance."""

import importlib.util
import os
import shutil
from pathlib import Path

import pytest


@pytest.mark.integration
def test_real_thickness_loop_three_fresh_trials(tmp_path):
    from open_engineering_intelligence.cae.calculix_solver import discover_calculix_executable
    from open_engineering_intelligence.pipeline.closed_loop_contracts import load_experiment_config
    from open_engineering_intelligence.pipeline.experiment import run_experiment, verify_experiment
    from open_engineering_intelligence.pipeline.structural_evaluator import discover_freecad

    if importlib.util.find_spec("gmsh") is None:
        pytest.skip("Gmsh Python API is unavailable")
    try:
        discover_freecad()
        discover_calculix_executable()
    except RuntimeError as exc:
        pytest.skip(str(exc))
    config = load_experiment_config(Path(__file__).resolve().parents[1])
    root = Path(os.environ.get("CLOSED_LOOP_TEST_OUTPUT_ROOT", str(tmp_path / "experiment")))
    report = run_experiment(config, root)
    assert report["status"] == "passed", report["mismatches"]
    assert report["verified_trial_count"] == 3
    assert not report["mismatches"]
    for result in report["trial_results"]:
        assert 2 <= result["evaluation_count"] <= 5
        assert result["accepted_parameters"]["thickness_mm"] < 8
        assert result["mass_reduction_fraction"] > 0
        assert result["full_benchmark_feasible"] is None
    # A fresh read-only verification must derive the same outcome from raw evidence.
    assert verify_experiment(root)["status"] == "passed"
    # Relocation preserves evidence, while altered metadata must not be trusted even rehashed.
    from open_engineering_intelligence.pipeline.artifact_io import read_json, sha256, write_json

    relocated = tmp_path / "relocated_evidence"
    shutil.copytree(root, relocated)
    assert verify_experiment(relocated)["status"] == "passed"
    environment_path = relocated / "trial-001/environment_manifest.json"
    environment = read_json(environment_path)
    environment["source_tree_consistent"] = False
    write_json(environment_path, environment)
    result_path = relocated / "trial-001/closed_loop_result.json"
    result = read_json(result_path)
    result["environment_manifest"]["sha256"] = sha256(environment_path)
    write_json(result_path, result)
    tampered = verify_experiment(relocated)
    assert tampered["status"] == "failed"
    assert any("source changed" in item["message"] for item in tampered["mismatches"])
