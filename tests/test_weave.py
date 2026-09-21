"""核心织纹逻辑的单元测试（不依赖 FastAPI）。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.weave import (  # noqa: E402
    DesignError,
    audit_floats,
    build_interlacing,
    validate_design,
    _runs,
)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


def test_interlacing():
    # 平纹：2 综 2 踏
    threading = [0, 1, 0, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 1, 0, 1]
    m = build_interlacing(threading, tie_up, treadling)
    check(m == [[1, 0, 1, 0],
                [0, 1, 0, 1],
                [1, 0, 1, 0],
                [0, 1, 0, 1]], "plain weave interlacing")


def test_warp_and_weft_floats():
    # 第 0 根经纱连续 3 纬浮起；第 0 纬纬纱连续浮过 3 根经纱
    threading = [0, 0, 0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 0, 1]
    # 矩阵:
    # 1 1 1
    # 1 1 1
    # 1 1 1
    # 0 0 0
    _, v = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    warp = [x for x in v if x.direction == "warp"]
    weft = [x for x in v if x.direction == "weft"]
    check(len(warp) == 3 and all(x.length == 3 and x.start == 0 for x in warp),
          "warp floats of length 3 on all 3 ends")
    check(len(weft) == 1 and weft[0].yarn_index == 3 and weft[0].length == 3,
          "weft float of length 3 on pick 3")
    check(all(x.yarn_index in (0, 1, 2) for x in warp), "warp yarn indices")


def test_cyclic_merge():
    # 列: 1 1 0 0 1 1 -> 非循环两段(0,2),(4,2)；循环合并为 (4,4)
    check(_runs([1, 1, 0, 0, 1, 1], 1, False) == [(0, 2), (4, 2)],
          "non-cyclic runs")
    check(_runs([1, 1, 0, 0, 1, 1], 1, True) == [(4, 4)],
          "cyclic merge across boundary")
    # 全 1 列：只有一段，不自我合并
    check(_runs([1, 1, 1], 1, True) == [(0, 3)],
          "all-float line stays a single run")
    # 首尾不相接时不合并
    check(_runs([1, 0, 0, 1, 0], 1, True) == [(0, 1), (3, 1)],
          "no merge when boundary not both target")


def test_cyclic_audit_end_to_end():
    # 2/2 斜纹 4x4 循环，max_float=2：循环合并后每根经纱浮长恰为 2，不超限
    threading = [0, 1, 2, 3]
    tie_up = [[1, 1, 0, 0],
              [0, 1, 1, 0],
              [0, 0, 1, 1] if False else [0, 0, 1, 1],
              [1, 0, 0, 1]]
    treadling = [0, 1, 2, 3]
    _, v = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=True)
    check(v == [], "2/2 twill cyclic: no float exceeds 2")
    # 非循环时边界处浮长仍 <= 2，也不超限
    _, v2 = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    check(v2 == [], "2/2 twill non-cyclic: no float exceeds 2")
    # max_float=1 时循环与非循环都应报出浮长 2
    _, v3 = audit_floats(threading, tie_up, treadling, max_float=1, cyclic=True)
    check(len(v3) > 0 and all(x.length == 2 for x in v3),
          "2/2 twill with max_float=1 flags length-2 floats")


def test_cyclic_wrap_violation():
    # 构造跨边界合并后才超限的情形：列 1 1 0 1 1，max_float=2
    # 非循环：两段长度 2、2，不超限；循环：合并为长度 4，超限
    threading = [0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 1, 0, 0]
    _, v_off = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    check(v_off == [], "wrap-around float not flagged when cyclic=False")
    _, v_on = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=True)
    check(len(v_on) == 1 and v_on[0].direction == "warp"
          and v_on[0].yarn_index == 0 and v_on[0].start == 3 and v_on[0].length == 4,
          "wrap-around float merged to length 4 starting at 3")


def test_validation():
    ok_cases = []
    # 维度不一致：绑综矩阵不是矩形
    try:
        validate_design([0], [[1, 0], [1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 穿综索引越界
    try:
        validate_design([0, 2], [[1, 0], [0, 1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 踏综索引越界
    try:
        validate_design([0], [[1], [0]], [2], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 绑综取值非 0/1
    try:
        validate_design([0], [[2]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 空输入
    try:
        validate_design([], [[1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 负索引
    try:
        validate_design([-1], [[1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    check(all(ok_cases), "invalid designs are rejected")


if __name__ == "__main__":
    test_interlacing()
    test_warp_and_weft_floats()
    test_cyclic_merge()
    test_cyclic_audit_end_to_end()
    test_cyclic_wrap_violation()
    test_validation()
    print("all tests passed")
