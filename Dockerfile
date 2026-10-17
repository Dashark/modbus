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

# 修正 entrypoint.sh 的 CRLF 并赋可执行权限
RUN sed -i 's/\r$//' /app/docker/entrypoint.sh \
    && chmod +x /app/docker/entrypoint.sh

# 不创建非 root 用户，容器默认以 root 运行
# root 可直接绑定 502，无需额外 cap（但保留 cap_add 也无害）

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["slave"]