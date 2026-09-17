#!/bin/zsh
# PoC-3 真机 spike 材料（T0.4/ADR-003 A 判断 2；部署到目标域名后在微信内执行）
#
# 第 0 步（X5/ICP 前提）：微信内打开 https://<目标域名>/  —— 能正常打开才继续。
# 本脚本：起本地服务 → 造会话→accept → 打印 /go/{token} 完整 URL 样例与操作规程。
# 真机执行时在已部署环境用同等 API 调用铸 token（或临时以本机为服务器+手机同网访问）。
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

PORT=8121
DB=$(mktemp -d)/poc3.db
export WTE_DB_PATH="$DB" APP_VERSION=poc3 GIT_SHA=poc3 GO_SECRET="poc3-go-secret-0123456789abcdef0123456"

.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT --log-level warning &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
for i in {1..30}; do curl -sf http://127.0.0.1:$PORT/api/health >/dev/null 2>&1 && break; sleep 0.5; done

BASE="http://127.0.0.1:$PORT"
.venv/bin/python - <<EOF
import json, time, urllib.request

def call(m, p, b=None):
    r = urllib.request.Request("$BASE"+p, method=m)
    d = json.dumps(b).encode() if b is not None else None
    if d: r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, d, timeout=10) as x:
        return json.loads(x.read() or b"{}")

print("== PoC-3 材料铸造 ==")
for i in range(3):  # 3 个样例 token
    s = call("POST", "/api/session/start", {"anon_id": f"poc3device{i:04d}"})
    sid = s["session_id"]
    call("POST", f"/api/session/{sid}/answer", {"step": 1, "tags": ["要快"]})
    rec = call("POST", f"/api/session/{sid}/result-request", {"answers": {"tags": ["要快"]}})
    acc = call("POST", f"/api/session/{sid}/accept", {"dish_slug": rec["dish_slug"]})
    print(f"样例{i+1}: {rec['dish_name']}")
    print(f"  /go URL: $BASE/go/{acc['go_token']}")
    print(f"  预期 302 → 平台搜索（keyword={rec['dish_name']}）")
EOF

cat <<'EOF'

== 真机操作规程（iOS＋Android 微信各 ≥20 次，ADR-003 A 判断 2）==
1. 手机与服务器同网（或部署后用目标域名），微信内打开上述 /go URL（发给自己/文件传输助手）。
2. 每次记录：到达平台搜索页？(y/n) / 是否出现拦截页 / 肉眼秒表耗时。
3. 通过标准：到达率 ≥95%、无强制拦截页、P50 ≤300ms / P99 ≤800ms。
4. 记录表：docs/execution/data/m0/poc3-jump-log.csv
   列：device,ts,url_no,arrived,blocked,ms
5. 不达 → 切 beacon＋服务端关联（+2 人日，ADR-003 重评条件 6）——停下汇报，不自行改架构。
EOF
