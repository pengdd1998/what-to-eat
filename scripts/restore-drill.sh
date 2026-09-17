#!/bin/sh
# 恢复演练（落地方案 §2.5/§3.4：RTO ≤4h / RPO ≤24h；T1.10 演练脚本入库项）。
# 流程：对生产库副本做备份 → 模拟数据损坏路径（库替换）→ 完整性校验 →
#       在临时目录恢复 → 用恢复库起冒烟 → 清理。
# 与 age 的联动：若备份为 .age 且本机有 age 身份密钥，演练含"另一台设备凭私钥解密"
# 验收语义（§2.5 评审 9）；无私钥环境跑明文路径并如实标注。
# 用法：./scripts/restore-drill.sh   （不动生产库；全程临时目录）
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="${WTE_DB_PATH:-$ROOT/app.db}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "[drill] 1/5 生产库一致性快照"
BACKUP_DIR="$TMP/backups" "$ROOT/scripts/backup.sh"
BK="$(ls -1 "$TMP/backups" | head -1)"
echo "[drill]   备份产物: $BK"

if echo "$BK" | grep -q '\.age$'; then
  echo "[drill] 2/5 age 解密（本机私钥路径）"
  if ! command -v age >/dev/null 2>&1; then
    echo "[drill] FAIL: 备份为 age 加密但本机无 age"; exit 1; fi
  age -d -o "$TMP/restored.db" "$TMP/backups/$BK"
else
  echo "[drill] 2/5 明文备份（AGE_RECIPIENT 未设置——演练走非加密路径，留痕）"
  cp "$TMP/backups/$BK" "$TMP/restored.db"
fi

echo "[drill] 3/5 恢复库完整性校验"
sqlite3 "$TMP/restored.db" "PRAGMA integrity_check;" | grep -q '^ok$' || {
  echo "[drill] FAIL: 恢复库 integrity_check 非 ok"; exit 1; }

echo "[drill] 4/5 模拟库替换（数据损坏路径：down → 替换 → up 的库操作半件）"
RESTORE_TARGET="$TMP/app-restored-copy.db"
sqlite3 "$TMP/restored.db" ".backup '$RESTORE_TARGET'"
sqlite3 "$RESTORE_TARGET" "PRAGMA integrity_check;" | grep -q '^ok$' || {
  echo "[drill] FAIL: 替换后库不可用"; exit 1; }

echo "[drill] 5/5 恢复库冒烟（以恢复库起公共面＋Admin 内网面，跑全链路断言）"
WTE_DB_PATH="$RESTORE_TARGET" GO_SECRET="drill-go-secret-0123456789abcdef0123456789abcdef" \
  APP_VERSION=drill GIT_SHA=drill \
  "$ROOT/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8102 --app-dir "$ROOT" --log-level warning &
UVPID=$!
DRILL_TOKEN="drill-admin-token-0123456789abcdef0123456789abcdef"
WTE_DB_PATH="$RESTORE_TARGET" GO_SECRET="drill-go-secret-0123456789abcdef0123456789abcdef" \
  ADMIN_TOKEN="$DRILL_TOKEN" \
  "$ROOT/.venv/bin/uvicorn" app.admin:admin_app --host 127.0.0.1 --port 8107 \
  --app-dir "$ROOT" --log-level warning &
ADPID=$!
trap 'kill $UVPID $ADPID 2>/dev/null || true; rm -rf "$TMP"' EXIT
for i in $(seq 1 30); do
  curl -sf http://127.0.0.1:8102/api/health >/dev/null 2>&1 && \
    curl -sf -o /dev/null -H "Authorization: Bearer $DRILL_TOKEN" \
      http://127.0.0.1:8107/api/admin/audit >/dev/null 2>&1 && break
  sleep 0.5
done
SMOKE_BASE_URL=http://127.0.0.1:8102 SMOKE_ADMIN_URL=http://127.0.0.1:8107 \
  SMOKE_ADMIN_TOKEN="$DRILL_TOKEN" \
  "$ROOT/.venv/bin/python" "$ROOT/scripts/smoke.py" \
  && echo "[drill] PASS: 备份→恢复→校验→替换→恢复库双面冒烟 全链路演练通过"
