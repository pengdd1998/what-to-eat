"""web/misc_api——health/回访/假门/埋点批次/冷启画像（未成域的公共面端点）。"""
import json
import os
import shutil
import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from ..core import db, umami
from ..core.util import now_iso
from ..core.events import CLIENT_ALLOWED
from ..domain import memory
from .schemas import EventsBatchIn, FakeDoorRegisterIn, VisitReportIn
from .support import (CONFIG_DEFAULTS, _client_id, _insert_event,
                      _last_accepted_dish, _visited_recently)

router = APIRouter()


# ---------- 端点 ----------

@router.get("/api/health")
def health():
    total, _, free = shutil.disk_usage(
        os.path.dirname(os.path.abspath(db.DB_PATH)) or "/")
    writable = db.db_writable()
    llm_cfg = db.get_config("llm", {})
    umami_ok = bool(db.get_config("umami", {}).get("base_url"))
    return {
        "status": "ok" if writable else "degraded",
        "db_writable": writable,
        "disk_pct": round(100 * (total - free) / total, 1),
        "llm_status": llm_cfg.get("provider", "stub"),
        "umami_status": "configured" if umami_ok else "not_configured",
        "version": f"{db.APP_VERSION}+{db.GIT_SHA}",
        "form": db.get_config("form", "undecided"),
    }


@router.post("/api/visit-report", status_code=204)
def visit_report(body: VisitReportIn):
    """次日回访（FR-16/18）：满意/不满意＋自报下单（M3 起）＋NPS（M2 起）。

    W-7 频控：服务端二次校验 ≤1 次/人/7 天（前端判定可被绕过）。
    """
    conn = db.connect()
    probe_cfg = db.get_config("visit_probe", {"enabled": False})
    if not probe_cfg.get("enabled", False):
        raise HTTPException(status_code=404, detail="visit probe disabled")
    if _visited_recently(conn, body.anon_id, days=7):
        raise HTTPException(status_code=429, detail="visit probe already shown this week")
    with db.tx() as tconn:
        if body.answer == "unsatisfied" and body.dish_slug:  # 回访不满意=−1
            memory.write_memory(tconn, body.anon_id, body.dish_slug, "visit_bad",
                                db.get_config("memory"))
        _insert_event(tconn, client_event_id="ev_" + uuid.uuid4().hex,
                      session_id="visit_" + body.anon_id, anon_id=body.anon_id,
                      type_="visit_report", step=None,
                      payload={"answer": body.answer, "ordered": body.ordered,
                               "nps": body.nps, "dish_slug": body.dish_slug},
                      client_ts=None)
    return Response(status_code=204)


@router.get("/api/session/probe-cards")
def session_probe_cards(request: Request):
    """FR-16/17 卡片探测（轻量，不建会话行）：回访频控＋假门开关＋昨晚菜名。"""
    aid = _client_id(request)
    probe_cfg = db.get_config("visit_probe", CONFIG_DEFAULTS["visit_probe"])
    visit_ok = (probe_cfg.get("enabled", False)
                and not _visited_recently(db.connect(), aid, days=7))
    dish = _last_accepted_dish(db.connect(), aid) if visit_ok else None
    fd = db.get_config("fakedoor", CONFIG_DEFAULTS["fakedoor"])
    return {"visit_probe": {"enabled": bool(visit_ok), "dish_name": dish},
            "fakedoor_enabled": bool(fd.get("enabled", False))}


@router.post("/api/fakedoor/register", status_code=204)
def fakedoor_register(body: FakeDoorRegisterIn):
    """诚实假门登记（FR-17，M3）：仅意向事件，零联系字段（v3.1 评审 10）。

    未启用（config.fakedoor.enabled=false）→ 404；匿名即可登记。
    """
    fcfg = db.get_config("fakedoor", CONFIG_DEFAULTS["fakedoor"])
    if not fcfg.get("enabled", False):
        raise HTTPException(status_code=404, detail="fakedoor disabled")
    with db.tx() as tconn:
        _insert_event(tconn, client_event_id="ev_" + uuid.uuid4().hex,
                      session_id="fakedoor_" + body.anon_id, anon_id=body.anon_id,
                      type_="fakedoor_register", step=None,
                      payload={"anchor_x": body.anchor_x}, client_ts=None)
    return Response(status_code=204)


@router.post("/api/events/batch", status_code=204)
def events_batch(body: EventsBatchIn):
    conn = db.connect()
    wanted = {ev.session_id for ev in body.events}
    placeholders = ",".join("?" * len(wanted))
    rows = conn.execute(
        f"SELECT id, anon_id FROM sessions WHERE id IN ({placeholders})",
        tuple(wanted)).fetchall()
    anon_of = {r["id"]: r["anon_id"] for r in rows}
    for ev in body.events:
        if ev.session_id not in anon_of:
            raise HTTPException(status_code=404,
                                detail=f"session not found: {ev.session_id}")
    inserted = duplicates = 0
    with db.tx() as tconn:
        for ev in body.events:
            ok = _insert_event(tconn, client_event_id=ev.client_event_id,
                               session_id=ev.session_id,
                               anon_id=anon_of[ev.session_id],
                               type_=ev.type, step=ev.step,
                               payload=ev.payload or {}, client_ts=ev.client_ts)
            inserted += 1 if ok else 0
            duplicates += 0 if ok else 1
    umami.forward_async()                        # 游标重放式异步副本（T1.6）
    return Response(status_code=204,
                    headers={"X-Inserted": str(inserted),
                             "X-Duplicates": str(duplicates)})

