"""web/support——HTTP 层共享 helper＋配置缺省单源＋密钥守卫（阶段3重组）。

依赖方向：web → domain/providers/core（禁被 domain 反向 import）。"""
import json
import os
import re
import sys
import uuid
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from ..core import db
from ..core.config import STATIC_DEFAULTS
from ..core.util import now_iso
from ..providers import env_ctx
from ..domain import memory

# 配置缺省单源（2026-09-16 分层：纯静态键在 core/config——cron 直引不跨层；
# 跨层值 memory/scenes/env/quiz 在此组装，对外 CONFIG_DEFAULTS 不变）
CONFIG_DEFAULTS = {
    **STATIC_DEFAULTS,
    "memory": memory.DEFAULTS,                 # SC-3 参数化
    # 环境上下文（预取注入 2026-09-15）：场景边界支持跨午夜（hi 以 24+ 小时表示）
    "scenes": env_ctx.SCENES_DEFAULT,
    "env": env_ctx.ENV_DEFAULTS,
    # 画像收敛加速：count≥threshold 时收口下限放宽到 min_steps_profiled（P2）；
    # min_steps 5→4＝owner 拍板观察期（2026-09-15 漏斗收敛改造）
    "quiz": {"profile_threshold": 3, "min_steps": 4, "min_steps_profiled": 3},
}



def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status,
                        content={"error": {"code": code, "message": message}})



def _get_session(conn, session_id: str):
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    return row


def _insert_event(conn, *, client_event_id: str, session_id: str, anon_id: str,
                  type_: str, step: Optional[int], payload: dict,
                  client_ts: Optional[str]) -> bool:
    """幂等插入（client_event_id 唯一）；返回是否新插入。"""
    cur = conn.execute(
        "INSERT OR IGNORE INTO events(client_event_id,session_id,anon_id,type,step,"
        "payload,client_ts,server_ts) VALUES(?,?,?,?,?,?,?,?)",
        (client_event_id, session_id, anon_id, type_, step,
         json.dumps(payload, ensure_ascii=False), client_ts, now_iso()))
    return cur.rowcount > 0


def _deep_link(conn, dish_slug: str) -> Optional[str]:
    links = db.get_config("links", CONFIG_DEFAULTS["links"])
    if links.get("status") == "dead":          # 探活全红自动兜底（§1.1 cron）
        return None
    name_row = conn.execute(
        "SELECT dish_name FROM dish_library WHERE dish_slug=? UNION ALL "
        "SELECT dish_name FROM dish_pool WHERE dish_slug=? LIMIT 1",
        (dish_slug, dish_slug)).fetchone()
    kw = name_row["dish_name"] if name_row else dish_slug
    tpl = links.get("templates", {}).get(links.get("default_platform", "meituan"))
    return tpl.replace("{kw}", kw) if tpl else None



def _visited_recently(conn, anon_id: str, days: int) -> bool:
    """回访抽样频控（W-7）：按 anon_id 计最近 N 天曝光/应答，≤1 次/人/周。

    （阶段2旧链删除时被误伤、阶段3拆分时自 git baf3d8d 找回归位——探针未启用时
    短路故冒烟未暴露，翻 enabled 即 500 的隐患。）
    """
    row = conn.execute(
        "SELECT COUNT(*) c FROM events WHERE anon_id=? AND type IN "
        "('visit_probe_show','visit_report') AND server_ts >= datetime('now', ?)",
        (anon_id, f"-{days} days")).fetchone()
    return row["c"] > 0


def _last_accepted_dish(conn, anon_id: str):
    """回访卡菜名回填：最近一次 accept 事件的 dish_slug。"""
    row = conn.execute(
        "SELECT e.payload FROM events e WHERE e.anon_id=? AND e.type='accept' "
        "ORDER BY e.id DESC LIMIT 1", (anon_id,)).fetchone()
    return json.loads(row["payload"]).get("dish_slug") if row else None



def _client_id(request: Request) -> str:
    aid = (request.headers.get("X-Anon-Id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", aid or ""):
        raise HTTPException(status_code=422, detail="missing/invalid X-Anon-Id")
    return aid


def _client_ip(request: Request) -> str:
    """真实客户端 IP（uvicorn forwarded-allow-ips=* 已解析代理头；与限流同源）。
    仅用于天气城市推断（env_ctx），不落库不进日志（隐私口径 2026-09-15）。"""
    return request.client.host if request.client else ""


def _quiz_session_row(sid: int, aid: str):
    return db.connect().execute(
        "SELECT * FROM quiz_session WHERE id=? AND anon_id=?", (sid, aid)).fetchone()


def _ensure_quiz_session_row(tconn, *, sid: int, aid: str, status: str = "presented"):
    """quiz 会话→sessions 表映射（北极星/聚合口径兼容；阶段2收口：原三处重复）。"""
    tconn.execute(
        "INSERT OR IGNORE INTO sessions(id,anon_id,status,is_cold_start,"
        "swap_limit,form,started_at) VALUES(?,?,?,?,?,?,?)",
        (f"sess_quiz_{sid}", aid, status, 1, 2,
         db.get_config("form", "undecided"), now_iso()))


def _quiz_write_event(tconn, *, anon_id, session_id, type_, payload):
    _insert_event(tconn, client_event_id="ev_" + uuid.uuid4().hex,
                  session_id=session_id, anon_id=anon_id, type_=type_,
                  step=None, payload=payload, client_ts=None)


def _guard_insecure_secret(name: str, value: str, dev_marker: str) -> None:
    """工程审查 V-4：密钥缺失/走 dev 兜底时不得静默——prod 拒绝启动，其余告警＋audit。"""
    if value and dev_marker not in value:
        return
    if os.environ.get("WTE_ENV") == "prod":
        raise RuntimeError(f"refuse to start in prod: {name} missing or dev fallback")
    print(f"[WTE-WARN] insecure secret fallback active: {name}", file=sys.stderr)
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO audit_log(ts,actor,action,target,detail,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (now_iso(), "system:api", "insecure_secret_fallback", name,
             json.dumps({"env": os.environ.get("WTE_ENV", "dev")}), now_iso()))
