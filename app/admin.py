"""Admin 内网面（T1.9）——独立 ASGI app，与公共面物理分离（§4.1 评审 8）。

部署形态：仅监听 127.0.0.1/内网端口（compose admin 服务 127.0.0.1:8001，
SSH 隧道到达）；生产另有 Caddy 对公网 /api/admin 403（X5 后补）。
鉴权：Bearer ADMIN_TOKEN（环境变量，≥64 字符随机）；全部调用写 audit_log。
config 三道闸（§1.3）：Schema 校验 → 写后冒烟 → 失败自动回滚（before 恢复）。
"""
import csv
import hmac
import io
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .web import llm_dash

import os as _os
templates = Jinja2Templates(directory=_os.path.join(
    _os.path.dirname(__file__), "templates", "admin"))
# 自动转义保持默认开启（N3 修复：SVG 经 |safe 精确放行，其余变量默认转义防 XSS）

from .core import db
from .core.util import now_iso
from .domain.strategy import get_strategy

from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def _lifespan(_app):
    """独立进程自初始化（幂等）＋密钥守卫（工程审查 V-4/W-3 批次）。"""
    db.init_schema()
    if not os.environ.get("ADMIN_TOKEN"):
        if os.environ.get("WTE_ENV") == "prod":
            raise RuntimeError(
                "refuse to start in prod: ADMIN_TOKEN missing or dev fallback")
        print("[WTE-WARN] insecure secret fallback active: ADMIN_TOKEN",
              file=sys.stderr)
    yield


admin_app = FastAPI(title="what-to-eat-admin", version=db.APP_VERSION,
                    docs_url=None, redoc_url=None, lifespan=_lifespan)

DEV_TOKEN = "dev-admin-token-do-not-use-in-prod-0000000000000000000000000000"
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN") or DEV_TOKEN  # 生产必须注入（SUP-02）

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def audit(action: str, target: str = None, detail: dict = None) -> None:
    with db.tx() as conn:
        conn.execute(
            "INSERT INTO audit_log(ts,actor,action,target,detail,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (_now(), "owner", action, target,
             json.dumps(detail or {}, ensure_ascii=False), _now()))


def require_basic(request: Request) -> bool:
    """看板 HTTP Basic（拍板 A 2026-09-16）：ADMIN_TOKEN 同值作密码，恒时比较；
    三层防线（回环/隧道/Caddy 403）不变，Basic 是第四层。"""
    auth = request.headers.get("authorization", "")
    import base64 as _b64
    ok = False
    if auth.startswith("Basic "):
        try:
            user_pwd = _b64.b64decode(auth[6:]).decode("utf-8", "ignore")
            ok = hmac.compare_digest(user_pwd, f"owner:{ADMIN_TOKEN}")
        except Exception:
            ok = False
    if not ok:
        raise HTTPException(
            status_code=401, detail="basic auth required",
            headers={"WWW-Authenticate": 'Basic realm="wte-admin"'})
    return True


def require_token(request: Request):
    auth = request.headers.get("authorization", "")
    try:                                          # 工程审查 W-3：恒时比较防时序侧信道
        ok = hmac.compare_digest(auth, f"Bearer {ADMIN_TOKEN}")
    except TypeError:                             # 非 ASCII 头等无法比较的输入
        ok = False
    if not ok:
        raise HTTPException(status_code=401, detail="admin token required")
    return True




# ---- config 三道闸 ----

def validate_config(key: str, value) -> None:
    """闸 1：Schema 校验（键白名单＋类型/范围）。"""
    if key == "form":
        if value not in ("A", "C", "undecided"):
            raise ValueError("form must be A|C|undecided")
    elif key == "swap_limits":
        if not (isinstance(value, dict)
                and isinstance(value.get("cold"), int) and 2 <= value["cold"] <= 3
                and isinstance(value.get("steady"), int) and 1 <= value["steady"] <= 3):
            raise ValueError("swap_limits: {cold:2-3, steady:1-3}")
    elif key == "cold_start_threshold":
        if not (isinstance(value, int) and 1 <= value <= 20):
            raise ValueError("cold_start_threshold: int 1-20")
    elif key == "memory":
        if not (isinstance(value, dict)
                and isinstance(value.get("window"), int)
                and isinstance(value.get("half_life_days"), (int, float))
                and isinstance(value.get("weights"), dict)):
            raise ValueError("memory: window/half_life_days/weights")
    elif key == "llm":
        if not (isinstance(value, dict)
                and value.get("provider") in ("stub", "openai_compatible")):
            raise ValueError("llm: provider stub|openai_compatible")
    elif key == "links":
        tpl = value.get("templates", {}) if isinstance(value, dict) else {}
        if not (isinstance(value, dict) and value.get("status") in
                ("assumed_ok", "dead") and isinstance(tpl, dict)):
            raise ValueError("links: status + templates")
        for p, u in tpl.items():
            if "{kw}" not in u:
                raise ValueError(f"links.templates.{p} must contain {{kw}}")
    elif key == "visit_probe":
        if not (isinstance(value, dict)
                and isinstance(value.get("enabled"), bool)
                and 0 <= value.get("probability", 0) <= 1):
            raise ValueError("visit_probe: enabled + probability")
    elif key == "scenes":
        # 环境上下文（2026-09-15 预取注入）：场景边界 [起,止) 小时，止可 >24 表跨午夜
        if not (isinstance(value, dict) and value
                and all(isinstance(v, list) and len(v) == 2
                        and all(isinstance(x, (int, float)) and 0 <= x <= 30 for x in v)
                        for v in value.values())):
            raise ValueError("scenes: {场景名: [起,止] 小时 0-30}")
    elif key == "env":
        if not (isinstance(value, dict)
                and isinstance(value.get("weather_enabled"), bool)
                and isinstance(value.get("ttl_min"), int) and value["ttl_min"] >= 5
                and isinstance(value.get("timeout_s"), (int, float))
                and 0 < value["timeout_s"] <= 5):
            raise ValueError("env: weather_enabled + ttl_min>=5 + timeout_s(0,5]")
    elif key == "quiz":
        if not (isinstance(value, dict)
                and isinstance(value.get("profile_threshold"), int)
                and 1 <= value["profile_threshold"] <= 20
                and isinstance(value.get("min_steps_profiled"), int)
                and 2 <= value["min_steps_profiled"] <= 5
                and isinstance(value.get("min_steps"), int)
                and 2 <= value["min_steps"] <= 8):
            raise ValueError("quiz: profile_threshold 1-20 + min_steps(_profiled) 2-8")
    else:
        raise ValueError(f"config key not manageable: {key}")


def smoke_config(key: str) -> None:
    """闸 2：写后模拟下发冒烟——形态开关可实例化、菜库可出结果。"""
    conn = db.connect()
    if get_strategy(conn, db.get_config("form", "undecided")) is None:
        raise RuntimeError("strategy factory failed")
    n = conn.execute("SELECT COUNT(*) c FROM dish_library WHERE active=1").fetchone()["c"]
    if n < 1:
        raise RuntimeError("dish_library empty")


class ConfigIn(BaseModel):
    key: str
    value: Any


@admin_app.exception_handler(RequestValidationError)
async def ve(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422,
                        content={"error": {"code": "invalid_request",
                                           "message": str(exc.errors()[:2])}})


@admin_app.get("/api/health")
def admin_health():
    return {"status": "ok", "db_writable": db.db_writable(),
            "version": f"{db.APP_VERSION}+{db.GIT_SHA}"}


@admin_app.get("/api/admin/config", dependencies=[Depends(require_token)])
def get_all_config():
    rows = db.connect().execute(
        "SELECT key, value, updated_at FROM config ORDER BY key").fetchall()
    return {"config": {r["key"]: json.loads(r["value"]) for r in rows}}


@admin_app.post("/api/admin/config", dependencies=[Depends(require_token)])
def set_config(body: ConfigIn):
    try:
        validate_config(body.key, body.value)      # 闸 1
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    before = db.get_config(body.key)               # 闸 3 的回滚点
    db.set_config(body.key, body.value)
    try:
        smoke_config(body.key)                     # 闸 2
    except Exception as e:
        db.set_config(body.key, before)            # 闸 3：失败自动回滚
        audit("config_change", body.key, {"status": "rolled_back", "error": str(e),
                                          "before": before})
        raise HTTPException(status_code=409, detail=f"smoke failed, rolled back: {e}")
    audit("config_change", body.key, {"status": "ok", "before": before,
                                      "after": body.value})
    return {"ok": True}


@admin_app.get("/api/admin/export", dependencies=[Depends(require_token)])
def export(table: str, date: Optional[str] = None):
    if table not in ("daily_metrics", "events", "sessions", "llm_calls",
                     "batch_runs", "audit_log"):
        raise HTTPException(status_code=422, detail="table not exportable")
    conn = db.connect()
    if table == "daily_metrics" and date:
        rows = conn.execute(
            "SELECT * FROM daily_metrics WHERE metric_date=? ORDER BY metric",
            (date,)).fetchall()
    elif table == "events" and date:
        rows = conn.execute(
            "SELECT * FROM events WHERE substr(server_ts,1,10)=? ORDER BY id",
            (date,)).fetchall()
    else:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()

    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        if rows:
            w.writerow(rows[0].keys())
            yield buf.getvalue()
            buf.truncate(0)
            buf.seek(0)
        for r in rows:
            w.writerow(list(r))
            yield buf.getvalue()
            buf.truncate(0)
            buf.seek(0)
    audit("export", table, {"date": date, "rows": len(rows)})
    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition":
                                      f'attachment; filename="{table}.csv"'})


@admin_app.get("/api/admin/batch", dependencies=[Depends(require_token)])
def list_batches():
    rows = db.connect().execute(
        "SELECT * FROM batch_runs ORDER BY id DESC LIMIT 50").fetchall()
    return {"batches": [dict(r) for r in rows]}


@admin_app.post("/api/admin/batch/{batch_id}/activate",
                dependencies=[Depends(require_token)])
def activate_batch(batch_id: int):
    conn = db.connect()
    row = conn.execute("SELECT * FROM batch_runs WHERE id=?", (batch_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="batch not found")
    with db.tx() as tconn:                       # 激活新批次＝旧池下线（周更语义）
        tconn.execute("UPDATE dish_pool SET active=0 WHERE batch_id != ?",
                      (row["id"],))
        tconn.execute("UPDATE dish_pool SET active=1 WHERE batch_id=?",
                      (row["id"],))
        tconn.execute("UPDATE batch_runs SET status='active' WHERE id=?",
                      (row["id"],))
    audit("batch_activate", str(batch_id), {})
    return {"ok": True}


@admin_app.post("/api/admin/wipe/{anon_id}", dependencies=[Depends(require_token)])
def wipe(anon_id: str):
    """按 anon_id 清除（FR-11 一键清空的服务端面；audit 留痕）。"""
    with db.tx() as conn:
        for table in ("events", "memory_events", "preference_profile", "sessions"):
            conn.execute(f"DELETE FROM {table} WHERE anon_id=?", (anon_id,))
        conn.execute("DELETE FROM identity WHERE anon_id=?", (anon_id,))
    audit("data_wipe", anon_id, {})
    return {"ok": True}


@admin_app.get("/api/admin/audit", dependencies=[Depends(require_token)])
def audit_log(limit: int = 50):
    rows = db.connect().execute(
        "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (min(limit, 500),)
    ).fetchall()
    return {"audit": [dict(r) for r in rows]}


# ---- LLM 监控看板（llm-monitoring-plan §4，P1） ----

@admin_app.get("/admin/llm")
def llm_dashboard(request: Request, days: int = 14):
    require_basic(request)
    days = max(2, min(days, 90))
    data = llm_dash.overview(days)
    t = data["trend"]
    audit("llm_dashboard_view", "llm", {"days": days})
    return templates.TemplateResponse(request, "llm.html", {
        "days": days, "card": {**data["card"], "date": data["today"]},
        "detail": data["detail"], "audit": data["audit"],
        "svg_p95": llm_dash.svg_line(t["llm_p95_ms"], color="#e8b93e",
                                     ref_line=3000, ref_label="软超时 3000ms"),
        "svg_cost": llm_dash.svg_bars(t["llm_cost_usd"], color="#7bc8a4",
                                      ref_line=40 / days, ref_label="月$40日均",
                                      fmt="${:.2f}"),
        "svg_calls": llm_dash.svg_bars(t["llm_calls"], color="#8aa8d8",
                                       fmt="{:.0f}"),
        "svg_success": llm_dash.svg_line(
            [None if v is None else v * 100 for v in t["llm_success_rate"]],
            color="#7bc8a4", fmt="{:.0f}%"),
        "svg_local": llm_dash.svg_bars(
            [None if v is None else v * 100 for v in t["quiz_finalize_local_rate"]],
            color="#e88d5a", fmt="{:.0f}%"),
        "svg_ql": llm_dash.svg_line(
            [None if v is None else v * 100 for v in t["quiz_question_llm_rate"]],
            color="#8aa8d8", ref_line=70, ref_label="目标 70%", fmt="{:.0f}%"),
    })


@admin_app.get("/api/admin/llm/overview")
def llm_overview(request: Request, days: int = 14):
    require_token(request)
    return llm_dash.overview(max(2, min(days, 90)))
