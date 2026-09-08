"""Repeatability assertions must detect changed branches and numerical drift."""

import pytest


def test_synthetic_budget_cannot_masquerade_as_production_snapshot(tmp_path):
    from open_engineering_intelligence.pipeline.closed_loop_contracts import ExperimentConfig
    from open_engineering_intelligence.pipeline.experiment import validate_config_snapshot

    path = tmp_path / "closed_loop_thickness_v1.yaml"
    path.write_text("evaluation_budget: 30\n")
    validate_config_snapshot(ExperimentConfig(repo_root=tmp_path), path)
    with pytest.raises(ValueError, match="production configuration"):
        validate_config_snapshot(ExperimentConfig(repo_root=tmp_path, evaluation_budget=2), path)


def test_identical_bytes_do_not_permit_misdirected_dedicated_reference(tmp_path):
    from open_engineering_intelligence.pipeline.artifact_io import artifact_ref
    from open_engineering_intelligence.pipeline.experiment import verify_canonical_ref

    expected = tmp_path / "parameters.json"
    other = tmp_path / "other.json"
    expected.write_text("{}")
    other.write_text("{}")
    assert verify_canonical_ref(artifact_ref(expected, tmp_path), tmp_path, expected) == expected
    with pytest.raises(ValueError, match="misdirected"):
        verify_canonical_ref(artifact_ref(other, tmp_path), tmp_path, expected)


def test_numerical_repeatability_rejects_shape_mismatch_and_above_tolerance():
    from open_engineering_intelligence.pipeline.experiment import compare_numerical

    assert compare_numerical({"value": 1.0}, {"value": 1.000000001}) < 1e-8
    with pytest.raises(ValueError, match="tolerance"):
        compare_numerical({"value": 1.0}, {"value": 1.001})
    with pytest.raises(ValueError):
        compare_numerical({"value": 1.0}, {"other": 1.0})
    with pytest.raises(ValueError):
        compare_numerical([1.0], [1.0, 2.0])


def test_numerical_repeatability_does_not_tolerate_changed_boolean_or_nonfinite():
    from open_engineering_intelligence.pipeline.experiment import compare_numerical

    for first, repeated in ((True, False), (1.0, float("nan")), (True, 1.0)):
        with pytest.raises(ValueError):
            compare_numerical(first, repeated)


def test_repeatability_requires_identical_decision_trajectory():
    from open_engineering_intelligence.pipeline.experiment import compare_trials

    original = {
        "identity": {"parameters": [8.0, 7.0], "accepted_iteration": 1},
        "numerical": {"stress": 25.0},
    }
    changed = {
        "identity": {"parameters": [8.0, 7.0, 6.0], "accepted_iteration": 1},
        "numerical": {"stress": 25.000000001},
    }
    with pytest.raises(ValueError, match="identity"):
        compare_trials(original, changed)


def test_verify_empty_experiment_cannot_claim_repeatability(tmp_path):
    from open_engineering_intelligence.pipeline.experiment import verify_experiment

    report = verify_experiment(tmp_path)
    assert report["status"] == "failed"
    assert report["mismatches"]


def test_accepted_environment_rejects_source_drift_and_missing_tool_identity():
    import copy
    import hashlib

    from open_engineering_intelligence.pipeline.experiment import validate_environment

    source_hash = "a" * 64
    tree_hash = hashlib.sha256(f"src/sample.py\0{source_hash}\n".encode()).hexdigest()
    environment = {
        "git_available": True,
        "repository_commit": "a" * 40,
        "repository_dirty": False,
        "source_tree_consistent": True,
        "source_tree_sha256": tree_hash,
        "source_tree_sha256_end": tree_hash,
        "source_file_sha256": {"src/sample.py": source_hash},
        "source_file_sha256_end": {"src/sample.py": source_hash},
        "discovered_executables": {
            name: {"available": True, "path": f"/tools/{name}", "sha256": "b" * 64}
            for name in ("freecad", "calculix")
        },
        "runtime_versions": {
            "freecad": ["1", "1", "0"],
            "opencascade": "7.8.1",
            "calculix": "2.22",
        },
        "packages": {"gmsh": "4.15.2"},
    }
    validate_environment(environment)
    for field, bad in (
        ("source_tree_consistent", False),
        ("source_tree_sha256_end", "0" * 64),
        ("repository_commit", "unavailable"),
    ):
        broken = copy.deepcopy(environment)
        broken[field] = bad
        with pytest.raises(ValueError):
            validate_environment(broken)
    broken = copy.deepcopy(environment)
    broken["discovered_executables"]["freecad"]["sha256"] = None
    with pytest.raises(ValueError):
        validate_environment(broken)


def test_all_three_trial_pairs_are_compared(monkeypatch, tmp_path):
    from open_engineering_intelligence.pipeline import experiment

    def fake_verified(path):
        value = {"trial-001": 1.0, "trial-002": 1.000000009, "trial-003": 0.999999991}[path.name]
        return {
            "identity": {"same": True},
            "numerical": {"value": value},
            "clean_commit": True,
            "result": {
                "status": "accepted",
                "evaluation_count": 2,
                "mass_reduction_fraction": 0.1,
                "accepted_parameters": {"thickness_mm": 7.0},
            },
        }

    monkeypatch.setattr(experiment, "verify_trial", fake_verified)
    report = experiment.verify_experiment(tmp_path)
    assert report["status"] == "failed"
    assert len(report["mismatches"]) == 1
    assert report["mismatches"][0]["compared_with"].endswith("trial-002")
    assert report["mismatches"][0]["trial"].endswith("trial-003")


def test_replay_requires_recorded_implementation(monkeypatch):
    from open_engineering_intelligence.pipeline import closed_loop, experiment

    monkeypatch.setattr(
        closed_loop,
        "_git_provenance",
        lambda root: {
            "repository_dirty": False,
            "repository_commit": "a" * 40,
        },
    )
    monkeypatch.setattr(closed_loop, "_source_hashes", lambda root: ({}, "b" * 64))
    experiment._require_replay_implementation(
        {
            "repository_commit": "a" * 40,
            "source_tree_sha256": "b" * 64,
        }
    )
    with pytest.raises(ValueError, match="recorded clean implementation"):
        experiment._require_replay_implementation(
            {
                "repository_commit": "c" * 40,
                "source_tree_sha256": "b" * 64,
            }
        )
