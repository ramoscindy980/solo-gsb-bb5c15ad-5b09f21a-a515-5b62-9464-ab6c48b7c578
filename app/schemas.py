"""Pydantic request/response models."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, StrictInt


class DesignRequest(BaseModel):
    # StrictInt: JSON booleans (true/false) are not silently accepted as harness
    # or treadle indices; range/semantic checks still happen in validate_design.
    draft: list[StrictInt] = Field(
        description="经纱 -> 综框索引 (0 基), 长度 = 经纱数"
    )
    tieup: list[list[StrictInt]] = Field(
        description="绑综矩阵 踏板 x 综框, 1 = 踩下时提起综框"
    )
    treadling: list[StrictInt] = Field(
        description="逐纬踏板索引 (0 基), 长度 = 纬纱数"
    )
    max_float: StrictInt = Field(description="允许的最大连续浮长 (>= 1)")
    cyclic: bool = Field(
        default=False, description="纹样是否循环, 循环时合并首尾跨界连续段"
    )


class FloatViolation(BaseModel):
    direction: Literal["warp", "weft"]
    yarn: int
    start: int
    length: int


class DesignResponse(BaseModel):
    id: int
    draft: list[int]
    tieup: list[list[int]]
    treadling: list[int]
    max_float: int
    cyclic: bool
    warp_count: int
    weft_count: int
    harness_count: int
    treadle_count: int
    interlacement: list[list[int]]
    violations: list[FloatViolation]
    created_at: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    errors: list[str] | None = None


class HealthResponse(BaseModel):
    status: str
