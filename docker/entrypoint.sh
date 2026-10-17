#!/usr/bin/env bash
set -euo pipefail

# 确保日志目录存在（挂载卷时可能覆盖权限）
mkdir -p /app/logs

ROLE="${1:-slave}"
shift || true

case "$ROLE" in
  slave)
    exec python -u run_slave.py \
      --source "${SOURCE_KIND:-db}" \
      --host 0.0.0.0 \
      --port "${MODBUS_PORT:-502}" \
      "$@"
    ;;
  master)
    exec python -u run_master.py \
      --ip "${PLC_HOST:-127.0.0.1}" \
      --port "${MODBUS_PORT:-502}" \
      "$@"
    ;;
  test)
    exec python -m unittest discover -s tests -v
    ;;
  shell)
    exec /bin/bash
    ;;
  *)
    echo "未知角色: $ROLE（可选 slave/master/test/shell）" >&2
    exit 1
    ;;
esac