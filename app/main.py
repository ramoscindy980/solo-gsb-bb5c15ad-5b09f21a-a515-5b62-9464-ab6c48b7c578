"""FastAPI application: weave float audit HTTP API."""
from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import db
from .schemas import DesignRequest, DesignResponse, HealthResponse
from .weave import build_interlacement, find_float_violations, validate_design

DEFAULT_DB_PATH = os.path.join(os.getcwd(), "data", "weave.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 建表纳入启动: 幂等执行, 数据库文件/目录缺失时自动创建。
    path = os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)
    app.state.db_path = path
    app.state.db = db.connect(path)
    db.init_db(app.state.db)
    yield


app = FastAPI(
    title="机织纹样浮长审计 API",
    description=(
        "根据穿综 (draft)、绑综 (tieup)、踏综 (treadling) 生成经纬交织矩阵, "
        "审计超过 max_float 的经向/纬向连续浮长; cyclic 纹样合并跨首尾边界连续段。"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


def get_db(request: Request) -> sqlite3.Connection:
    return request.app.state.db


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Pydantic 层面的结构错误 (缺字段/类型错误/矩阵非矩形等) 统一为 422,
    # 整份设计被拒绝且不入库。
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(
            {
                "code": "invalid_design",
                "message": "design rejected: dimension mismatch or invalid indices",
                "errors": [
                    f"{'/'.join(str(x) for x in e['loc'] if x != 'body') or 'body'}: "
                    f"{e['msg']}"
                    for e in exc.errors()
                ],
            }
        ),
    )


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post(
    "/api/designs",
    response_model=DesignResponse,
    status_code=201,
    tags=["designs"],
    responses={422: {"description": "维度不一致或索引越界, 整份设计被拒绝"}},
)
def create_design(
    payload: DesignRequest,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    draft = payload.draft
    tieup = payload.tieup
    treadling = payload.treadling
    max_float = payload.max_float
    cyclic = payload.cyclic

    errors = validate_design(draft, tieup, treadling, max_float)
    if errors:
        # 语义校验 (维度/越界/取值) 失败: 拒绝整份设计, 不写入。
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_design",
                "message": (
                    "design rejected: dimension mismatch or invalid indices"
                ),
                "errors": errors,
            },
        )

    matrix = build_interlacement(draft, tieup, treadling)
    violations = [asdict(v) for v in find_float_violations(matrix, max_float, cyclic)]

    design_id = db.insert_design(
        conn,
        draft=draft,
        tieup=tieup,
        treadling=treadling,
        max_float=max_float,
        cyclic=cyclic,
        warp_count=len(draft),
        weft_count=len(treadling),
        harness_count=max(draft) + 1,
        treadle_count=len(tieup),
        interlacement=matrix,
        violations=violations,
    )

    saved = db.get_design(conn, design_id)
    assert saved is not None
    return saved


@app.get(
    "/api/designs/{design_id}",
    response_model=DesignResponse,
    tags=["designs"],
    responses={404: {"description": "设计不存在"}},
)
def read_design(
    design_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict[str, Any]:
    saved = db.get_design(conn, design_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="design not found")
    return saved
