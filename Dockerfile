FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    DATABASE_PATH=/data/weave.db

WORKDIR /app

# 依赖安装纳入镜像构建 (即服务启动链路的一部分)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# 建表在应用启动 (lifespan) 时幂等执行, 随后启动 HTTP 服务
CMD uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
