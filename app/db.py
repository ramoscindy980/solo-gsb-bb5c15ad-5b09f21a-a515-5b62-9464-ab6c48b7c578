"""SQLite persistence for designs and audited float violations."""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS designs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    draft           TEXT    NOT NULL,
    tieup           TEXT    NOT NULL,
    treadling       TEXT    NOT NULL,
    max_float       INTEGER NOT NULL,
    cyclic          INTEGER NOT NULL,
    warp_count      INTEGER NOT NULL,
    weft_count      INTEGER NOT NULL,
    harness_count   INTEGER NOT NULL,
    treadle_count   INTEGER NOT NULL,
    interlacement   TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS float_violations (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    design_id INTEGER NOT NULL REFERENCES designs(id) ON DELETE CASCADE,
    direction TEXT    NOT NULL CHECK (direction IN ('warp', 'weft')),
    yarn      INTEGER NOT NULL,
    start     INTEGER NOT NULL,
    length    INTEGER NOT NULL,
    sort_no   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_float_violations_design
    ON float_violations(design_id);
"""


def connect(database_path: str) -> sqlite3.Connection:
    directory = os.path.dirname(os.path.abspath(database_path))
    os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Idempotent table creation, run at application startup."""
    conn.executescript(SCHEMA)
    conn.commit()


def insert_design(
    conn: sqlite3.Connection,
    *,
    draft: list[int],
    tieup: list[list[int]],
    treadling: list[int],
    max_float: int,
    cyclic: bool,
    warp_count: int,
    weft_count: int,
    harness_count: int,
    treadle_count: int,
    interlacement: list[list[int]],
    violations: list[dict[str, Any]],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO designs (draft, tieup, treadling, max_float, cyclic,
                             warp_count, weft_count, harness_count,
                             treadle_count, interlacement)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            json.dumps(draft),
            json.dumps(tieup),
            json.dumps(treadling),
            max_float,
            1 if cyclic else 0,
            warp_count,
            weft_count,
            harness_count,
            treadle_count,
            json.dumps(interlacement),
        ),
    )
    design_id = int(cur.lastrowid)
    conn.executemany(
        """
        INSERT INTO float_violations
            (design_id, direction, yarn, start, length, sort_no)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                design_id,
                v["direction"],
                v["yarn"],
                v["start"],
                v["length"],
                idx,
            )
            for idx, v in enumerate(violations)
        ],
    )
    conn.commit()
    return design_id


def get_design(conn: sqlite3.Connection, design_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM designs WHERE id = ?", (design_id,)
    ).fetchone()
    if row is None:
        return None

    violation_rows = conn.execute(
        """
        SELECT direction, yarn, start, length
        FROM float_violations
        WHERE design_id = ?
        ORDER BY sort_no
        """,
        (design_id,),
    ).fetchall()

    return {
        "id": row["id"],
        "draft": json.loads(row["draft"]),
        "tieup": json.loads(row["tieup"]),
        "treadling": json.loads(row["treadling"]),
        "max_float": row["max_float"],
        "cyclic": bool(row["cyclic"]),
        "warp_count": row["warp_count"],
        "weft_count": row["weft_count"],
        "harness_count": row["harness_count"],
        "treadle_count": row["treadle_count"],
        "interlacement": json.loads(row["interlacement"]),
        "violations": [
            {
                "direction": r["direction"],
                "yarn": r["yarn"],
                "start": r["start"],
                "length": r["length"],
            }
            for r in violation_rows
        ],
        "created_at": row["created_at"],
    }
