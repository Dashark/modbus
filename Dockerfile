# 泵站流量检测系统 Modbus TCP 从站/主站镜像
FROM python:3.11-slim

# 时区与编码
ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 系统依赖（psycopg binary 已自带 libpq，这里只装 tzdata）
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install -r requirements.txt

# 拷贝应用代码
COPY . .

# 非 root 用户运行（502 端口需 CAP_NET_BIND_SERVICE，见 compose）
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app
USER appuser

# 默认启动从站（可被 compose command 覆盖）
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["slave"]