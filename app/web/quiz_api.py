"""web/quiz_api——/api/quiz/* 5 端点＋/api/memory/*（北极星桥接在 support）。"""
import re
import threading

from fastapi import APIRouter, Request

from ..core import db, umami
from ..core.util import now_iso
from ..domain import jump, memory, quiz as quiz_engine
from ..providers import env_ctx
from .support import (CONFIG_DEFAULTS, _client_id, _client_ip, _err,
                      _ensure_quiz_session_row, _quiz_session_row,
                      _quiz_write_event)

router = APIRouter()


@router.post("/api/quiz/session")
def quiz_session_start(request: Request):
    aid = _client_id(request)
    ip = _client_ip(request)
    threading.Thread(target=env_ctx.warm_weather, args=(ip,),
                     daemon=True).start()      # 天气预热：首问时缓存已热（异常全吞）
    s = quiz_engine.create_session(aid)
    with db.tx() as t:
        # FR-15：映射 sessions 行（聚合口径兼容）＋ session_start 事件
        _ensure_quiz_session_row(t, sid=s["id"], aid=aid, status="answering")
        _quiz_write_event(t, anon_id=aid, session_id=f"sess_quiz_{s['id']}",
                          type_="session_start", payload={"engine": "quiz"})
    return {"session_id": s["id"], "step_index": s["step_index"]}


@router.get("/api/quiz/{sid}/next")
def quiz_next(sid: int, request: Request):
    aid = _client_id(request)
    s = _quiz_session_row(sid, aid)
    if not s:
        return _err(404, "no_session", "会话不存在")
    if s["state"] == "done":
        return {"done": True}
    q = quiz_engine.next_question(s, client_ip=_client_ip(request))
    return q


@router.post("/api/quiz/{sid}/answer")
def quiz_answer(sid: int, request: Request, body: dict):
    aid = _client_id(request)
    s = _quiz_session_row(sid, aid)
    if not s:
        return _err(404, "no_session", "会话不存在")
    opt_id = str(body.get("option_id", ""))[:24]
    opt_text = str(body.get("option_text", ""))[:40]
    question = str(body.get("question", ""))[:60]
    s = quiz_engine.answer_option(sid, aid, opt_id, opt_text, question,
                                  bool(body.get("from_local_bank")),
                                  body.get("all_options"))
    with db.tx() as t:
        _quiz_write_event(t, anon_id=aid, session_id=f"sess_quiz_{sid}",
                          type_="answer",
                          payload={"step": s["step_index"], "choice_id": opt_id,
                                   "choice_text": opt_text})
    return {"step_index": s["step_index"], "done": s["state"] == "done"}


@router.post("/api/quiz/{sid}/finalize")
def quiz_finalize(sid: int, request: Request):
    """收口：锁外调 LLM（quiz.py 三段式红线），短事务落结果＋FR-15 事件。"""
    aid = _client_id(request)
    s = _quiz_session_row(sid, aid)
    if not s:
        return _err(404, "no_session", "会话不存在")
    r = quiz_engine.finalize(sid, aid, client_ip=_client_ip(request))
    s = _quiz_session_row(sid, aid)          # 换片剩余计数（P0-1）透传
    if s is not None:
        limits = db.get_config("swap_limits", {"cold": 3, "steady": 2})
        r["swaps_left"] = max(0, int(limits.get("steady", 2)) - (s["swap_count"] or 0))
    # slug 保留中文（修复事故 2026-09-15：旧算法只留 [a-z0-9]，中文菜名全滤成 "dish"，
    # 深链 keyword 失义）——quiz 菜名不在 dish_library/pool 时，中文 slug 即搜索词
    dish_slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", r["name"].lower()).strip("-")[:64] or "dish"
    with db.tx() as t:
        sess_id = f"sess_quiz_{sid}"
        _ensure_quiz_session_row(t, sid=sid, aid=aid)
        _quiz_write_event(t, anon_id=aid, session_id=sess_id,
                          type_="result_served",
                          payload={"dish_slug": dish_slug, "name": r["name"],
                                   "source": r.get("source", "llm"),
                                   "tags": r.get("tags", [])})
        _quiz_write_event(t, anon_id=aid, session_id=sess_id,
                          type_="recommend_exposure",
                          payload={"dish_slug": dish_slug})
    token = jump.make_token(sess_id, dish_slug)
    return {"name": r["name"], "reason": r.get("reason", ""),
            "tags": r.get("tags", []), "dish_slug": dish_slug,
            "go_token": token,
            "swaps_left": r.get("swaps_left")}   # P0-1 换片计数（前端 renderSwapCounter）


@router.post("/api/quiz/{sid}/accept")
def quiz_accept(sid: int, request: Request, body: dict):
    """北极星第一事件（quiz 引擎版）：accept＋记忆+1＋go_token。"""
    aid = _client_id(request)
    dish_slug = str(body.get("dish_slug", ""))[:64]
    sess_id = f"sess_quiz_{sid}"
    with db.tx() as t:
        _ensure_quiz_session_row(t, sid=sid, aid=aid)
        _quiz_write_event(t, anon_id=aid, session_id=sess_id, type_="accept",
                          payload={"dish_slug": dish_slug})
        try:
            memory.write_memory(t, aid, dish_slug, "accept",
                                db.get_config("memory"))
        except Exception:
            pass
        t.execute("UPDATE sessions SET status='accepted', ended_at=? WHERE id=?",
                  (now_iso(), sess_id))
    umami.forward_async()
    return {"go_token": jump.make_token(sess_id, dish_slug)}


@router.post("/api/quiz/{sid}/swap")
def quiz_swap(sid: int, request: Request):
    """换一（灯箱换片，P0-1）：校验属主→引擎 swap→前端重 finalize。"""
    aid = _client_id(request)
    s = _quiz_session_row(sid, aid)
    if not s:
        return _err(404, "no_session", "会话不存在")
    limits = db.get_config("swap_limits", {"cold": 3, "steady": 2})
    # 简化取 max（画像充分判冷/稳态在收口时已用步数体现；口径记录于迭代日志）
    max_swaps = int(limits.get("steady", 2))
    try:
        out = quiz_engine.swap(sid, aid, max_swaps)
    except ValueError as e:
        return _err(409, str(e), "当前状态不可换一")
    if out.get("exhausted"):
        with db.tx() as t:
            _quiz_write_event(t, anon_id=aid, session_id=f"sess_quiz_{sid}",
                              type_="swap_exhausted", payload={"nth": max_swaps})
        return _err(409, "swap_limit_reached", "换一次数已用完，今天就吃这个吧")
    umami.forward_async()
    return out


@router.get("/api/memory")
def memory_list(request: Request):
    aid = _client_id(request)
    return {"items": quiz_engine.list_memory(aid),
            "summary": quiz_engine.taste_summary(aid)}


@router.post("/api/memory/{rec_id}/feedback")
def memory_feedback(rec_id: int, request: Request, body: dict):
    aid = _client_id(request)
    try:
        quiz_engine.feedback_recommendation(rec_id, aid, int(body.get("score", 999)))
    except (ValueError, LookupError) as e:
        return _err(404 if isinstance(e, LookupError) else 422,
                    "bad_feedback", str(e))
    return {"ok": True}
