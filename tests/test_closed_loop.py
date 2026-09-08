"""Pure-Python closed-loop orchestration tests; external engineering tools are faked."""

from __future__ import annotations

from pathlib import Path

import pytest

from open_engineering_intelligence.pipeline.artifact_io import read_json, write_json
from open_engineering_intelligence.pipeline.closed_loop_contracts import (
    ControllerDecision,
    ExperimentConfig,
    failed_evaluation,
    make_completed_evaluation,
)


def _config(repo: Path, *, budget: int = 30) -> ExperimentConfig:
    config_dir = repo / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "bracket_default.yaml": "benchmark: bracket_v1\n",
        "gmsh_bracket_v1.yaml": "meshing: gmsh\n",
        "calculix_bracket_v1.yaml": "solver: calculix\n",
        "closed_loop_thickness_v1.yaml": "evaluation_budget: 30\n",
    }
    for name, text in sources.items():
        (config_dir / name).write_text(text, encoding="utf-8")
    source_dir = repo / "src"
    source_dir.mkdir()
    (source_dir / "implementation.py").write_text("VERSION = 1\n", encoding="utf-8")
    return ExperimentConfig(repo_root=repo, evaluation_budget=budget)


def _fake_evaluator(volumes=None, *, infeasible_at=None, fail_at=None, omit_at=None):
    volumes = volumes or {}
    calls = []

    def evaluate(parameters, config, directory):
        index = int(directory.name)
        calls.append(
            (
                index,
                parameters,
                (directory / "parameters.json").is_file(),
                (directory.parents[1] / "experiment_config.json").is_file()
                and (directory.parents[1] / "environment_manifest.json").is_file(),
            )
        )
        if fail_at == index:
            return failed_evaluation(index, parameters, "solver", "timeout", "timed out")
        write_json(directory / "effective_analysis.json", {"thickness_mm": parameters.thickness_mm})
        write_json(directory / "cad/bracket_v1_manifest.json", {"kind": "cad"})
        write_json(directory / "mesh/bracket_v1_mesh_manifest.json", {"kind": "mesh"})
        if omit_at != index:
            write_json(directory / "fea/physics_result.json", {"solver_version": "2.22"})
        write_json(
            directory / "cad_backend.json",
            {"freecad_version": [1, 0, 0], "opencascade_version": "7.8.1"},
        )
        stress = 26.0 if infeasible_at == index else 20.0
        return make_completed_evaluation(
            index,
            parameters,
            volume_mm3=volumes.get(index, (10_000.0 - 1_000.0 * index)),
            max_von_mises_mpa=stress,
            max_displacement_mm=1.0,
        )

    evaluate.calls = calls
    return evaluate


def _load_result(output: Path):
    from open_engineering_intelligence.pipeline.closed_loop_contracts import ClosedLoopResult

    return ClosedLoopResult.model_validate(read_json(output / "closed_loop_result.json"))


def test_fresh_run_descends_to_boundary_and_retains_linked_evidence(tmp_path: Path) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import run_closed_loop

    config = _config(tmp_path / "repo")
    evaluator = _fake_evaluator()
    output = tmp_path / "trial"

    result = run_closed_loop(config, output, evaluator=evaluator)

    assert result.status == "accepted"
    assert result.termination_reason == "lower_bound_reached"
    assert result.evaluation_count == 5
    assert [call[1].thickness_mm for call in evaluator.calls] == [8.0, 7.0, 6.0, 5.0, 4.0]
    assert all(call[2] for call in evaluator.calls)
    assert all(call[3] for call in evaluator.calls)
    assert result.accepted_iteration == 4
    assert result.initial_mass_g == pytest.approx(12.4)
    assert result.accepted_mass_g == pytest.approx(7.44)
    assert result.mass_reduction_fraction == pytest.approx(0.4)

    first = read_json(output / "iterations/000/iteration_manifest.json")
    second = read_json(output / "iterations/001/iteration_manifest.json")
    assert first["previous_iteration_manifest"] is None
    assert second["previous_iteration_manifest"]["path"] == (
        "iterations/000/iteration_manifest.json"
    )
    assert first["terminal"] is False
    assert read_json(output / "iterations/004/iteration_manifest.json")["terminal"] is True
    assert {ref["path"] for ref in first["artifacts"]} == {
        "iterations/000/cad/bracket_v1_manifest.json",
        "iterations/000/cad_backend.json",
        "iterations/000/decision.json",
        "iterations/000/effective_analysis.json",
        "iterations/000/fea/physics_result.json",
        "iterations/000/parameters.json",
        "iterations/000/mesh/bracket_v1_mesh_manifest.json",
    }

    environment = read_json(output / "environment_manifest.json")
    assert set(environment["source_configs"]) == {
        "bracket_default.yaml",
        "gmsh_bracket_v1.yaml",
        "calculix_bracket_v1.yaml",
        "closed_loop_thickness_v1.yaml",
    }
    assert environment["source_tree_consistent"] is True
    assert environment["runtime_versions"]["freecad"] == [1, 0, 0]
    assert environment["runtime_versions"]["opencascade"] == "7.8.1"
    assert environment["runtime_versions"]["calculix"] == "2.22"
    for ref in environment["source_configs"].values():
        assert (output / ref["path"]).is_file()


def test_existing_output_directory_is_refused_before_any_evaluation(tmp_path: Path) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import run_closed_loop

    config = _config(tmp_path / "repo")
    output = tmp_path / "trial"
    output.mkdir()
    evaluator = _fake_evaluator()

    with pytest.raises(FileExistsError):
        run_closed_loop(config, output, evaluator=evaluator)

    assert evaluator.calls == []


def test_backend_failure_after_feasible_candidate_remains_error_and_retains_best(
    tmp_path: Path,
) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import run_closed_loop

    config = _config(tmp_path / "repo")
    output = tmp_path / "trial"

    result = run_closed_loop(config, output, evaluator=_fake_evaluator(fail_at=1))

    assert result.status == "error"
    assert result.termination_reason == "evaluation_failed"
    assert result.evaluation_count == 2
    assert result.best_feasible_iteration == 0
    assert result.accepted_iteration is None
    assert result.accepted_parameters is None
    assert result.accepted_mass_g is None
    assert read_json(output / "iterations/001/iteration_manifest.json")["failure"] == {
        "stage": "solver",
        "code": "timeout",
        "message": "timed out",
    }


def test_budget_guard_stops_without_a_third_expensive_evaluation(tmp_path: Path) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import run_closed_loop

    evaluator = _fake_evaluator()

    result = run_closed_loop(
        _config(tmp_path / "repo", budget=2), tmp_path / "trial", evaluator=evaluator
    )

    assert result.status == "budget_exhausted"
    assert result.termination_reason == "budget_exhausted"
    assert len(evaluator.calls) == 2
    assert result.best_feasible_iteration == 1


def test_budget_guard_rejects_an_injected_proposal_after_the_last_allowed_evaluation(
    tmp_path: Path,
) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import run_closed_loop

    evaluator = _fake_evaluator()

    def ignores_budget(experiment_config, history):
        current = history[-1]
        return ControllerDecision(
            schema_version="1.0",
            controller="thickness_descent_v1",
            iteration=current.iteration,
            input_parameters=current.parameters,
            current_evaluation="feasible",
            violated_constraints=[],
            action="decrease_thickness",
            reason="feasible_try_thinner",
            next_parameters=current.parameters.model_copy(update={"thickness_mm": 7.0}),
            best_feasible_iteration=0,
        )

    output = tmp_path / "trial"
    result = run_closed_loop(
        _config(tmp_path / "repo", budget=1),
        output,
        evaluator=evaluator,
        controller=ignores_budget,
    )

    assert result.status == "error"
    assert result.termination_reason == "invalid_proposal"
    assert len(evaluator.calls) == 1
    assert result.best_feasible_iteration == 0
    manifest = read_json(output / "iterations/000/iteration_manifest.json")
    assert manifest["terminal"] is True
    assert manifest["evaluation_status"] == "completed"
    assert manifest["failure"] is None


def test_missing_completed_artifact_is_converted_to_terminal_evaluation_error(
    tmp_path: Path,
) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import run_closed_loop

    output = tmp_path / "trial"
    result = run_closed_loop(
        _config(tmp_path / "repo"), output, evaluator=_fake_evaluator(omit_at=0)
    )

    manifest = read_json(output / "iterations/000/iteration_manifest.json")
    assert result.status == "error"
    assert result.evaluation_count == 1
    assert manifest["evaluation_status"] == "failed"
    assert manifest["failure"]["code"] == "missing_artifact"
    assert manifest["physics_result"] is None


def test_stale_evaluation_identity_stops_without_calling_controller(tmp_path: Path) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import run_closed_loop

    config = _config(tmp_path / "repo")
    good = _fake_evaluator()
    controller_calls = []

    def stale(parameters, experiment_config, directory):
        good(parameters, experiment_config, directory)
        return make_completed_evaluation(99, parameters, 10_000.0, 20.0, 1.0)

    def controller(experiment_config, history):
        controller_calls.append(history)
        raise AssertionError("controller must not consume stale evidence")

    result = run_closed_loop(config, tmp_path / "trial", evaluator=stale, controller=controller)

    assert result.status == "error"
    assert result.termination_reason == "provenance_mismatch"
    assert result.evaluation_count == 1
    assert controller_calls == []


def test_invalid_controller_proposal_is_recorded_without_extra_evaluation(tmp_path: Path) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import run_closed_loop

    config = _config(tmp_path / "repo")
    evaluator = _fake_evaluator()

    def duplicate(experiment_config, history):
        current = history[-1]
        return ControllerDecision(
            schema_version="1.0",
            controller="thickness_descent_v1",
            iteration=current.iteration,
            input_parameters=current.parameters,
            current_evaluation="feasible",
            violated_constraints=[],
            action="decrease_thickness",
            reason="feasible_try_thinner",
            next_parameters=current.parameters,
            best_feasible_iteration=current.iteration,
        )

    result = run_closed_loop(config, tmp_path / "trial", evaluator=evaluator, controller=duplicate)

    assert result.status == "error"
    assert result.termination_reason == "invalid_proposal"
    assert len(evaluator.calls) == 1
    decision = read_json(tmp_path / "trial/iterations/000/decision.json")
    assert decision["action"] == "stop"
    assert decision["reason"] == "invalid_proposal"
    manifest = read_json(tmp_path / "trial/iterations/000/iteration_manifest.json")
    assert manifest["evaluation_status"] == "failed"
    assert manifest["failure"]["stage"] == "controller"


def test_well_shaped_early_stop_is_rejected_without_masking_the_evaluated_best(
    tmp_path: Path,
) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import run_closed_loop

    evaluator = _fake_evaluator()

    def early_stop(experiment_config, history):
        current = history[-1]
        return ControllerDecision(
            schema_version="1.0",
            controller="thickness_descent_v1",
            iteration=current.iteration,
            input_parameters=current.parameters,
            current_evaluation="feasible",
            violated_constraints=[],
            action="stop",
            reason="lower_bound_reached",
            next_parameters=None,
            best_feasible_iteration=0,
        )

    output = tmp_path / "trial"
    result = run_closed_loop(
        _config(tmp_path / "repo"),
        output,
        evaluator=evaluator,
        controller=early_stop,
    )

    assert result.status == "error"
    assert result.termination_reason == "invalid_proposal"
    assert result.best_feasible_iteration == 0
    assert len(evaluator.calls) == 1
    decision = read_json(output / "iterations/000/decision.json")
    assert decision["action"] == "stop"
    assert decision["reason"] == "invalid_proposal"
    manifest = read_json(output / "iterations/000/iteration_manifest.json")
    assert manifest["evaluation_status"] == "completed"
    assert manifest["failure"] is None
    assert manifest["terminal"] is True


def test_malformed_controller_result_becomes_terminal_error_decision(tmp_path: Path) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import run_closed_loop

    evaluator = _fake_evaluator()

    def malformed(experiment_config, history):
        return {"action": "launch_unbounded_search"}

    output = tmp_path / "trial"
    result = run_closed_loop(
        _config(tmp_path / "repo"), output, evaluator=evaluator, controller=malformed
    )

    assert result.status == "error"
    assert len(evaluator.calls) == 1
    assert read_json(output / "iterations/000/decision.json")["reason"] == "invalid_proposal"
    assert read_json(output / "iterations/000/iteration_manifest.json")["failure"]["stage"] == (
        "controller"
    )


def test_controller_exception_becomes_a_retained_terminal_error(tmp_path: Path) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import run_closed_loop

    def broken_controller(experiment_config, history):
        raise RuntimeError("controller crashed")

    output = tmp_path / "trial"
    result = run_closed_loop(
        _config(tmp_path / "repo"),
        output,
        evaluator=_fake_evaluator(),
        controller=broken_controller,
    )

    assert result.status == "error"
    assert result.termination_reason == "invalid_proposal"
    manifest = read_json(output / "iterations/000/iteration_manifest.json")
    assert manifest["failure"] == {
        "stage": "controller",
        "code": "invalid_proposal",
        "message": "controller crashed",
    }


def test_source_change_during_run_prevents_acceptance(tmp_path: Path) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import run_closed_loop

    config = _config(tmp_path / "repo")
    base = _fake_evaluator(infeasible_at=1)

    def mutating(parameters, experiment_config, directory):
        result = base(parameters, experiment_config, directory)
        if int(directory.name) == 0:
            source = config.repo_root / "src/implementation.py"
            source.write_text("VERSION = 2\n", encoding="utf-8")
        return result

    output = tmp_path / "trial"
    result = run_closed_loop(config, output, evaluator=mutating)

    assert result.status == "error"
    assert result.termination_reason == "provenance_mismatch"
    assert result.best_feasible_iteration == 0
    environment = read_json(output / "environment_manifest.json")
    assert environment["source_tree_consistent"] is False
    assert environment["source_tree_sha256"] != environment["source_tree_sha256_end"]


@pytest.mark.parametrize(
    ("status", "expected"),
    [("accepted", 0), ("no_feasible_design", 1), ("budget_exhausted", 1), ("error", 1)],
)
def test_normal_cli_exit_status_only_accepts_success(status: str, expected: int) -> None:
    from open_engineering_intelligence.pipeline.closed_loop import _normal_exit_code

    assert _normal_exit_code(status) == expected
