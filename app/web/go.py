"""web/go——北极星第二事件：302 跳板（token 哈希幂等、首个 jump 生效）。"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from ..core import db, umami
from ..domain import jump
from .support import CONFIG_DEFAULTS, _deep_link, _get_session, _insert_event

router = APIRouter()


@router.get("/go/{go_token}")
def go(go_token: str):
    """北极星第二事件：302 跳板，token 哈希幂等、首个 jump 生效（v3.1 评审 13）。"""
    parsed = jump.verify_token(go_token)
    if parsed is None:
        raise HTTPException(status_code=404, detail="go_token invalid or expired")
    session_id, dish_slug, _ = parsed
    conn = db.connect()
    row = _get_session(conn, session_id)
    with db.tx() as tconn:
        _insert_event(tconn, client_event_id=jump.token_fingerprint(go_token),
                      session_id=session_id, anon_id=row["anon_id"],
                      type_="jump", step=None,
                      payload={"dish_slug": dish_slug}, client_ts=None)
    umami.forward_async()
    link = _deep_link(conn, dish_slug)
    if link is None:
        return Response(status_code=200,
                        content=json.dumps({
                            "error": {"code": "link_dead",
                                      "message": "深链不可用，请手动搜索菜品名"}},
                            ensure_ascii=False),
                        media_type="application/json")
    return RedirectResponse(url=link, status_code=302)

