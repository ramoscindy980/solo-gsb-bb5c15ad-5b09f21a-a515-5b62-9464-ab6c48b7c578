"""Core weave math: validation, interlacement matrix and float auditing."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FloatSegment:
    """A maximal run of identical interlacement points along one yarn.

    direction: "warp" -> run runs along picks (rows) for one warp (column);
               "weft" -> run runs across warps (columns) for one pick (row).
    yarn:      0-based yarn index (warp column / weft row).
    start:     0-based index of the run's first cell along the crossing axis
               (pick index for warp floats, warp index for weft floats).
               For cyclic merges this is the linear start of the merged run.
    length:    number of consecutive interlacement points in the run.
    """

    direction: str
    yarn: int
    start: int
    length: int


def _is_strict_int(value: object) -> bool:
    """bool is a subclass of int; reject it for index/scalar integer fields."""
    return isinstance(value, int) and not isinstance(value, bool)


def validate_design(
    draft: object, tieup: object, treadling: object, max_float: object
) -> list[str]:
    """Collect all dimensional / range errors for one submitted design."""
    errors: list[str] = []

    # --- draft ----------------------------------------------------------------
    if not isinstance(draft, list) or not draft:
        errors.append("draft must be a non-empty array of integers")
        draft_ok = False
        draft_ints: list[int] = []
    else:
        draft_ok = all(_is_strict_int(x) for x in draft)
        if not draft_ok:
            errors.append("draft entries must be integers (booleans not allowed)")
        draft_ints = [x for x in draft if _is_strict_int(x)]

    # --- tieup ----------------------------------------------------------------
    harness_count = (max(draft_ints) + 1) if draft_ok and draft_ints else None

    treadle_count: int | None = None
    tieup_rectangular = False
    if not isinstance(tieup, list) or not tieup:
        errors.append("tieup must be a non-empty 2D matrix of 0/1")
        tie_widths: list[int] = []
    else:
        treadle_count = len(tieup)
        if not all(isinstance(row, list) and row for row in tieup):
            errors.append("each tieup row must be a non-empty array")
            tie_widths = []
        else:
            tie_widths = [len(row) for row in tieup]
            width = tie_widths[0]
            tieup_rectangular = all(w == width for w in tie_widths)
            if not tieup_rectangular:
                errors.append("tieup must be rectangular (all rows same length)")
            else:
                for t, row in enumerate(tieup):
                    for h, cell in enumerate(row):
                        if not _is_strict_int(cell) or cell not in (0, 1):
                            errors.append(f"tieup[{t}][{h}] must be 0 or 1")

    if tieup_rectangular and tie_widths and harness_count is not None:
        tieup_harnesses = tie_widths[0]
        if tieup_harnesses != harness_count:
            errors.append(
                f"tieup has {tieup_harnesses} harness column(s) but draft "
                f"requires {harness_count} (referenced harnesses 0..{harness_count - 1})"
            )

    # --- treadling ------------------------------------------------------------
    if not isinstance(treadling, list) or not treadling:
        errors.append("treadling must be a non-empty array of integers")
        treadling_ok = False
        treadling_ints: list[int] = []
    else:
        treadling_ok = all(_is_strict_int(x) for x in treadling)
        if not treadling_ok:
            errors.append(
                "treadling entries must be integers (booleans not allowed)"
            )
        treadling_ints = [x for x in treadling if _is_strict_int(x)]

    # --- index ranges ---------------------------------------------------------
    if draft_ok and harness_count is not None:
        for w, h in enumerate(draft_ints):
            if h < 0 or h >= harness_count:
                errors.append(
                    f"draft[{w}]={h} out of range for {harness_count} harness(es)"
                )

    if treadling_ok and treadle_count is not None:
        for p, t in enumerate(treadling_ints):
            if t < 0 or t >= treadle_count:
                errors.append(
                    f"treadling[{p}]={t} out of range for {treadle_count} treadle(s)"
                )

    # --- max_float ------------------------------------------------------------
    if not _is_strict_int(max_float):
        errors.append("max_float must be an integer")
    elif max_float < 1:
        errors.append("max_float must be >= 1")

    return errors


def build_interlacement(
    draft: list[int], tieup: list[list[int]], treadling: list[int]
) -> list[list[int]]:
    """Build the picks x warps interlacement matrix.

    cell = 1 means the warp is raised (warp over weft) at that intersection.
    Assumes the design has already passed validate_design.
    """
    return [
        [tieup[treadle][harness] for harness in draft]
        for treadle in treadling
    ]


def _maximal_runs(bits: list[int], target: int, cyclic: bool) -> list[tuple[int, int]]:
    """Return maximal runs of `target` in a binary sequence as (start, length).

    For cyclic sequences a run crossing the end/start boundary is merged into
    one run whose start is the linear index of its first cell.
    """
    n = len(bits)
    runs: list[tuple[int, int]] = []
    i = 0
    while i < n:
        if bits[i] != target:
            i += 1
            continue
        j = i
        while j < n and bits[j] == target:
            j += 1
        runs.append((i, j - i))
        i = j

    if cyclic and len(runs) > 1:
        first_start, first_len = runs[0]
        last_start, last_len = runs[-1]
        if first_start == 0 and last_start + last_len == n:
            # Boundary-touching runs join: the merged run starts at `last_start`
            # and wraps across the end onto the beginning.
            runs = runs[1:-1] + [(last_start, last_len + first_len)]

    runs.sort(key=lambda r: r[0])
    return runs


def find_float_violations(
    matrix: list[list[int]], max_float: int, cyclic: bool
) -> list[FloatSegment]:
    """Find warp (columns of 1s) and weft (rows of 0s) runs over the limit."""
    picks = len(matrix)
    warps = len(matrix[0]) if picks else 0
    violations: list[FloatSegment] = []

    # Warp floats: 1-runs down each warp column (across picks).
    for w in range(warps):
        column = [matrix[p][w] for p in range(picks)]
        for start, length in _maximal_runs(column, 1, cyclic):
            if length > max_float:
                violations.append(FloatSegment("warp", w, start, length))

    # Weft floats: 0-runs across each pick row (across warps).
    for p in range(picks):
        for start, length in _maximal_runs(matrix[p], 0, cyclic):
            if length > max_float:
                violations.append(FloatSegment("weft", p, start, length))

    return violations
