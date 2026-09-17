#!/bin/zsh
# 本地冒烟：起 venv + uvicorn(公共面 8100 + Admin 内网面 8103，临时库)
#   → scripts/smoke.py → 清理
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

export WTE_DB_PATH="$(mktemp -d)/smoke-$$.db"
export APP_VERSION="0.2.0-t1x"
export GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo dev)"
export SMOKE_BASE_URL="http://127.0.0.1:8100"
export SMOKE_ADMIN_URL="http://127.0.0.1:8103"
export SMOKE_ADMIN_TOKEN="smoke-admin-token-0123456789abcdef0123456789abcdef"
export ADMIN_TOKEN="$SMOKE_ADMIN_TOKEN"
# GO_SECRET 故意不注入——冒烟走 dev 兜底路径，覆盖密钥守卫的告警＋audit 断言
# （工程审查 V-4；生产形态由发布检查单的"非默认值服务器侧核验"把关）
export SMOKE_EXPECT_DEV_FALLBACK=1

# 阶段5：pytest 前置（快败；requirements-dev 钉版不进运行镜像）
.venv/bin/pip install -q -r requirements-dev.txt
.venv/bin/pytest -q || { echo "pytest 失败，冒烟中止"; exit 1; }

.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8100 --log-level warning &
PID1=$!
.venv/bin/uvicorn app.admin:admin_app --host 127.0.0.1 --port 8103 --log-level warning &
PID2=$!
trap 'kill $PID1 $PID2 2>/dev/null || true; rm -f "$WTE_DB_PATH" "$WTE_DB_PATH-wal" "$WTE_DB_PATH-shm"' EXIT

for i in {1..30}; do
  curl -sf "$SMOKE_BASE_URL/api/health" >/dev/null 2>&1 && \
    curl -sf -o /dev/null -H "Authorization: Bearer $ADMIN_TOKEN" \
      "$SMOKE_ADMIN_URL/api/admin/audit" >/dev/null 2>&1 && break
  sleep 0.5
done

.venv/bin/python scripts/smoke.py
