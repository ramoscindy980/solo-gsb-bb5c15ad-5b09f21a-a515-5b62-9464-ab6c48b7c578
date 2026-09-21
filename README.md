# 机织纹样浮长审计 (Weave Float Audit)

基于 **Python + FastAPI + SQLite** 的 HTTP API：根据穿综图 (draft)、绑综矩阵
(tie-up) 和逐纬踏综序列 (treadling) 生成经纬交织矩阵，审计超过上限的经向
与纬向连续浮长，并可声明纹样循环（跨首尾边界合并连续段）。

- API 端口：**8000**
- API 地址：<http://localhost:8000>
- 交互文档：<http://localhost:8000/docs>

## 单条启动命令

```bash
docker compose up --build
```

启动时会自动完成：

1. 安装 `requirements.txt` 中的依赖（构建镜像阶段）；
2. 创建 SQLite 数据表（应用启动阶段，表已存在则跳过）；
3. 在 `0.0.0.0:8000` 启动 uvicorn。

> 不用容器时：`pip install -r requirements.txt && uvicorn app.main:app --host 0.0.0.0 --port 8000`
> （应用启动时同样会自动建表，SQLite 文件位于 `./data/weave.db`。）

## 必要配置

均为可选项，通过环境变量或 compose 文件覆盖：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8000` | 容器内监听端口（一般无需修改） |
| `DATABASE_PATH` | `/data/weave.db` | SQLite 数据库文件路径，目录不存在会自动创建 |

宿主机映射端口在 `docker-compose.yml` 中通过 `"${HOST_PORT:-8000}:8000"` 配置；
如需换端口：`HOST_PORT=9000 docker compose up --build`。

## API

### `POST /api/designs`

提交一份纹样并执行浮长审计；校验通过后持久化，返回设计 ID、交织矩阵与超标浮长。

请求字段（索引全部为 **0 基**）：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `draft` | `int[]` | 长度 = 经纱数；每个元素是该经纱所穿的综框索引，取值 `[0, 综框数)` |
| `tieup` | `int[][]` | 绑综矩阵，维度 **踏板数 × 综框数**；`tieup[t][h]=1` 表示踩踏板 `t` 时提起综框 `h`，元素只能是 0/1 |
| `treadling` | `int[]` | 长度 = 纬纱数；逐纬（按纬序）踩下的踏板索引，取值 `[0, 踏板数)` |
| `max_float` | `int` | 允许的最大连续浮长，必须 ≥ 1；长度 **严格大于** 该值的浮长会被报告 |
| `cyclic` | `bool` | 纹样是否循环；为 `true` 时合并跨矩阵首尾边界的连续段 |

交织矩阵 `interlacement[pick][warp]`：`1` = 经浮点（该经纱在该纬纱之上），
`0` = 纬浮点（该纬纱在该经纱之上）。

浮长定义为同一种浮点状态的最大连续段长度：

- `warp`（经浮长）：沿某根经纱（列）连续的 `1`；
- `weft`（纬浮长）：沿某根纬纱（行）连续的 `0`。

循环纹样合并边界段后，`start` 为合并段在原矩阵上的线性起点索引
（沿对端纱线方向：经浮长为纬序，纬浮长为经序；即跨界段从靠矩阵末尾的
那一段开始，跨过终点续到矩阵开头）。

**请求示例 —— 平纹（无超标）：**

```bash
curl -s -X POST http://localhost:8000/api/designs \
  -H 'Content-Type: application/json' \
  -d '{
    "draft": [0, 1],
    "tieup": [[1, 0], [0, 1]],
    "treadling": [0, 1],
    "max_float": 1,
    "cyclic": false
  }'
```

**请求示例 —— 4×4 纹样（`cyclic=true`，浮长跨过循环边界被合并；上限 2）：**

```bash
curl -s -X POST http://localhost:8000/api/designs \
  -H 'Content-Type: application/json' \
  -d '{
    "draft": [0, 1, 2, 3],
    "tieup": [[0,0,1,1], [0,1,0,0], [1,0,1,0], [1,0,1,0]],
    "treadling": [0, 1, 2, 3],
    "max_float": 2,
    "cyclic": true
  }'
```

交织矩阵中第 2 列（0 基）的经浮点序列为 `[1,0,1,1]`：首尾的 `1` 与尾端
连续段在循环处合并为长度 3 的经浮长（`start=2`）；第 1 行的纬浮点序列
`[0,1,0,0]` 同理合并为长度 3 的纬浮长。同一份矩阵把 `cyclic` 改为
`false` 则审计通过（最长仅 2）。

响应（节选）：

```json
{
  "id": 1,
  "cyclic": true,
  "warp_count": 4,
  "weft_count": 4,
  "harness_count": 4,
  "treadle_count": 4,
  "max_float": 2,
  "interlacement": [[0,0,1,1],[0,1,0,0],[1,0,1,0],[1,0,1,0]],
  "violations": [
    {"direction": "warp", "yarn": 2, "start": 2, "length": 3},
    {"direction": "weft", "yarn": 1, "start": 2, "length": 3}
  ]
}
```

维度不一致（如 `tieup` 行宽与 `draft` 隐含的综框数不符、矩阵非矩形、
缺字段）或索引越界（穿综/踏综值超出范围、`max_float < 1`）时，整份设计被
拒绝，返回 **422** 且不写入数据库，错误明细在 `errors` 中逐条给出。

### `GET /api/designs/{id}`

按 ID 查询已入库的合法设计及其审计结果，结构与 POST 响应一致；
不存在返回 **404**。

### `GET /health`

健康检查，返回 `{"status": "ok"}`。

## 本地测试

```bash
python3 -m pytest -q
```
