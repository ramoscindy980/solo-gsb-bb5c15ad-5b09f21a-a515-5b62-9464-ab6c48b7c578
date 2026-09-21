"""Unit tests for weave math (matrix building, run merging, auditing)."""
from app.weave import (
    build_interlacement,
    find_float_violations,
    validate_design,
)


def test_plain_weave_matrix_and_no_violations():
    draft = [0, 1]
    tieup = [[1, 0], [0, 1]]
    treadling = [0, 1]
    assert validate_design(draft, tieup, treadling, 1) == []

    matrix = build_interlacement(draft, tieup, treadling)
    assert matrix == [[1, 0], [0, 1]]

    violations = find_float_violations(matrix, max_float=1, cyclic=False)
    assert violations == []


def test_twill_matrix():
    # 3-harness 2/1 twill
    draft = [0, 1, 2]
    tieup = [[1, 0, 0], [1, 1, 0], [0, 1, 1]]
    treadling = [0, 1, 2]
    matrix = build_interlacement(draft, tieup, treadling)
    assert matrix == [[1, 0, 0], [1, 1, 0], [0, 1, 1]]


def test_warp_float_run_along_column():
    # All picks raise the same single harness: every column is constant.
    draft = [0, 1]
    tieup = [[1, 1]]
    treadling = [0, 0, 0, 0]
    matrix = build_interlacement(draft, tieup, treadling)
    assert matrix == [[1, 1], [1, 1], [1, 1], [1, 1]]

    violations = find_float_violations(matrix, max_float=3, cyclic=False)
    # warp floats length 4 > 3; weft runs are 1-runs, no 0s so no weft floats
    assert {(v.direction, v.yarn, v.start, v.length) for v in violations} == {
        ("warp", 0, 0, 4),
        ("warp", 1, 0, 4),
    }


def test_weft_float_run_along_row():
    draft = [0, 0, 0, 0]
    tieup = [[0]]  # harness never raised -> weft floats everywhere
    treadling = [0, 0]
    matrix = build_interlacement(draft, tieup, treadling)

    violations = find_float_violations(matrix, max_float=2, cyclic=False)
    assert {(v.direction, v.yarn, v.start, v.length) for v in violations} == {
        ("weft", 0, 0, 4),
        ("weft", 1, 0, 4),
    }


def test_cyclic_merges_boundary_runs():
    # warp0 column [1,1,0,1]: 1s at picks 0,1,3 -> merged run start=3 length 3
    # warp1 column [0,1,1,1]: interior run (1,3), boundary is broken by pick0=0
    matrix = [[1, 0], [1, 1], [0, 1], [1, 1]]
    violations = find_float_violations(matrix, max_float=2, cyclic=True)
    warp_hits = {(v.yarn, v.start, v.length) for v in violations if v.direction == "warp"}
    assert warp_hits == {(0, 3, 3), (1, 1, 3)}
    # rows: r0 = [1,0] (weft float len 1), r1=[1,1], r2=[0,1] (len 1), r3=[1,1]
    assert all(v.length <= 2 for v in violations if v.direction == "weft")


def test_non_cyclic_does_not_merge_boundary():
    matrix = [[1, 0], [1, 1], [0, 1], [1, 1]]
    violations = find_float_violations(matrix, max_float=1, cyclic=False)
    # warp0 [1,1,0,1]: run (0,2) exceeds 1; trailing run (3,1) does not
    warp0 = sorted((v.start, v.length) for v in violations if v.direction == "warp" and v.yarn == 0)
    assert warp0 == [(0, 2)]


def test_cyclic_all_same_is_single_full_run():
    matrix = [[1, 1], [1, 1]]
    violations = find_float_violations(matrix, max_float=1, cyclic=True)
    assert {(v.direction, v.yarn, v.start, v.length) for v in violations} == {
        ("warp", 0, 0, 2),
        ("warp", 1, 0, 2),
    }


def test_threshold_is_strict_greater_than():
    matrix = [[1, 0], [0, 1]]
    assert find_float_violations(matrix, max_float=1, cyclic=True) == []
    assert find_float_violations(matrix, max_float=0, cyclic=True) != []


def test_validation_collects_errors():
    # tieup width 2 != harness count 3 implied by draft; treadle index out of range
    errors = validate_design(
        draft=[0, 2],
        tieup=[[0, 0]],
        treadling=[0, 5],
        max_float=0,
    )
    assert errors
    assert any("tieup" in e for e in errors)
    assert any("treadling[1]" in e for e in errors)
    assert any("max_float" in e for e in errors)


def test_validation_rejects_ragged_and_non_integer():
    assert validate_design([], [[1]], [0], 1)
    assert validate_design([0], [[1, 0], [1]], [0], 1)
    assert validate_design([True], [[1]], [0], 1)
    assert validate_design([0], [[2]], [0], 1)
    assert validate_design([-1], [[0]], [0], 1)
