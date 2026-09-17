#!/bin/sh
# 每日备份（落地方案 §2.5，SUP-01）：sqlite3 .backup 在线一致性快照——严禁直接复制库文件。
# 流程：.backup → (可选) age 加密 → 轮转保留 BACKUP_KEEP 份（默认 14）。
# 环境变量：
#   WTE_DB_PATH   源库路径（默认 ./app.db）
#   BACKUP_DIR    备份目录（默认 ./backups）
#   AGE_RECIPIENT age 公钥（设置则加密；私钥仅存本人本地设备，禁入 VPS/git/备份介质）
#   BACKUP_KEEP   保留份数（默认 14）
# 退出码：0 成功；1 失败（03:30 未绿告警即本码非 0，§5.1 备份告警行）。
set -eu

DB_PATH="${WTE_DB_PATH:-./app.db}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP="${BACKUP_KEEP:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BACKUP_DIR"
[ -f "$DB_PATH" ] || { echo "[backup] FAIL: db not found: $DB_PATH"; exit 1; }

RAW="$BACKUP_DIR/app-$STAMP.db"
sqlite3 "$DB_PATH" ".backup '$RAW'"
sqlite3 "$RAW" "PRAGMA integrity_check;" | grep -q '^ok$' || {
  echo "[backup] FAIL: integrity_check not ok on $RAW"; exit 1; }

if [ -n "${AGE_RECIPIENT:-}" ] && command -v age >/dev/null 2>&1; then
  age -r "$AGE_RECIPIENT" -o "$RAW.age" "$RAW" && rm -f "$RAW"
  FINAL="$RAW.age"
else
  FINAL="$RAW"
fi

# 轮转：按名称时间序保留最近 KEEP 份（加密与明文混排场景按同一前缀排序）
ls -1 "$BACKUP_DIR" | grep '^app-.*\(\.db\|\.db\.age\)$' | sort -r | tail -n +"$((KEEP + 1))" \
  | while read -r f; do rm -f "$BACKUP_DIR/$f"; done

echo "[backup] OK: $FINAL ($(du -h "$FINAL" | cut -f1))"
