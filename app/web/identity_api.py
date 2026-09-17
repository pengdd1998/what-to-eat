"""web/identity_api——/api/identity/*（bootstrap/passphrase/recover/data/passcode）。"""
import json
import re
import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from ..core import db
from ..domain import identity
from ..core.util import now_iso
from .schemas import PasscodeIn
from .support import _client_id, _err

router = APIRouter()


@router.post("/api/identity/bootstrap")
def identity_bootstrap(request: Request):
    """首访（FR-11）：返回（或新建）匿名标识＋是否已设口令。
    bootstrap 是身份链起点：X-Anon-Id 缺失/非法时服务端生成新标识返回
    （真机事故 2026-09-15：首访即 422 死锁，永远拿不到身份）。其余端点仍强制校验。"""
    raw = (request.headers.get("X-Anon-Id") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{4,64}", raw or ""):
        aid = raw
    else:
        aid = uuid.uuid4().hex  # 32 位 hex，匹配 [A-Za-z0-9_-]{4,64}
    row = db.connect().execute(
        "SELECT passcode_hash FROM identity WHERE anon_id=?", (aid,)).fetchone()
    if not row:                                  # 首访落 identity 行（无口令）
        with db.tx() as t:
            t.execute(
                "INSERT OR IGNORE INTO identity(anon_id,passcode_salt,passcode_hash,"
                "created_at,recovery_count,locked_until) VALUES(?,?,?,?,0,NULL)",
                (aid, None, None, now_iso()[:10]))
    has_pw = bool(row and row["passcode_hash"]) if row else False
    return {"anon_id": aid, "has_passphrase": has_pw}


@router.post("/api/identity/passphrase")
def identity_set_passphrase(request: Request, body: dict):
    """设置口令（复刻前端契约）→ 映射生产 passcode 存储（W-2 后逻辑复用）。"""
    aid = _client_id(request)
    ok, reason = identity.set_passcode(aid, str(body.get("passphrase", "")))
    if not ok:
        return _err(422, "weak_passphrase", reason)
    return {"ok": True}


@router.post("/api/identity/recover")
def identity_recover(request: Request, body: dict):
    """凭 匿名标识＋口令 找回（复刻前端契约）→ 映射生产 recover 语义。"""
    aid = re.sub(r"[^A-Za-z0-9]", "", str(body.get("anon_id", "")))[:64]
    pw = str(body.get("passphrase", ""))
    if not aid:
        return _err(422, "invalid_identity", "请输入匿名标识")
    state, _ = identity.try_recover(aid, pw)
    if state == "not_found":
        return _err(404, "not_found", "未找到该标识的口令记录")
    if state == "locked":
        return _err(423, "locked", "口令错误，剩余锁定 24 小时内")
    if state == "ok":
        return {"ok": True, "anon_id": aid}
    return _err(403, "wrong_passphrase", "口令不正确")


@router.delete("/api/identity/data")
def identity_clear_data(request: Request):
    """一键清空该匿名标识的全部数据（FR-11 一键清空）。"""
    aid = _client_id(request)
    with db.tx() as t:
        for tbl in ("memory_events", "recommendation", "quiz_session",
                    "preference_profile"):
            t.execute(f"DELETE FROM {tbl} WHERE anon_id=?", (aid,))
        t.execute("DELETE FROM sessions WHERE anon_id=?", (aid,))
        t.execute("DELETE FROM identity WHERE anon_id=?", (aid,))
        t.execute(
            "INSERT INTO audit_log(ts,actor,action,target,detail,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (now_iso(), f"anon:{aid[:6]}", "data_cleared", aid, "{}", now_iso()))
    return {"ok": True}


@router.post("/api/identity/passcode")
def passcode(body: PasscodeIn):
    """口令恢复常设能力（FR-11）。

    口径收敛（工程审查 W-2，2026-09-04）：recover **必须携带 anon_id**——
    移除全表扫描模式（≤500 行 ×PBKDF2(120k) 的 CPU 放大面）；UI 侧标识
    常设可见可复制（FR-11），携带无摩擦。行级锁定/弱口令策略不变。
    """
    conn = db.connect()
    if body.action == "set":
        if not body.anon_id:
            raise HTTPException(status_code=422, detail="set requires anon_id")
        ok, reason = identity.set_passcode(body.anon_id, body.passcode)
        if not ok:
            raise HTTPException(status_code=422, detail=f"weak passcode: {reason}")
        return Response(status_code=204)

    # recover（必须带 anon_id；W-2 收敛）
    if not body.anon_id:
        raise HTTPException(status_code=422,
                            detail="recover requires anon_id（见「我的标识」页）")
    state, _ = identity.try_recover(body.anon_id, body.passcode)
    if state == "not_found":
        raise HTTPException(status_code=404, detail="identity not found")
    if state == "locked":
        raise HTTPException(status_code=403, detail="locked 24h")
    if state == "ok":
        return {"anon_id": body.anon_id}
    raise HTTPException(status_code=403, detail="passcode mismatch")

