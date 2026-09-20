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


from ..core.notify import notify   # P0-2 收口（sys 缺失顺修）；re-export 兼容既有调用方
