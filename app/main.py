"""机织纹样浮长审计 HTTP API。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from . import db, weave
from .models import AuditOut, DesignIn, DesignOut, DesignSummary, ErrorOut, Violation


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 服务启动时建表（幂等）
    db.init_db()
    yield


app = FastAPI(
    title="Weave Float Audit API",
    summary="机织纹样浮长审计：生成经纬交织矩阵并审计超限浮长",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@app.post(
    "/designs",
    status_code=201,
    response_model=DesignOut,
    responses={400: {"model": ErrorOut, "description": "维度不一致或索引越界，整份设计被拒绝"}},
    tags=["designs"],
)
def submit_design(design: DesignIn) -> dict:
    """提交设计：校验 → 生成交织矩阵 → 浮长审计 → 入库，返回完整结果。"""
    try:
        shafts, treadles = weave.validate_design(
            design.threading, design.tie_up, design.treadling, design.max_float
        )
        interlacing, violations = weave.audit_floats(
            design.threading,
            design.tie_up,
            design.treadling,
            design.max_float,
            design.cyclic,
        )
    except weave.DesignError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    violation_dicts = [v.to_dict() for v in violations]
    design_id = db.insert_design_with_audit(
        name=design.name,
        cyclic=design.cyclic,
        max_float=design.max_float,
        shafts=shafts,
        treadles=treadles,
        threading_map=design.threading,
        tie_up=design.tie_up,
        treadling=design.treadling,
        interlacing=interlacing,
        violations=violation_dicts,
    )
    stored = db.get_design(design_id)
    assert stored is not None  # 刚写入，必然存在
    return stored


@app.get(
    "/designs",
    response_model=list[DesignSummary],
    tags=["designs"],
)
def list_designs() -> list[dict]:
    """列出全部已入库的合法设计（摘要）。"""
    return db.list_designs()


@app.get(
    "/designs/{design_id}",
    response_model=DesignOut,
    responses={404: {"model": ErrorOut, "description": "设计不存在"}},
    tags=["designs"],
)
def get_design(design_id: int) -> dict:
    """按 ID 查询已入库的设计及其审计结果。"""
    stored = db.get_design(design_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"design {design_id} not found")
    return stored


@app.get(
    "/designs/{design_id}/audit",
    response_model=AuditOut,
    responses={404: {"model": ErrorOut, "description": "设计不存在"}},
    tags=["designs"],
)
def get_audit(design_id: int) -> dict:
    """按设计 ID 单独查询审计结果。"""
    stored = db.get_design(design_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"design {design_id} not found")
    return stored["audit"]
