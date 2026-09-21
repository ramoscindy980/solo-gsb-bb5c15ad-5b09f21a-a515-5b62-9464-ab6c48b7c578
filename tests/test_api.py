"""End-to-end API tests with an isolated temporary SQLite database."""
import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    import app.main as main

    importlib.reload(main)
    with TestClient(main.app) as c:
        yield c


PLAIN = {
    "draft": [0, 1],
    "tieup": [[1, 0], [0, 1]],
    "treadling": [0, 1],
    "max_float": 1,
    "cyclic": False,
}

# 4x4 pattern where float runs cross the repeat boundary:
# col2 = [1,0,1,1] (1s wrap to a single length-3 warp float),
# row1 = [0,1,0,0] (0s wrap to a single length-3 weft float).
BOUNDARY = {
    "draft": [0, 1, 2, 3],
    "tieup": [[0, 0, 1, 1], [0, 1, 0, 0], [1, 0, 1, 0], [1, 0, 1, 0]],
    "treadling": [0, 1, 2, 3],
    "max_float": 2,
    "cyclic": True,
}


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_post_plain_weave_persists_and_retrieves(client):
    r = client.post("/api/designs", json=PLAIN)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["interlacement"] == [[1, 0], [0, 1]]
    assert body["violations"] == []
    assert body["warp_count"] == 2 and body["weft_count"] == 2
    assert body["harness_count"] == 2 and body["treadle_count"] == 2
    design_id = body["id"]

    r2 = client.get(f"/api/designs/{design_id}")
    assert r2.status_code == 200
    assert r2.json() == body


def test_cyclic_design_reports_boundary_merging(client):
    r = client.post("/api/designs", json=BOUNDARY)
    assert r.status_code == 201, r.text
    assert r.json()["interlacement"] == [
        [0, 0, 1, 1],
        [0, 1, 0, 0],
        [1, 0, 1, 0],
        [1, 0, 1, 0],
    ]
    violations = {
        (v["direction"], v["yarn"], v["start"], v["length"])
        for v in r.json()["violations"]
    }
    # col2 1s wrap into one run starting at the tail; row1 0s likewise.
    assert violations == {
        ("warp", 2, 2, 3),
        ("weft", 1, 2, 3),
    }

    # same matrix, non-cyclic: no run exceeds 2 -> clean audit
    r2 = client.post("/api/designs", json=dict(BOUNDARY, cyclic=False))
    assert r2.status_code == 201, r2.text
    assert r2.json()["violations"] == []


def test_get_missing_returns_404(client):
    assert client.get("/api/designs/999").status_code == 404


def test_dimension_mismatch_rejected_not_persisted(client):
    bad = dict(PLAIN, tieup=[[1, 0, 0], [0, 1, 0]])  # width 3 != 2 harnesses
    r = client.post("/api/designs", json=bad)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert any("tieup" in e for e in detail["errors"])

    # whole design rejected: nothing stored beyond failing inserts
    assert client.get("/api/designs/1").status_code == 404


def test_index_out_of_range_rejected(client):
    bad = dict(PLAIN, treadling=[0, 7])
    r = client.post("/api/designs", json=bad)
    assert r.status_code == 422
    assert any("treadling[1]" in e for e in r.json()["detail"]["errors"])


def test_missing_field_returns_422(client):
    bad = {k: v for k, v in PLAIN.items() if k != "max_float"}
    r = client.post("/api/designs", json=bad)
    assert r.status_code == 422


def test_non_cyclic_same_design_gives_split_runs(client):
    payload = dict(BOUNDARY, cyclic=False, max_float=1)
    r = client.post("/api/designs", json=payload)
    assert r.status_code == 201, r.text
    violations = r.json()["violations"]
    # without wrapping, only runs of length 2 exceed max_float 1
    assert all(v["length"] == 2 for v in violations)
    assert len(violations) == 4
