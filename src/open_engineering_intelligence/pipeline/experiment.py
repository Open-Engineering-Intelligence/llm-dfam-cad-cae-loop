"""Three independent real trials and read-only verification of retained evidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
from itertools import combinations
from pathlib import Path

import yaml

from open_engineering_intelligence.optimization.thickness_controller import decide
from open_engineering_intelligence.pipeline.artifact_io import (
    read_json,
    run_process,
    verify_ref,
    write_json,
)
from open_engineering_intelligence.pipeline.closed_loop_contracts import (
    CandidateEvaluation,
    ClosedLoopResult,
    ControllerDecision,
    ExperimentConfig,
    IterationManifest,
    LoopParameters,
)
from open_engineering_intelligence.pipeline.structural_evaluator import collect_evaluation

TOLERANCE = "abs(a-b) <= max(1e-9, 1e-8 * max(abs(a), abs(b)))"


def compare_numerical(first, repeated, path="root") -> float:
    """Compare complete matching structures; numerical tolerance never applies to booleans."""
    if isinstance(first, dict) and isinstance(repeated, dict):
        if first.keys() != repeated.keys():
            raise ValueError(f"numerical shape mismatch at {path}")
        return max(
            (compare_numerical(first[k], repeated[k], f"{path}.{k}") for k in first), default=0
        )
    if isinstance(first, list) and isinstance(repeated, list):
        if len(first) != len(repeated):
            raise ValueError(f"numerical length mismatch at {path}")
        return max(
            (
                compare_numerical(a, b, f"{path}[{i}]")
                for i, (a, b) in enumerate(zip(first, repeated, strict=True))
            ),
            default=0,
        )
    if type(first) in (int, float) and type(repeated) in (int, float):
        if not math.isfinite(first) or not math.isfinite(repeated):
            raise ValueError(f"nonfinite numerical value at {path}")
        delta = abs(first - repeated)
        if delta > max(1e-9, 1e-8 * max(abs(first), abs(repeated))):
            raise ValueError(f"numerical tolerance exceeded at {path}: {first} versus {repeated}")
        return delta
    if type(first) is not type(repeated) or first != repeated:
        raise ValueError(f"non-numerical value mismatch at {path}")
    return 0.0


def compare_trials(first: dict, repeated: dict) -> float:
    if first["identity"] != repeated["identity"]:
        raise ValueError("repeat identity mismatch (configuration, environment, or trajectory)")
    return compare_numerical(first["numerical"], repeated["numerical"])


def verify_canonical_ref(reference, root: Path, expected: Path) -> Path:
    path = verify_ref(reference, root)
    if path != expected:
        raise ValueError(f"misdirected reference: expected {expected.relative_to(root)}")
    return path


def validate_config_snapshot(config: ExperimentConfig, snapshot: Path) -> None:
    values = yaml.safe_load(snapshot.read_text(encoding="utf-8"))
    if not isinstance(values, dict) or "repo_root" in values:
        raise ValueError("invalid production configuration snapshot")
    expected = ExperimentConfig.model_validate({**values, "repo_root": config.repo_root})
    if expected != config or expected.evaluation_budget != 30:
        raise ValueError("persisted configuration differs from frozen production configuration")


def validate_environment(environment: dict) -> None:
    if (
        environment["git_available"] is not True
        or not re.fullmatch(r"[0-9a-f]{40}", environment["repository_commit"])
        or environment["repository_dirty"] is not False
    ):
        raise ValueError("acceptance requires a recorded clean implementation commit")
    if (
        environment["source_tree_consistent"] is not True
        or environment["source_tree_sha256"] != environment["source_tree_sha256_end"]
        or environment["source_file_sha256"] != environment["source_file_sha256_end"]
    ):
        raise ValueError("recorded implementation source changed during evaluation")
    digest = hashlib.sha256()
    for name, value in sorted(environment["source_file_sha256"].items()):
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("invalid source hash")
        digest.update(f"{name}\0{value}\n".encode())
    if digest.hexdigest() != environment["source_tree_sha256"]:
        raise ValueError("source tree hash does not match file identities")
    for tool in ("freecad", "calculix"):
        record = environment["discovered_executables"][tool]
        if (
            record["available"] is not True
            or not record["path"]
            or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"] or "")
        ):
            raise ValueError(f"missing executable identity: {tool}")
    versions = environment["runtime_versions"]
    if (
        not versions["freecad"]
        or not versions["opencascade"]
        or versions["calculix"] != "2.22"
        or environment["packages"]["gmsh"] != "4.15.2"
    ):
        raise ValueError("missing or incorrect backend versions")


def _require_replay_implementation(environment):
    from open_engineering_intelligence.pipeline.closed_loop import _git_provenance, _source_hashes

    executing_repo = Path(__file__).resolve().parents[3]
    current = _git_provenance(executing_repo)
    _, tree_hash = _source_hashes(executing_repo)
    if (
        current["repository_dirty"]
        or current["repository_commit"] != environment["repository_commit"]
        or tree_hash != environment["source_tree_sha256"]
    ):
        raise ValueError("verify using the recorded clean implementation commit and source tree")


def verify_trial(root: Path) -> dict:
    root = Path(root).resolve()
    result = ClosedLoopResult.model_validate(read_json(root / "closed_loop_result.json"))
    for reference, name in (
        (result.experiment_config, "experiment_config.json"),
        (result.environment_manifest, "environment_manifest.json"),
    ):
        verify_canonical_ref(reference, root, root / name)
    config = ExperimentConfig.model_validate_json(
        json.dumps(read_json(verify_ref(result.experiment_config, root)))
    )
    environment = read_json(verify_ref(result.environment_manifest, root))
    if result.status == "accepted":
        validate_environment(environment)
    _require_replay_implementation(environment)
    sources = environment["source_configs"]
    source_names = {
        "bracket_default.yaml",
        "gmsh_bracket_v1.yaml",
        "calculix_bracket_v1.yaml",
        "closed_loop_thickness_v1.yaml",
    }
    if sources.keys() != source_names:
        raise ValueError("incomplete source configuration snapshot")
    for name, source_ref in sources.items():
        path = verify_ref(source_ref, root)
        if path != root / "source_configs" / name or (
            source_ref["sha256"] != environment["source_file_sha256"][f"configs/{name}"]
        ):
            raise ValueError("source configuration snapshot identity mismatch")
    validate_config_snapshot(config, root / "source_configs/closed_loop_thickness_v1.yaml")
    # All effective analysis checks use the retained source snapshots, not today's checkout.
    evidence_config = config.model_copy(update={"repo_root": root})
    history, identities, numerical = [], [], []
    previous_ref = None
    for index, ref in enumerate(result.iteration_manifests):
        manifest_path = verify_canonical_ref(
            ref, root, root / "iterations" / f"{index:03}" / "iteration_manifest.json"
        )
        manifest = IterationManifest.model_validate(read_json(manifest_path))
        if manifest.iteration != index or manifest.previous_iteration_manifest != previous_ref:
            raise ValueError("broken iteration manifest chain")
        previous_ref = ref
        directory = manifest_path.parent
        listed_paths = set()
        for artifact in manifest.artifacts:
            verified = verify_ref(artifact, root)
            if verified in listed_paths:
                raise ValueError("duplicate artifact reference")
            listed_paths.add(verified)
        actual_paths = {p.resolve() for p in directory.rglob("*") if p.is_file()} - {manifest_path}
        if listed_paths != actual_paths:
            raise ValueError("incomplete iteration artifact inventory")
        canonical_refs = {
            "parameters": "parameters.json",
            "decision": "decision.json",
            "effective_analysis": "effective_analysis.json",
            "cad_manifest": "cad/bracket_v1_manifest.json",
            "mesh_manifest": "mesh/bracket_v1_mesh_manifest.json",
            "physics_result": "fea/physics_result.json",
        }
        for field, name in canonical_refs.items():
            reference = getattr(manifest, field)
            if reference is not None:
                path = verify_canonical_ref(reference, root, directory / name)
                if path not in listed_paths:
                    raise ValueError(f"misdirected {field} reference")
        params = LoopParameters.model_validate(read_json(verify_ref(manifest.parameters, root)))
        for item in (
            manifest.effective_analysis,
            manifest.cad_manifest,
            manifest.mesh_manifest,
            manifest.physics_result,
        ):
            if item is not None:
                verify_ref(item, root)
        evaluation = CandidateEvaluation(
            iteration=index,
            parameters=params,
            evaluation_status=manifest.evaluation_status,
            metrics=manifest.metrics,
            constraint_checks=manifest.constraint_checks,
            structural_feasible=manifest.structural_feasible,
            failure=manifest.failure,
        )
        if evaluation.evaluation_status == "completed":
            if collect_evaluation(params, evidence_config, directory) != evaluation:
                raise ValueError("manifest metrics differ from engineering evidence")
        history.append(evaluation)
        decision = ControllerDecision.model_validate(read_json(verify_ref(manifest.decision, root)))
        if decision != decide(config, history):
            raise ValueError("controller decision does not replay from retained evidence")
        if manifest.terminal != (decision.action == "stop"):
            raise ValueError("terminal manifest/decision mismatch")
        if index < len(result.iteration_manifests) - 1 and manifest.terminal:
            raise ValueError("iterations exist after a terminal decision")
        physics = (
            read_json(verify_ref(manifest.physics_result, root)) if manifest.physics_result else {}
        )
        cad = read_json(verify_ref(manifest.cad_manifest, root)) if manifest.cad_manifest else {}
        if evaluation.evaluation_status == "completed":
            backend = read_json(directory / "cad_backend.json")
            versions = environment["runtime_versions"]
            executable = environment["discovered_executables"]["calculix"]["path"]
            if (
                backend["freecad_version"] != versions["freecad"]
                or backend["opencascade_version"] != versions["opencascade"]
                or physics["invocation"]["executable"] != executable
            ):
                raise ValueError("iteration backend identity differs from recorded environment")
        identity = {
            "parameters": params.model_dump(),
            "decision": decision.model_dump(),
            "evaluation_status": evaluation.evaluation_status,
            "constraint_checks": evaluation.constraint_checks.model_dump(),
            "cad_fingerprint": cad.get("cad_fingerprint"),
        }
        for key in (
            "mesh_provenance",
            "analysis_definition",
            "analysis_fingerprint",
            "calculix_input_sha256",
            "boundary_condition",
            "load",
            "solver_version",
        ):
            identity[key] = physics.get(key)
        for key in ("max_displacement", "max_von_mises_stress"):
            identity[key] = {k: v for k, v in (physics.get(key) or {}).items() if k != "value"}
        identities.append(identity)
        values = {"metrics": evaluation.metrics.model_dump()}
        for key in ("reaction_force_n", "equilibrium_residual_n", "diagnostics"):
            values[key] = physics.get(key)
        numerical.append(values)
    if not history or len(history) != result.evaluation_count:
        raise ValueError("evaluation count mismatch or empty trial")
    terminal = decide(config, history)
    if terminal.action != "stop" or result.termination_reason != terminal.reason:
        raise ValueError("result does not match terminal decision")
    if result.best_feasible_iteration != terminal.best_feasible_iteration:
        raise ValueError("result best feasible selection mismatch")
    if result.initial_mass_g != history[0].metrics.mass_g:
        raise ValueError("initial mass mismatch")
    expected_status = {
        "lower_bound_reached": "accepted",
        "structural_boundary_reached": "accepted",
        "initial_infeasible": "no_feasible_design",
        "budget_exhausted": "budget_exhausted",
    }.get(terminal.reason, "error")
    if result.status != expected_status:
        raise ValueError("result status mismatch")
    if result.status == "accepted":
        best = history[terminal.best_feasible_iteration]
        if (
            result.accepted_iteration != best.iteration
            or result.accepted_parameters != best.parameters
        ):
            raise ValueError("accepted design mismatch")
        if result.accepted_mass_g != best.metrics.mass_g:
            raise ValueError("accepted mass mismatch")
        reduction = (result.initial_mass_g - best.metrics.mass_g) / result.initial_mass_g
        if result.mass_reduction_fraction != reduction:
            raise ValueError("mass reduction mismatch")
    # Paths and clocks are not software/numerical identity. Runtime versions remain exact.
    config_identity = config.model_dump(mode="json")
    config_identity.pop("repo_root", None)
    identity_environment = {
        key: value
        for key, value in environment.items()
        if key not in ("source_configs", "created_at", "elapsed_seconds", "repository_root")
    }
    return {
        "identity": {
            "config": config_identity,
            "environment": identity_environment,
            "source_configs": {k: v["sha256"] for k, v in sources.items()},
            "iterations": identities,
            "status": result.status,
            "accepted_iteration": result.accepted_iteration,
            "termination_reason": result.termination_reason,
        },
        "numerical": numerical,
        "result": result.model_dump(mode="json"),
        "clean_commit": environment["repository_dirty"] is False,
    }


def verify_experiment(directory: Path) -> dict:
    """Read only: recompute acceptance, never trust a saved 'passed' flag."""
    directory = Path(directory).resolve()
    paths = [directory / f"trial-{index:03}" for index in (1, 2, 3)]
    trials, mismatches, maximum = [], [], 0.0
    for path in paths:
        try:
            trials.append(verify_trial(path))
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
            mismatches.append({"trial": str(path), "message": str(exc)})
    if len(trials) == 3:
        for first_index, repeated_index in combinations(range(3), 2):
            try:
                maximum = max(maximum, compare_trials(trials[first_index], trials[repeated_index]))
            except ValueError as exc:
                mismatches.append(
                    {
                        "trial": str(paths[repeated_index]),
                        "compared_with": str(paths[first_index]),
                        "message": str(exc),
                    }
                )
        for path, trial in zip(paths, trials, strict=True):
            result = trial["result"]
            if not trial["clean_commit"]:
                mismatches.append(
                    {"trial": str(path), "message": "not a clean implementation commit"}
                )
            if result["status"] != "accepted" or not (
                result["evaluation_count"] >= 2
                and (result["mass_reduction_fraction"] or 0) > 0
                and result["accepted_parameters"]["thickness_mm"] < 8
            ):
                mismatches.append(
                    {"trial": str(path), "message": "mass-reduction hypothesis unsupported"}
                )
    return {
        "schema_version": "1.0",
        "status": "passed" if not mismatches else "failed",
        "trial_paths": [str(p) for p in paths],
        "verified_trial_count": len(trials),
        "tolerance": TOLERANCE,
        "maximum_absolute_difference": maximum,
        "identity_fields": [
            "configuration",
            "environment",
            "source_config_hashes",
            "parameters",
            "decisions",
            "CAD fingerprint",
            "mesh identity",
            "analysis identity",
            "input hash",
            "load",
            "boundary",
            "selection",
        ],
        "numerical_fields": [
            "mass",
            "volume",
            "stress",
            "displacement",
            "reactions",
            "diagnostics",
        ],
        "mismatches": mismatches,
        "trial_results": [trial["result"] for trial in trials],
        "dfam_status": "not_evaluated",
        "full_benchmark_feasible": None,
    }


def run_experiment(config: ExperimentConfig, output_directory: Path) -> dict:
    directory = Path(output_directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    status = subprocess.check_output(
        ["git", "status", "--porcelain=v1"], cwd=config.repo_root, text=True
    ).strip()
    if status:
        report = {
            "status": "failed",
            "mismatches": [{"message": "clean implementation commit required"}],
        }
        write_json(directory / "experiment_report.json", report)
        return report
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(config.repo_root / "src")
    for index in (1, 2, 3):
        args = [
            sys.executable,
            "-m",
            "open_engineering_intelligence.pipeline.closed_loop",
            "--repo-root",
            str(config.repo_root),
            "--output",
            str(directory / f"trial-{index:03}"),
        ]
        try:
            run_process(args, directory, f"trial-{index:03}", 1600, env=environment)
        except (TimeoutError, OSError) as exc:
            write_json(directory / f"trial-{index:03}.failure.json", {"message": str(exc)})
    report = verify_experiment(directory)
    write_json(directory / "repeatability.json", report)
    write_json(
        directory / "experiment_report.json",
        {
            **report,
            "hypothesis_supported": report["status"] == "passed",
            "claim_scope": (
                "structural-only computational baseline; not full DfAM or physical validation"
            ),
        },
    )
    return report
