"""Bounded deterministic structural-thinning runner and command-line entry point."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from open_engineering_intelligence.optimization.thickness_controller import decide
from open_engineering_intelligence.pipeline.artifact_io import (
    artifact_ref,
    read_json,
    sha256,
    write_json,
)
from open_engineering_intelligence.pipeline.closed_loop_contracts import (
    CONTROLLER_NAME,
    EXPERIMENT_NAME,
    SCHEMA_VERSION,
    ArtifactRef,
    CandidateEvaluation,
    ClosedLoopResult,
    ControllerDecision,
    ExperimentConfig,
    IterationManifest,
    LoopParameters,
    failed_evaluation,
    load_experiment_config,
)
from open_engineering_intelligence.pipeline.structural_evaluator import evaluate_candidate

SOURCE_CONFIG_NAMES = (
    "bracket_default.yaml",
    "gmsh_bracket_v1.yaml",
    "calculix_bracket_v1.yaml",
    "closed_loop_thickness_v1.yaml",
)
REQUIRED_COMPLETED_ARTIFACTS = {
    "effective_analysis": "effective_analysis.json",
    "cad_manifest": "cad/bracket_v1_manifest.json",
    "mesh_manifest": "mesh/bracket_v1_mesh_manifest.json",
    "physics_result": "fea/physics_result.json",
}


def _ref(path: Path, root: Path) -> ArtifactRef:
    return ArtifactRef.model_validate(artifact_ref(path, root))


def _file_identity(path: Path | None) -> dict:
    if path is None or not path.is_file():
        return {"path": str(path) if path is not None else None, "sha256": None}
    try:
        digest = sha256(path)
    except OSError:
        digest = None
    return {"path": str(path.resolve()), "sha256": digest}


def _discover_executable(
    environment_name: str,
    names: tuple[str, ...],
    fallback: Path | None = None,
) -> Path | None:
    configured = os.environ.get(environment_name)
    if configured and Path(configured).is_file():
        return Path(configured).resolve()
    for name in names:
        candidate = shutil.which(name)
        if candidate:
            return Path(candidate).resolve()
    if fallback is not None and fallback.is_file():
        return fallback.resolve()
    return None


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _git_provenance(repo_root: Path) -> dict:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, text=True, stderr=subprocess.DEVNULL
        ).strip()
        status_text = subprocess.check_output(
            ["git", "status", "--porcelain=v1"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        tracked_diff = subprocess.check_output(
            ["git", "diff", "--binary", "HEAD"], cwd=repo_root, stderr=subprocess.DEVNULL
        )
        changed_names = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).splitlines()
    except (OSError, subprocess.CalledProcessError):
        return {
            "git_available": False,
            "repository_commit": "unavailable",
            "repository_dirty": True,
            "repository_status": None,
            "tracked_diff_sha256": None,
            "tracked_diff_file_sha256": None,
        }
    changed_hashes = {}
    for name in changed_names:
        path = repo_root / name
        changed_hashes[name] = sha256(path) if path.is_file() else None
    return {
        "git_available": True,
        "repository_commit": commit,
        "repository_dirty": bool(status_text),
        "repository_status": status_text.splitlines(),
        "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
        "tracked_diff_file_sha256": changed_hashes,
    }


def _source_hashes(repo_root: Path) -> tuple[dict[str, str], str]:
    paths = {repo_root / "configs" / name for name in SOURCE_CONFIG_NAMES}
    source_directory = repo_root / "src"
    if source_directory.is_dir():
        paths.update(path for path in source_directory.rglob("*.py") if path.is_file())
    paths.update(
        path
        for path in (repo_root / "pyproject.toml", repo_root / "requirements.txt")
        if path.is_file()
    )
    identities = {
        path.relative_to(repo_root).as_posix(): sha256(path)
        for path in sorted(paths, key=lambda item: item.relative_to(repo_root).as_posix())
    }
    digest = hashlib.sha256()
    for name, value in identities.items():
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(value.encode("ascii"))
        digest.update(b"\n")
    return identities, digest.hexdigest()


def _snapshot_environment(config: ExperimentConfig, root: Path) -> dict:
    source_directory = root / "source_configs"
    source_directory.mkdir()
    source_refs = {}
    for name in SOURCE_CONFIG_NAMES:
        destination = source_directory / name
        shutil.copyfile(config.repo_root / "configs" / name, destination)
        source_refs[name] = artifact_ref(destination, root)

    source_hashes, tree_hash = _source_hashes(config.repo_root)
    freecad = _discover_executable(
        "FREECAD_CMD",
        ("FreeCADCmd", "freecadcmd", "FreeCADCmd.exe"),
        Path(r"C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe"),
    )
    calculix = _discover_executable("CALCULIX_CCX", ("ccx", "ccx.exe"))
    environment = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository_root": str(config.repo_root),
        **_git_provenance(config.repo_root),
        "source_configs": source_refs,
        "source_file_sha256": source_hashes,
        "source_tree_sha256": tree_hash,
        "source_tree_sha256_end": tree_hash,
        "source_tree_consistent": True,
        "platform": platform.platform(),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": _file_identity(Path(sys.executable)),
        },
        "packages": {
            name: _package_version(name)
            for name in ("open-engineering-intelligence", "pydantic", "PyYAML", "gmsh")
        },
        "discovered_executables": {
            "freecad": {"available": freecad is not None, **_file_identity(freecad)},
            "calculix": {"available": calculix is not None, **_file_identity(calculix)},
        },
        "runtime_versions": {
            "freecad": None,
            "opencascade": None,
            "calculix": None,
        },
        "elapsed_seconds": None,
    }
    write_json(root / "environment_manifest.json", environment)
    return environment


def _runtime_versions(root: Path) -> dict:
    versions = {"freecad": None, "opencascade": None, "calculix": None}
    for directory in sorted((root / "iterations").glob("[0-9][0-9][0-9]")):
        cad_backend = directory / "cad_backend.json"
        if cad_backend.is_file() and versions["freecad"] is None:
            try:
                payload = read_json(cad_backend)
                versions["freecad"] = payload.get("freecad_version")
                versions["opencascade"] = payload.get("opencascade_version")
            except (OSError, ValueError, TypeError):
                pass
        physics = directory / "fea/physics_result.json"
        if physics.is_file() and versions["calculix"] is None:
            try:
                versions["calculix"] = read_json(physics).get("solver_version")
            except (OSError, ValueError, TypeError):
                pass
        if all(value is not None for value in versions.values()):
            break
    return versions


def _best_feasible(history: list[CandidateEvaluation]) -> int | None:
    feasible = [item for item in history if item.structural_feasible is True]
    if not feasible:
        return None
    return min(
        feasible,
        key=lambda item: (
            item.metrics.mass_g,
            item.parameters.thickness_mm,
            item.iteration,
        ),
    ).iteration


def _error_decision(
    parameters: LoopParameters,
    iteration: int,
    history: list[CandidateEvaluation],
    reason: str,
) -> ControllerDecision:
    return ControllerDecision(
        schema_version=SCHEMA_VERSION,
        controller=CONTROLLER_NAME,
        iteration=iteration,
        input_parameters=parameters,
        current_evaluation="error",
        violated_constraints=[],
        action="stop",
        reason=reason,
        next_parameters=None,
        best_feasible_iteration=_best_feasible(history),
    )


def _evaluate_safely(evaluator, parameters, config, directory, iteration):
    try:
        raw = evaluator(parameters, config, directory)
        evaluation = CandidateEvaluation.model_validate(raw)
    except Exception as exc:
        return failed_evaluation(
            iteration, parameters, "evaluation", "evaluation_failed", str(exc) or type(exc).__name__
        )
    if evaluation.iteration != iteration or evaluation.parameters != parameters:
        return failed_evaluation(
            iteration,
            parameters,
            "provenance",
            "evaluation_identity_mismatch",
            "evaluator returned a different iteration or parameter identity",
        )
    if evaluation.evaluation_status == "completed":
        missing = [
            relative
            for relative in REQUIRED_COMPLETED_ARTIFACTS.values()
            if not (directory / relative).is_file()
        ]
        if missing:
            return failed_evaluation(
                iteration,
                parameters,
                "provenance",
                "missing_artifact",
                "completed evaluation omitted required artifacts: " + ", ".join(missing),
            )
    return evaluation


def _validated_decision(controller, config, history):
    try:
        raw_decision = controller(config, tuple(history))
        decision = ControllerDecision.model_validate(raw_decision)
    except Exception as exc:
        return None, str(exc) or type(exc).__name__, True
    try:
        expected = decide(config, tuple(history))
        if decision != expected:
            raise ValueError("controller decision differs from the frozen policy")
        return decision, None, False
    except (ValueError, TypeError, AssertionError) as exc:
        return None, str(exc) or type(exc).__name__, False


def _optional_ref(directory: Path, relative: str, root: Path) -> ArtifactRef | None:
    path = directory / relative
    return _ref(path, root) if path.is_file() else None


def _write_manifest(
    root: Path,
    directory: Path,
    evaluation: CandidateEvaluation,
    decision: ControllerDecision,
    previous: ArtifactRef | None,
) -> ArtifactRef:
    decision_path = directory / "decision.json"
    write_json(decision_path, decision)
    files = sorted(
        (path for path in directory.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    manifest = IterationManifest(
        schema_version=SCHEMA_VERSION,
        iteration=evaluation.iteration,
        previous_iteration_manifest=previous,
        parameters=_ref(directory / "parameters.json", root),
        effective_analysis=_optional_ref(directory, "effective_analysis.json", root),
        evaluation_status=evaluation.evaluation_status,
        metrics=evaluation.metrics,
        constraint_checks=evaluation.constraint_checks,
        structural_feasible=evaluation.structural_feasible,
        dfam_status="not_evaluated",
        full_benchmark_feasible=None,
        cad_manifest=_optional_ref(directory, "cad/bracket_v1_manifest.json", root),
        mesh_manifest=_optional_ref(directory, "mesh/bracket_v1_mesh_manifest.json", root),
        physics_result=_optional_ref(directory, "fea/physics_result.json", root),
        decision=_ref(decision_path, root),
        artifacts=[_ref(path, root) for path in files],
        failure=evaluation.failure,
        terminal=decision.action == "stop",
    )
    path = directory / "iteration_manifest.json"
    write_json(path, manifest)
    return _ref(path, root)


def _status_for(reason: str) -> str:
    return {
        "lower_bound_reached": "accepted",
        "structural_boundary_reached": "accepted",
        "initial_infeasible": "no_feasible_design",
        "budget_exhausted": "budget_exhausted",
    }.get(reason, "error")


def run_closed_loop(
    experiment_config: ExperimentConfig,
    output_directory: Path,
    *,
    evaluator=evaluate_candidate,
    controller=decide,
) -> ClosedLoopResult:
    """Run one fresh bounded trial and retain every evaluated candidate."""
    config = ExperimentConfig.model_validate(experiment_config)
    root = Path(output_directory).resolve()
    root.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    write_json(root / "experiment_config.json", config)
    environment = _snapshot_environment(config, root)

    history: list[CandidateEvaluation] = []
    manifest_refs: list[ArtifactRef] = []
    parameters = config.initial_parameters
    terminal_decision = None

    while len(history) < config.evaluation_budget:
        iteration = len(history)
        directory = root / "iterations" / f"{iteration:03d}"
        directory.mkdir(parents=True, exist_ok=False)
        write_json(directory / "parameters.json", parameters)
        evaluation = _evaluate_safely(evaluator, parameters, config, directory, iteration)
        history.append(evaluation)

        identity_failure = (
            evaluation.failure is not None
            and evaluation.failure.code == "evaluation_identity_mismatch"
        )
        if identity_failure:
            decision = _error_decision(parameters, iteration, history[:-1], "provenance_mismatch")
        else:
            decision, controller_failure, malformed = _validated_decision(
                controller, config, history
            )
            if decision is None:
                if malformed:
                    evaluation = failed_evaluation(
                        iteration,
                        parameters,
                        "controller",
                        "invalid_proposal",
                        controller_failure or "controller returned an invalid proposal",
                    )
                    history[-1] = evaluation
                    decision_history = history[:-1]
                else:
                    decision_history = history
                decision = _error_decision(
                    parameters, iteration, decision_history, "invalid_proposal"
                )

        manifest_ref = _write_manifest(
            root,
            directory,
            history[-1],
            decision,
            manifest_refs[-1] if manifest_refs else None,
        )
        manifest_refs.append(manifest_ref)
        if decision.action == "stop":
            terminal_decision = decision
            break
        assert decision.next_parameters is not None
        parameters = decision.next_parameters

    if terminal_decision is None:
        current = history[-1]
        terminal_decision = _error_decision(
            current.parameters, current.iteration, history, "invalid_proposal"
        )
        raise RuntimeError("evaluation budget ended without a terminal controller decision")

    end_hashes, end_tree_hash = _source_hashes(config.repo_root)
    environment["source_file_sha256_end"] = end_hashes
    environment["source_tree_sha256_end"] = end_tree_hash
    environment["source_tree_consistent"] = end_tree_hash == environment["source_tree_sha256"]
    environment["runtime_versions"] = _runtime_versions(root)
    environment["elapsed_seconds"] = time.monotonic() - started
    write_json(root / "environment_manifest.json", environment)

    reason = terminal_decision.reason
    if not environment["source_tree_consistent"]:
        reason = "provenance_mismatch"
    status = _status_for(reason)
    best_iteration = terminal_decision.best_feasible_iteration
    initial_mass = history[0].metrics.mass_g if history else None
    accepted = (
        history[best_iteration]
        if status == "accepted" and best_iteration is not None
        else None
    )
    accepted_mass = accepted.metrics.mass_g if accepted is not None else None
    reduction = None
    if accepted_mass is not None and initial_mass is not None:
        reduction = (initial_mass - accepted_mass) / initial_mass
    result = ClosedLoopResult(
        schema_version=SCHEMA_VERSION,
        experiment=EXPERIMENT_NAME,
        controller=CONTROLLER_NAME,
        status=status,
        termination_reason=reason,
        experiment_config=_ref(root / "experiment_config.json", root),
        environment_manifest=_ref(root / "environment_manifest.json", root),
        evaluation_count=len(history),
        iteration_manifests=manifest_refs,
        best_feasible_iteration=best_iteration,
        accepted_iteration=accepted.iteration if accepted is not None else None,
        accepted_parameters=accepted.parameters if accepted is not None else None,
        initial_mass_g=initial_mass,
        accepted_mass_g=accepted_mass,
        mass_reduction_fraction=reduction,
        dfam_status="not_evaluated",
        full_benchmark_feasible=None,
    )
    write_json(root / "closed_loop_result.json", result)
    return result


def _normal_exit_code(status: str) -> int:
    return 0 if status == "accepted" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--experiment", action="store_true")
    parser.add_argument("--verify", type=Path)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
    )
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.verify is not None:
            if args.output is not None or args.experiment:
                raise ValueError("--verify cannot be combined with --output or --experiment")
            from open_engineering_intelligence.pipeline.experiment import verify_experiment

            report = verify_experiment(args.verify)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report["status"] == "passed" else 1
        if args.output is None:
            raise ValueError("--output is required unless --verify is used")
        config = load_experiment_config(args.repo_root.resolve())
        if args.experiment:
            from open_engineering_intelligence.pipeline.experiment import run_experiment

            report = run_experiment(config, args.output)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report["status"] == "passed" else 1
        result = run_closed_loop(config, args.output)
        print(result.model_dump_json(indent=2))
        return _normal_exit_code(result.status)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"closed-loop command failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
