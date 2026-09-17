"""core/audit——audit_log 统一写入封装（阶段3：原 10 处 INSERT 字面量收口）。

约定：必须在 db.tx() 事务内调用（与既有调用点一致）；ts 自动取 UTC 秒级。
"""
import json

from . import db
from .util import now_iso


def audit(tconn, actor: str, action: str, target: str, detail) -> None:
    """写审计行。detail 接受 dict（自动 JSON 化）或 str。"""
    if not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False)
    tconn.execute(
        "INSERT INTO audit_log(ts,actor,action,target,detail,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (now_iso(), actor, action, target, detail, now_iso()))
