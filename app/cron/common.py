"""cron 公共件：notify（Server酱/ntfy 告警）＋指标写入 helper。"""
import json
import os
import urllib.request
from datetime import datetime, timezone


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _write_metric(conn, date: str, metric: str, value, n=None):
    conn.execute(
        "INSERT INTO daily_metrics(metric_date, metric, value, n) VALUES(?,?,?,?) "
        "ON CONFLICT(metric_date, metric) DO UPDATE SET value=excluded.value, "
        "n=excluded.n",
        (date, metric, json.dumps(value, ensure_ascii=False), n))


def notify(title: str, body: str = "", priority: str = "P1") -> bool:
    """X6 个人告警发送（U10）：Server酱 / ntfy 双通道，key 仅环境变量注入。

    任一通道成功即返回 True；双通道失败打 stderr（不抛——告警失败不掩盖主流程）。
    P1＝立即触达；P2＝随日结批处理顺带（调用方自定频率）。
    """
    import urllib.parse
    sent = False
    key = os.environ.get("SERVERCHAN_SENDKEY", "")
    if key:                                    # Server酱（微信）
        try:
            data = urllib.parse.urlencode(
                {"title": f"[{priority}] {title}", "desp": body}).encode()
            req = urllib.request.Request(
                f"https://sctapi.ftqq.com/{key}.send", data=data)
            urllib.request.urlopen(req, timeout=5).read()
            sent = True
        except Exception as e:
            print(f"[notify] serverchan fail: {e}", file=sys.stderr)
    topic = os.environ.get("NTFY_TOPIC", "")
    if topic:                                  # ntfy（Android 应用订阅）
        try:
            req = urllib.request.Request(
                f"https://ntfy.sh/{topic}",
                data=f"[{priority}] {title}\n{body}".encode(),
                headers={"Title": f"[{priority}] {title}",
                         "Priority": "high" if priority == "P1" else "default"})
            urllib.request.urlopen(req, timeout=5).read()
            sent = True
        except Exception as e:
            print(f"[notify] ntfy fail: {e}", file=sys.stderr)
    if not sent:
        print(f"[notify] no channel configured (SERVERCHAN_SENDKEY/NTFY_TOPIC)",
              file=sys.stderr)
    return sent
