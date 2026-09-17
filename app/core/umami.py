"""Umami 游标重放式双写（T1.6；§2.2 v3.1 评审 12）。

设计：SQLite events 为唯一口径源；Umami＝按 id 游标重放的异步副本——无独立
队列，进程重启不丢在途事件，断流后从游标补发。目标未配置（X4 未部署）时
静默跳过＝占位。日结对账（差异 >1% 告警）在 cron 侧（cost_close 的 umami_lag）。

发送格式：Umami v2 /api/send 每请求一个事件对象——逐事件发送，游标推进到
最后一个成功事件（中途失败则停在最后成功处，剩余待下次补发）。
"""
import json
import threading
import urllib.request

from . import db


def _cfg() -> dict:
    return db.get_config("umami", {})


def forward_pending(conn=None) -> dict:
    """把游标之后的事件转发到 Umami；按成功推进游标。返回统计。"""
    cfg = _cfg()
    base_url = cfg.get("base_url")
    website_id = cfg.get("website_id")
    if not (base_url and website_id):
        return {"skipped": "not_configured"}
    conn = conn or db.connect()
    cursor = int(cfg.get("cursor", 0))
    rows = conn.execute(
        "SELECT id, type, payload, session_id, server_ts FROM events "
        "WHERE id > ? ORDER BY id LIMIT ?",
        (cursor, int(cfg.get("batch", 100)))).fetchall()
    if not rows:
        return {"forwarded": 0}
    sent = 0
    last_ok = None
    for r in rows:
        body = {
            "type": "event",
            "payload": {
                "website": website_id,
                "hostname": cfg.get("hostname", "chishenma.top"),
                "url": "/" + r["type"],          # Umami v3 必填（缺则静默丢弃）
                "name": r["type"],
                "data": {"session_id": r["session_id"],
                         "payload": json.loads(r["payload"]),
                         "server_ts": r["server_ts"]},
            },
        }
        req = urllib.request.Request(
            base_url.rstrip("/") + "/api/send",
            data=json.dumps(body).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        # Umami v3 校验 UA 需浏览器格式（自定义 UA 被静默丢弃，T1.6 预验实测）
        req.add_header("User-Agent",
                       "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 wte-forwarder/1.0")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception:
            break                            # 游标停在最后成功处，下次补发
        sent += 1
        last_ok = r["id"]
    if last_ok is not None and last_ok > cursor:
        with db.tx() as tconn:
            tconn.execute(
                "INSERT INTO config(key,value,updated_at) VALUES('umami',?,"
                "datetime('now')) ON CONFLICT(key) DO UPDATE SET "
                "value=excluded.value",
                (json.dumps({**cfg, "cursor": last_ok}, ensure_ascii=False),))
    return {"forwarded": sent, "cursor": last_ok}


def forward_async() -> None:
    """写路径后尽力转发（守护线程，失败静默——游标保证不丢）。"""

    def _run():
        try:
            forward_pending()
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()
