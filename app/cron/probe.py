"""cron/probe（阶段3拆分自 app/cron.py）。"""
import json
import os
import urllib.request   # P0-1（monitoring-workbench-plan §3）：阶段3拆分丢失绑定→全探活 NameError 被 except 吞成假 fail
from datetime import datetime, timezone

from ..core import db
from .common import _today, _write_metric, notify


def probe() -> dict:
    """深链探活：样本 [假设 20–30 菜品词，当前取菜库 top-8＋1 对照]。

    全红且对照绿 → 自动置 links.status=dead＋audit（system:cron）；
    人工次日复核（runbook §5.2.6）。对照 URL 用于判探活器自身故障（SUP-05）。
    """
    conn = db.connect()
    links = db.get_config("links", {})
    date = _today()
    dishes = conn.execute(
        "SELECT dish_name FROM dish_library WHERE active=1 "
        "ORDER BY base_score DESC LIMIT 8").fetchall()
    control = "https://www.baidu.com"          # 对照 [假设：稳定可达]
    from ..core.config import STATIC_DEFAULTS   # 深链模板单源（2026-09-16 消 cron→web 跨层）
    tpl = links.get("templates", {}).get(
        "meituan") or STATIC_DEFAULTS["links"]["templates"]["meituan"]
    from urllib.parse import quote
    # 深链 keyword 须百分号编码（与浏览器行为一致）——原始中文 URL 会被美团拒（2026-09-13 全红误报根因）
    targets = [("ctrl", control)] + [
        (f"link:{d['dish_name'][:12]}",
         tpl.replace("{kw}", quote(d["dish_name"])))
        for d in dishes]
    import time as _time
    results = {}
    for key, url in targets:
        if not url:
            continue
        status = "fail"
        # 2026-09-13 误报加固：单轮 8/8 全红×5s 超时曾误触自动兜底（瞬时抖动，次日复核
        # 全绿恢复）——每条 3 次尝试（HEAD→GET→GET）＋末次 8s 超时＋间隔 1s
        for attempt, method in enumerate(("HEAD", "GET", "GET")):
            try:
                timeout = 8 if attempt == 2 else 5
                req = urllib.request.Request(
                    url, method=method, headers={"User-Agent": "wte-probe/1.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    status = "ok" if resp.status < 400 else "fail"
                if status == "ok":
                    break
            except Exception:
                status = "fail"
            if attempt < 2:
                _time.sleep(1)
        results[key] = status
    with db.tx() as t:
        for key, status in results.items():
            t.execute(
                "INSERT OR REPLACE INTO probe_results(check_date, link_key, "
                "platform, status, detail) VALUES(?,?,?,?,?)",
                (date, key, "meituan", status, ""))
        link_keys = [k for k in results if k.startswith("link:")]
        all_red = link_keys and all(results[k] == "fail" for k in link_keys)
        ctrl_green = results.get("ctrl") == "ok"
        flipped = False
        pending_notify = None
        all_green = link_keys and all(results[k] == "ok" for k in link_keys)
        if (all_red and ctrl_green
                and links.get("status") != "dead"):
            # 评审发现 A（翻转触发）：仅 ok→dead 翻转发 P1＋audit；持续 dead 静默
            # （深链持续死不值得每日 P1 重复打扰——跳转已下线用户面影响为零，§0 发现 B）。
            # config 幂等重写保留（与实际状态对齐，可自愈人为误改）。
            cfg = {**links, "status": "dead"}
            t.execute(
                "INSERT INTO config(key,value,updated_at) VALUES('links',?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(cfg, ensure_ascii=False),
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            t.execute(
                "INSERT INTO audit_log(ts,actor,action,target,detail,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "system:cron", "probe_auto_fallback", "links",
                 json.dumps(results, ensure_ascii=False),
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            flipped = True
            pending_notify = ("P1: 深链探活全红，已自动置全局兜底",
                              json.dumps(results, ensure_ascii=False), "P1")
        elif (all_green and ctrl_green            # 修复事故 2026-09-15：只置死不恢复，
              and links.get("status") == "dead"):  # 全红事件后深链永久卡 dead
            cfg = {**links, "status": "ok"}
            t.execute(
                "INSERT INTO config(key,value,updated_at) VALUES('links',?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(cfg, ensure_ascii=False),
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            t.execute(
                "INSERT INTO audit_log(ts,actor,action,target,detail,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "system:cron", "probe_auto_recover", "links",
                 json.dumps(results, ensure_ascii=False),
                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            flipped = True
            pending_notify = ("P2: 深链探活恢复全绿，links.status 已自动翻回 ok",
                              "", "P2")
    if pending_notify:                        # notify 在 tx 外（禁持锁做网络 IO）
        notify(*pending_notify)
    return {"date": date, "results": results, "auto_fallback": flipped}
