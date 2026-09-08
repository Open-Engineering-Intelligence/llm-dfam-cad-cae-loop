"""Issue #6 structural evaluation; existing CAD/mesh/solver adapters stay unchanged."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

from open_engineering_intelligence.cae.calculix_solver import (
    SANITY_CHECKS,
    CalculiXStaticSolver,
    _mesh_provenance,
    analysis_definition,
    analysis_fingerprint,
    discover_calculix_executable,
    load_calculix_static_config,
    parse_gmsh_msh,
    select_fixed_nodes,
    select_load_nodes,
)
from open_engineering_intelligence.cae.gmsh_mesher import GmshMesher, load_gmsh_meshing_config
from open_engineering_intelligence.pipeline.artifact_io import (
    read_json,
    run_process,
    sha256,
    write_json,
)
from open_engineering_intelligence.pipeline.closed_loop_contracts import (
    CandidateEvaluation,
    ExperimentConfig,
    LoopParameters,
    failed_evaluation,
    make_completed_evaluation,
    validate_parameters,
)


def discover_freecad() -> Path:
    candidate = (
        os.environ.get("FREECAD_CMD") or shutil.which("FreeCADCmd") or shutil.which("freecadcmd")
    )
    if not candidate:
        standard = Path(r"C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe")
        candidate = str(standard) if standard.is_file() else None
    if not candidate or not Path(candidate).is_file():
        raise RuntimeError("FreeCADCmd unavailable; set FREECAD_CMD")
    return Path(candidate).resolve()


def effective_config(parameters: LoopParameters, repo_root: Path):
    folder = "configs" if (repo_root / "configs").is_dir() else "source_configs"
    base = load_calculix_static_config(repo_root / folder / "calculix_bracket_v1.yaml")
    return replace(
        base,
        load_z_mm=parameters.thickness_mm,
        load_y_range_mm=(-parameters.width_mm / 2, parameters.width_mm / 2),
    )


def physics_metrics(result: dict) -> tuple[float, float]:
    if result["solver_status"] != "succeeded" or result["solver_version"] != "2.22":
        raise ValueError("physics evaluation did not succeed with CalculiX 2.22")
    checks = result["sanity_checks"]
    if set(checks) != set(SANITY_CHECKS) or any(checks[k] is not True for k in SANITY_CHECKS):
        raise ValueError("missing or failed physics sanity checks")
    stress, displacement = result["max_von_mises_stress"], result["max_displacement"]
    if stress["unit"] != "MPa" or displacement["unit"] != "mm":
        raise ValueError("incorrect engineering units")
    if stress["position"] != "integration_point":
        raise ValueError("stress must be measured at integration points")
    values = (stress["value"], displacement["value"])
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("invalid engineering metrics")
    return values


def collect_evaluation(parameters, config, directory: Path) -> CandidateEvaluation:
    """Validate the candidate-to-CAD-to-mesh-to-analysis chain before using feedback."""
    for name in ("bracket_v1.FCStd", "bracket_v1.step", "bracket_v1.stl"):
        artifact = directory / "cad" / name
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise ValueError(f"missing or empty CAD artifact: {name}")
    backend = read_json(directory / "cad_backend.json")
    if (
        not isinstance(backend.get("freecad_version"), list)
        or len(backend["freecad_version"]) < 3
        or not isinstance(backend.get("opencascade_version"), str)
        or not backend["opencascade_version"]
    ):
        raise ValueError("missing FreeCAD/OpenCascade version evidence")
    cad = read_json(directory / "cad/bracket_v1_manifest.json")
    expected_artifacts = {
        "freecad_document": "bracket_v1.FCStd",
        "step": "bracket_v1.step",
        "stl": "bracket_v1.stl",
    }
    if cad["artifact_paths"] != expected_artifacts:
        raise ValueError("CAD artifact names mismatch")
    for key, name in expected_artifacts.items():
        if cad["artifact_file_sizes_bytes"][key] != (directory / "cad" / name).stat().st_size:
            raise ValueError("CAD artifact size mismatch")
    mesh = read_json(directory / "mesh/bracket_v1_mesh_manifest.json")
    physics = read_json(directory / "fea/physics_result.json")
    invocation = physics["invocation"]
    if (
        invocation["return_code"] != 0
        or invocation["num_threads"] != 1
        or invocation["discovery"] not in ("explicit_path", "environment", "path")
        or not invocation["executable"]
        or not Path(invocation["executable"]).is_absolute()
        or invocation["timeout_seconds"] != 120
        or Path(invocation["cwd"]).name != "fea"
        or Path(invocation["cwd"]).parent.name != directory.name
        or invocation["arguments"] != [invocation["executable"], "-i", "bracket_v1_static"]
    ):
        raise ValueError("invalid solver invocation provenance")
    if cad["parameters"] != parameters.model_dump() or cad["shape_valid"] is not True:
        raise ValueError("CAD parameters/validity mismatch")
    geometry = cad["cad_fingerprint"]
    if cad["geometry_fingerprint"] != geometry:
        raise ValueError("CAD fingerprint aliases mismatch")
    if mesh["source_geometry_fingerprint"] != geometry:
        raise ValueError("mesh source geometry fingerprint mismatch")
    if physics["input_geometry_fingerprint"] != geometry:
        raise ValueError("physics geometry fingerprint mismatch")
    mesh_path = directory / "mesh/bracket_v1.msh"
    parsed_mesh = parse_gmsh_msh(mesh_path)
    _, provenance = _mesh_provenance(
        mesh_path, directory / "mesh/bracket_v1_mesh_manifest.json", parsed_mesh
    )
    if physics["mesh_provenance"] != provenance:
        raise ValueError("physics mesh provenance mismatch")
    config_folder = "configs" if (config.repo_root / "configs").is_dir() else "source_configs"
    meshing = load_gmsh_meshing_config(config.repo_root / config_folder / "gmsh_bracket_v1.yaml")
    if provenance["gmsh_version"] != "4.15.2" or provenance["meshing_parameters"] != asdict(
        meshing
    ):
        raise ValueError("meshing version/configuration mismatch")
    analysis = effective_config(parameters, config.repo_root)
    expected = analysis_definition(analysis)
    if read_json(directory / "effective_analysis.json") != expected:
        raise ValueError("effective analysis mismatch")
    if physics["analysis_definition"] != expected:
        raise ValueError("physics analysis definition mismatch")
    if physics["analysis_fingerprint"] != analysis_fingerprint(analysis):
        raise ValueError("analysis fingerprint mismatch")
    if physics["calculix_input_sha256"] != sha256(directory / "fea" / f"{analysis.case_name}.inp"):
        raise ValueError("CalculiX input hash mismatch")
    if physics["units"] != {"length": "mm", "force": "N", "stress": "MPa", "displacement": "mm"}:
        raise ValueError("incorrect physics unit system")
    fixed = select_fixed_nodes(parsed_mesh, analysis)
    loaded = select_load_nodes(parsed_mesh, analysis, fixed_node_ids=fixed)
    if physics["boundary_condition"]["node_ids"] != list(fixed):
        raise ValueError("fixed node selection mismatch")
    if physics["load"]["node_ids"] != list(loaded):
        raise ValueError("load node selection mismatch")
    for key in ("x_range_mm", "y_range_mm", "z_mm", "total_force_n"):
        if physics["load"][key] != expected["load"][key]:
            raise ValueError(f"load selection mismatch: {key}")
    if math.dist(physics["load"]["summed_force_n"], [0, 0, -150]) > 1e-9:
        raise ValueError("load resultant mismatch")
    stress, displacement = physics_metrics(physics)
    return make_completed_evaluation(
        int(directory.name),
        parameters,
        geometry["volume_mm3"],
        stress,
        displacement,
    )


def _failure(parameters, directory, stage, code, message):
    result = failed_evaluation(int(directory.name), parameters, stage, code, str(message))
    cad_path = directory / "cad/bracket_v1_manifest.json"
    if cad_path.is_file():
        try:
            cad = read_json(cad_path)
            if (
                cad["parameters"] != parameters.model_dump()
                or cad["shape_valid"] is not True
                or cad["cad_fingerprint"] != cad["geometry_fingerprint"]
            ):
                return result
            volume = cad["cad_fingerprint"]["volume_mm3"]
            if type(volume) in (int, float) and math.isfinite(volume) and volume > 0:
                data = result.model_dump()
                data["metrics"].update(volume_mm3=volume, mass_g=volume * 0.00124)
                result = CandidateEvaluation.model_validate(data)
        except (ValueError, KeyError, TypeError, OSError):
            pass
    return result


def evaluate_candidate(parameters, experiment_config, iteration_directory):
    """Run one fresh isolated worker; revalidate successful evidence in the parent."""
    parameters = LoopParameters.model_validate(parameters)
    config, directory = experiment_config, Path(iteration_directory).resolve()
    validate_parameters(parameters, config)
    if directory.exists() and any(p.name != "parameters.json" for p in directory.iterdir()):
        raise ValueError("candidate directory already contains evaluation evidence")
    if (directory / "parameters.json").exists() and (
        read_json(directory / "parameters.json") != parameters.model_dump()
    ):
        raise ValueError("existing parameter evidence does not match this candidate")
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "parameters.json", parameters)
    write_json(directory / "worker_config.json", config)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(config.repo_root / "src")
    args = [sys.executable, "-m", __name__, "--worker", str(directory)]
    try:
        code = run_process(args, directory, "evaluation", config.timeout_seconds, env=environment)
        result_path = directory / "candidate_evaluation.json"
        if not result_path.is_file():
            raise RuntimeError(f"evaluation worker exited {code} without a result")
        result = CandidateEvaluation.model_validate(read_json(result_path))
        if result.parameters != parameters or result.iteration != int(directory.name):
            raise ValueError("worker parameter identity mismatch")
        if code == 0 and result.evaluation_status == "completed":
            try:
                verified = collect_evaluation(parameters, config, directory)
                if verified != result:
                    raise ValueError("normalized worker result mismatch")
                return verified
            except (ValueError, KeyError, TypeError, OSError) as exc:
                return _failure(parameters, directory, "provenance", "provenance_mismatch", exc)
        if result.evaluation_status == "failed":
            return result
        raise RuntimeError(f"evaluation worker exited {code}")
    except (subprocess.TimeoutExpired, TimeoutError) as exc:
        return _failure(parameters, directory, "evaluation", "evaluation_timeout", exc)
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
        return _failure(parameters, directory, "evaluation", "evaluation_failed", exc)


def _worker(directory: Path) -> int:
    parameters = LoopParameters.model_validate(read_json(directory / "parameters.json"))
    config = ExperimentConfig.model_validate_json(
        json.dumps(read_json(directory / "worker_config.json"))
    )
    stage = "cad"
    try:
        validate_parameters(parameters, config)
        analysis = effective_config(parameters, config.repo_root)
        write_json(directory / "effective_analysis.json", analysis_definition(analysis))
        freecad = discover_freecad()
        script = directory / "generate_candidate.py"
        script.write_text(
            "import json, sys\nfrom pathlib import Path\n"
            f"sys.path.insert(0, {str(config.repo_root / 'src')!r})\n"
            "import FreeCAD, Part\n"
            "from open_engineering_intelligence.cad.freecad_backend import FreeCADBracketBackend\n"
            "from open_engineering_intelligence.schemas import DesignParameters\n"
            f"root = Path({str(directory)!r})\n"
            "params = DesignParameters(**json.loads((root/'parameters.json').read_text()))\n"
            "FreeCADBracketBackend().generate(params, root/'cad')\n"
            "(root/'cad_backend.json').write_text(json.dumps({"
            "'freecad_version': FreeCAD.Version(), 'opencascade_version': Part.OCC_VERSION"
            "}, sort_keys=True))\n",
            encoding="utf-8",
        )
        code = run_process(
            [str(freecad), "-c", str(script)], directory, "freecad", 60, new_group=False
        )
        if code != 0:
            raise RuntimeError(f"FreeCAD exited {code}")
        cad = read_json(directory / "cad/bracket_v1_manifest.json")
        if cad["parameters"] != parameters.model_dump() or cad["shape_valid"] is not True:
            raise ValueError("CAD identity or validity mismatch")
        stage = "mesh"
        mesher = GmshMesher(
            load_gmsh_meshing_config(config.repo_root / "configs/gmsh_bracket_v1.yaml")
        )
        artifacts = mesher.mesh(
            directory / "cad/bracket_v1.step",
            directory / "cad/bracket_v1_manifest.json",
            directory / "mesh",
        )
        stage = "analysis"
        executable, _ = discover_calculix_executable()
        stage = "solver"
        CalculiXStaticSolver(analysis, executable=executable).solve(
            artifacts["mesh"],
            artifacts["manifest"],
            directory / "fea",
        )
        stage = "provenance"
        result = collect_evaluation(parameters, config, directory)
        write_json(directory / "candidate_evaluation.json", result)
        return 0
    except Exception as exc:
        code = "provenance_mismatch" if stage == "provenance" else "evaluation_failed"
        write_json(
            directory / "candidate_evaluation.json",
            _failure(
                parameters,
                directory,
                getattr(exc, "stage", stage),
                code,
                exc,
            ),
        )
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", required=True, type=Path)
    sys.exit(_worker(parser.parse_args().worker.resolve()))
