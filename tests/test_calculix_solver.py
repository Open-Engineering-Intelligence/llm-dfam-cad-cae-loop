import json
from dataclasses import replace
from pathlib import Path

import pytest


def _write_msh(
    path: Path,
    *,
    volume_element_type: int = 4,
    volume_connectivity: str = "10 20 30 40",
) -> Path:
    volume_node_count = {4: 4, 5: 8}[volume_element_type]
    extra_nodes = ""
    node_count = 4
    max_node = 40
    if volume_node_count == 8:
        extra_nodes = "50\n60\n70\n80\n1 1 0\n1 0 1\n0 1 1\n1 1 1\n"
        node_count = 8
        max_node = 80
        volume_connectivity = "10 20 30 40 50 60 70 80"
    path.write_text(
        f"""$MeshFormat
4.1 0 8
$EndMeshFormat
$Nodes
1 {node_count} 10 {max_node}
3 1 0 {node_count}
10
20
30
40
{extra_nodes}0 0 0
1 0 0
0 1 0
0 0 1
$EndNodes
$Elements
2 2 1 100
2 1 2 1
1 10 20 30
3 1 {volume_element_type} 1
100 {volume_connectivity}
$EndElements
""",
        encoding="utf-8",
    )
    return path


def test_calculix_config_matches_frozen_static_analysis_definition() -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        load_calculix_static_config,
    )

    config = load_calculix_static_config(Path("configs/calculix_bracket_v1.yaml"))

    assert config.case_name == "bracket_v1_static"
    assert config.element_type == "C3D4"
    assert config.youngs_modulus_mpa == 3250.0
    assert config.poissons_ratio == 0.36
    assert config.fixed_x_mm == 0.0
    assert config.coordinate_tolerance_mm == 1e-6
    assert config.load_x_range_mm == (98.0, 108.0)
    assert config.load_y_range_mm == (-25.0, 25.0)
    assert config.load_z_mm == 8.0
    assert config.total_load_n == (0.0, 0.0, -150.0)
    assert config.units == {"length": "mm", "force": "N", "stress": "MPa"}


def test_parse_gmsh_msh_preserves_node_and_element_ids(tmp_path: Path) -> None:
    from open_engineering_intelligence.cae.calculix_solver import parse_gmsh_msh

    mesh = parse_gmsh_msh(_write_msh(tmp_path / "minimal.msh"))

    assert mesh.nodes == {
        10: (0.0, 0.0, 0.0),
        20: (1.0, 0.0, 0.0),
        30: (0.0, 1.0, 0.0),
        40: (0.0, 0.0, 1.0),
    }
    assert mesh.surface_node_ids == frozenset({10, 20, 30})
    assert [(element.element_id, element.node_ids) for element in mesh.tetrahedra] == [
        (100, (10, 20, 30, 40))
    ]


def test_parse_gmsh_msh_rejects_unsupported_volume_elements(tmp_path: Path) -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        CalculiXStaticError,
        parse_gmsh_msh,
    )

    with pytest.raises(CalculiXStaticError, match="unsupported Gmsh volume element type 5"):
        parse_gmsh_msh(_write_msh(tmp_path / "hex.msh", volume_element_type=5))


def test_parse_gmsh_msh_rejects_missing_referenced_nodes(tmp_path: Path) -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        CalculiXStaticError,
        parse_gmsh_msh,
    )

    with pytest.raises(CalculiXStaticError, match="missing node 999"):
        parse_gmsh_msh(
            _write_msh(
                tmp_path / "missing_node.msh",
                volume_connectivity="10 20 30 999",
            )
        )


@pytest.mark.parametrize(
    "coordinates",
    [
        {40: (0.0, 0.0, 0.0)},
        {20: (0.0, 1.0, 0.0), 30: (1.0, 0.0, 0.0)},
    ],
)
def test_validate_tetrahedra_rejects_nonpositive_volume(coordinates: dict[int, tuple]) -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        CalculiXStaticError,
        Tetrahedron,
        validate_tetrahedra,
    )

    nodes = {
        10: (0.0, 0.0, 0.0),
        20: (1.0, 0.0, 0.0),
        30: (0.0, 1.0, 0.0),
        40: (0.0, 0.0, 1.0),
    }
    nodes.update(coordinates)

    with pytest.raises(CalculiXStaticError, match="positive volume"):
        validate_tetrahedra(nodes, (Tetrahedron(100, (10, 20, 30, 40)),))


def _selection_mesh():
    from open_engineering_intelligence.cae.calculix_solver import GmshMesh

    nodes = {
        1: (0.0, -35.0, 0.0),
        2: (0.0, 35.0, 0.0),
        3: (0.0, 0.0, 70.0),
        101: (98.0, -25.0, 8.0),
        102: (103.0, 0.0, 8.0),
        103: (108.0, 25.0, 8.0),
        104: (103.0, 0.0, 7.9),
        999: (103.0, 0.0, 8.0),
    }
    return GmshMesh(
        nodes=nodes,
        surface_node_ids=frozenset({1, 2, 3, 101, 102, 103, 104}),
        tetrahedra=(),
    )


def test_fixed_and_load_node_selection_use_boundary_geometry() -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        load_calculix_static_config,
        select_fixed_nodes,
        select_load_nodes,
    )

    config = load_calculix_static_config(Path("configs/calculix_bracket_v1.yaml"))
    mesh = _selection_mesh()

    assert select_fixed_nodes(mesh, config) == (1, 2, 3)
    assert select_load_nodes(mesh, config, fixed_node_ids=(1, 2, 3)) == (101, 102, 103)


def test_fixed_node_selection_rejects_collinear_rear_face() -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        CalculiXStaticError,
        GmshMesh,
        load_calculix_static_config,
        select_fixed_nodes,
    )

    config = load_calculix_static_config(Path("configs/calculix_bracket_v1.yaml"))
    mesh = GmshMesh(
        nodes={1: (0.0, 0.0, 0.0), 2: (0.0, 1.0, 0.0), 3: (0.0, 2.0, 0.0)},
        surface_node_ids=frozenset({1, 2, 3}),
        tetrahedra=(),
    )

    with pytest.raises(CalculiXStaticError, match="not collinear") as error:
        select_fixed_nodes(mesh, config)

    assert error.value.stage == "boundary_selection"


def test_load_node_selection_rejects_overlap_with_fixed_nodes() -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        CalculiXStaticError,
        load_calculix_static_config,
        select_load_nodes,
    )

    config = load_calculix_static_config(Path("configs/calculix_bracket_v1.yaml"))

    with pytest.raises(CalculiXStaticError, match="disjoint") as error:
        select_load_nodes(_selection_mesh(), config, fixed_node_ids=(101,))

    assert error.value.stage == "boundary_selection"


def test_equivalent_nodal_loads_reconstruct_total_force() -> None:
    from open_engineering_intelligence.cae.calculix_solver import equivalent_nodal_loads

    loads = equivalent_nodal_loads((101, 102, 103), (0.0, 0.0, -150.0))

    assert loads == {
        101: (0.0, 0.0, -50.0),
        102: (0.0, 0.0, -50.0),
        103: (0.0, 0.0, -50.0),
    }
    assert tuple(sum(load[axis] for load in loads.values()) for axis in range(3)) == (
        0.0,
        0.0,
        -150.0,
    )


@pytest.mark.parametrize(
    ("stress", "expected"),
    [
        ((10.0, 0.0, 0.0, 0.0, 0.0, 0.0), 10.0),
        ((10.0, 10.0, 10.0, 0.0, 0.0, 0.0), 0.0),
        ((0.0, 0.0, 0.0, 5.0, 0.0, 0.0), 5.0 * (3.0**0.5)),
    ],
)
def test_von_mises_uses_six_integration_point_components(stress: tuple, expected: float) -> None:
    from open_engineering_intelligence.cae.calculix_solver import von_mises_stress

    assert von_mises_stress(*stress) == pytest.approx(expected)


def test_analysis_fingerprint_is_deterministic_and_load_sensitive() -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        analysis_fingerprint,
        load_calculix_static_config,
    )

    config = load_calculix_static_config(Path("configs/calculix_bracket_v1.yaml"))

    assert analysis_fingerprint(config) == analysis_fingerprint(config)
    assert analysis_fingerprint(config) != analysis_fingerprint(
        replace(config, total_load_n=(0.0, 0.0, -100.0))
    )
    assert analysis_fingerprint(config) != analysis_fingerprint(
        replace(config, youngs_modulus_mpa=3000.0)
    )


def test_failure_result_writes_null_numerics_and_stable_stage(tmp_path: Path) -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        load_calculix_static_config,
        write_failure_result,
    )

    config = load_calculix_static_config(Path("configs/calculix_bracket_v1.yaml"))
    result_path = write_failure_result(
        tmp_path,
        config=config,
        stage="mesh_validation",
        reason="mesh is malformed",
        geometry_fingerprint={"volume_mm3": 1.0},
        mesh_provenance={"mesh_sha256": "abc"},
        invocation_method=None,
        solver_version=None,
        calculix_input_sha256=None,
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))

    assert result["solver_status"] == "failed"
    assert result["failure_stage"] == "mesh_validation"
    assert result["failure_reason"] == "mesh is malformed"
    assert result["max_displacement"] is None
    assert result["max_von_mises_stress"] is None
    assert result["reaction_force_n"] is None


def test_failure_result_refuses_to_overwrite_successful_evidence(tmp_path: Path) -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        load_calculix_static_config,
        write_failure_result,
    )

    config = load_calculix_static_config(Path("configs/calculix_bracket_v1.yaml"))
    result_path = tmp_path / "physics_result.json"
    successful_evidence = '{"solver_status": "succeeded", "evidence": "preserve me"}\n'
    result_path.write_text(successful_evidence, encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_failure_result(
            tmp_path,
            config=config,
            stage="solver_execution",
            reason="later standalone failure",
            geometry_fingerprint=None,
            mesh_provenance=None,
            invocation_method=None,
            solver_version=None,
            calculix_input_sha256=None,
        )

    assert result_path.read_text(encoding="utf-8") == successful_evidence


def test_calculix_input_is_deterministic_and_complete(tmp_path: Path) -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        GmshMesh,
        Tetrahedron,
        equivalent_nodal_loads,
        load_calculix_static_config,
        write_calculix_input,
    )

    config = load_calculix_static_config(Path("configs/calculix_bracket_v1.yaml"))
    mesh = GmshMesh(
        nodes={
            30: (0.0, 1.0, 0.0),
            10: (0.0, 0.0, 0.0),
            40: (0.0, 0.0, 1.0),
            20: (1.0, 0.0, 0.0),
            50: (1.0, 1.0, 1.0),
        },
        surface_node_ids=frozenset({10, 20, 30, 50}),
        tetrahedra=(Tetrahedron(100, (10, 20, 30, 40)),),
    )
    loads = equivalent_nodal_loads((20, 50), config.total_load_n)

    first_path, first_sha = write_calculix_input(
        tmp_path / "first",
        mesh=mesh,
        config=config,
        fixed_node_ids=(10, 40),
        nodal_loads=loads,
    )
    second_path, second_sha = write_calculix_input(
        tmp_path / "second",
        mesh=mesh,
        config=config,
        fixed_node_ids=(10, 40),
        nodal_loads=loads,
    )
    first = first_path.read_text(encoding="ascii")
    second = second_path.read_text(encoding="ascii")

    assert first == second
    assert first_sha == second_sha
    assert "*NODE\n10, 0, 0, 0\n20, 1, 0, 0" in first
    assert "*ELEMENT, TYPE=C3D4, ELSET=VOLUME_ELEMENTS\n100, 10, 20, 30, 40" in first
    assert "*NSET, NSET=ALL_NODES" in first
    assert "*NSET, NSET=FIXED_NODES\n10, 40" in first
    assert "*NSET, NSET=LOAD_NODES\n20, 50" in first
    assert "*MATERIAL, NAME=PLA_LIKE_ISOTROPIC_REFERENCE" in first
    assert "*ELASTIC\n3250, 0.36" in first
    assert "*SOLID SECTION, ELSET=VOLUME_ELEMENTS" in first
    assert "*STATIC" in first
    assert "*BOUNDARY\nFIXED_NODES, 1, 3, 0" in first
    assert "20, 3, -75" in first
    assert "50, 3, -75" in first
    assert "*NODE PRINT, NSET=ALL_NODES" in first
    assert "*NODE PRINT, NSET=FIXED_NODES" in first
    assert "*EL PRINT, ELSET=VOLUME_ELEMENTS\nS" in first
    assert "*NODE FILE, NSET=ALL_NODES" in first
    assert "*EL FILE\nS" in first
    assert "POSITION=INTEGRATION" not in first
    assert "*EL FILE," not in first
    assert "U" in first
    assert "RF" in first
    assert "S" in first


def test_parse_calculix_dat_uses_named_sections_and_integration_point_stress(
    tmp_path: Path,
) -> None:
    from open_engineering_intelligence.cae.calculix_solver import parse_calculix_dat

    dat_path = tmp_path / "case.dat"
    dat_path.write_text(
        """
 displacements (vx,vy,vz) for set ALL_NODES and time  0.1000000E+01

        10  0.000000E+00  0.000000E+00  0.000000E+00
        20  3.000000E+00  4.000000E+00 -1.000000E+00

 forces (fx,fy,fz) for set FIXED_NODES and time  0.1000000E+01

        10  0.000000E+00  0.000000E+00  1.500000E+02

 stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set VOLUME_ELEMENTS and time  0.1000000E+01

       100   1  1.000000E+01  0.000000E+00  0.000000E+00  0.000000E+00  2.000000E+00  3.000000E+00
""",
        encoding="ascii",
    )

    parsed = parse_calculix_dat(
        dat_path,
        volume_node_ids={10, 20},
        fixed_node_ids={10},
        volume_element_ids={100},
    )

    assert parsed.displacements[20] == (3.0, 4.0, -1.0)
    assert parsed.reactions[10] == (0.0, 0.0, 150.0)
    assert parsed.stresses[(100, 1)] == (10.0, 0.0, 0.0, 0.0, 3.0, 2.0)
    assert parsed.max_displacement.node_id == 20
    assert parsed.max_displacement.value == pytest.approx(26.0**0.5)
    assert parsed.max_von_mises.element_id == 100
    assert parsed.max_von_mises.integration_point == 1


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("displacements (vx,vy,vz) for set ALL_NODES and time 1\n\n10 0 0 nan\n", "NaN or Inf"),
        (
            "displacements (vx,vy,vz) for set ALL_NODES and time 1\n\n999 0 0 0\n",
            "unknown node 999",
        ),
        ("", "missing displacement"),
    ],
)
def test_parse_calculix_dat_rejects_incomplete_or_invalid_results(
    tmp_path: Path, content: str, message: str
) -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        CalculiXStaticError,
        parse_calculix_dat,
    )

    path = tmp_path / "invalid.dat"
    path.write_text(content, encoding="ascii")

    with pytest.raises(CalculiXStaticError, match=message) as error:
        parse_calculix_dat(
            path,
            volume_node_ids={10},
            fixed_node_ids={10},
            volume_element_ids={100},
        )

    assert error.value.stage == "result_parsing"


def test_discover_calculix_executable_prefers_explicit_then_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        discover_calculix_executable,
    )

    explicit = tmp_path / "explicit-ccx.exe"
    environment = tmp_path / "environment-ccx.exe"
    explicit.write_bytes(b"x")
    environment.write_bytes(b"x")
    monkeypatch.setenv("CALCULIX_CCX", str(environment))

    assert discover_calculix_executable(explicit)[1] == "explicit_path"
    assert discover_calculix_executable()[0] == environment.resolve()
    assert discover_calculix_executable()[1] == "environment"


def test_discover_calculix_executable_fails_without_configured_or_path_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        CalculiXStaticError,
        discover_calculix_executable,
    )

    monkeypatch.delenv("CALCULIX_CCX", raising=False)
    monkeypatch.setattr("shutil.which", lambda _name: None)

    with pytest.raises(CalculiXStaticError, match="CALCULIX_CCX") as error:
        discover_calculix_executable()

    assert error.value.stage == "solver_invocation"


def test_parse_calculix_dat_uses_observed_222_tables(tmp_path: Path) -> None:
    from open_engineering_intelligence.cae.calculix_solver import parse_calculix_dat

    dat_path = tmp_path / "case.dat"
    dat_path.write_text(
        """
 displacements (vx,vy,vz) for set ALL_NODES and time  0.1000000E+01

         1  0.000000E+00  0.000000E+00  0.000000E+00
         2  1.000000E-01 -2.000000E-01 -3.000000E-01

 forces (fx,fy,fz) for set FIXED_NODES and time  0.1000000E+01

         1  1.000000E+00  2.000000E+00  1.500000E+02

 stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set VOLUME_ELEMENTS and time  0.1000000E+01

       100   1  1.000000E+00  2.000000E+00  3.000000E+00  4.000000E+00  5.000000E+00  6.000000E+00

""",
        encoding="ascii",
    )

    parsed = parse_calculix_dat(
        dat_path,
        volume_node_ids={1, 2},
        fixed_node_ids={1},
        volume_element_ids={100},
    )

    assert parsed.displacements == {
        1: (0.0, 0.0, 0.0),
        2: (0.1, -0.2, -0.3),
    }
    assert parsed.reaction_forces == {1: (1.0, 2.0, 150.0)}
    assert len(parsed.integration_point_stresses) == 1
    stress = parsed.integration_point_stresses[0]
    assert stress.element_id == 100
    assert stress.integration_point == 1
    assert stress.components == (1.0, 2.0, 3.0, 4.0, 6.0, 5.0)


def test_parse_calculix_dat_rejects_incomplete_volume_results(tmp_path: Path) -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        CalculiXStaticError,
        parse_calculix_dat,
    )

    dat_path = tmp_path / "incomplete.dat"
    dat_path.write_text(
        """
 displacements (vx,vy,vz) for set ALL_NODES and time  0.1000000E+01

         1  0.000000E+00  0.000000E+00  0.000000E+00

 forces (fx,fy,fz) for set FIXED_NODES and time  0.1000000E+01

         1  0.000000E+00  0.000000E+00  1.500000E+02

 stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set VOLUME_ELEMENTS and time  0.1000000E+01

       100   1  1.000000E+00  2.000000E+00  3.000000E+00  4.000000E+00  5.000000E+00  6.000000E+00

""",
        encoding="ascii",
    )

    with pytest.raises(CalculiXStaticError, match=r"missing displacements for nodes \[2\]"):
        parse_calculix_dat(
            dat_path,
            volume_node_ids={1, 2},
            fixed_node_ids={1},
            volume_element_ids={100},
        )


def test_validate_calculix_frd_requires_requested_datasets(tmp_path: Path) -> None:
    from open_engineering_intelligence.cae.calculix_solver import (
        CalculiXStaticError,
        validate_calculix_frd,
    )

    complete = tmp_path / "complete.frd"
    complete.write_text(
        " -4  DISP        4    1\n -4  STRESS      6    1\n -4  FORC        4    1\n",
        encoding="ascii",
    )
    validate_calculix_frd(complete)

    incomplete = tmp_path / "incomplete.frd"
    incomplete.write_text(" -4  DISP        4    1\n", encoding="ascii")
    with pytest.raises(CalculiXStaticError, match="missing datasets: FORC, STRESS"):
        validate_calculix_frd(incomplete)
