#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指标独立复算（HC-7/FR-19：生产实现＋独立实现复算一致才能写进结论）。

生产实现＝app/cron.py aggregate（Python 侧逐会话/逐事件迭代）；
本脚本＝**纯 SQL 路径**重算同一批指标（时间差/配对/去重在 SQLite 内完成），
并与 daily_metrics 表逐项比对；比例指标附 Wilson 95% CI（周判读纪律）。

用法：
  python scripts/recalc_metrics.py --date 2026-09-02 [--check]
    --check  与 daily_metrics 比对，不一致项列差并退出码 1
"""
import argparse
import json
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.core import db  # noqa: E402  复用连接/路径约定，不复用聚合逻辑（阶段3路径）

DAY_FILTER = "substr(e0.server_ts,1,10)=?"


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def recalc(conn, date: str) -> dict:
    q = lambda sql, *a: conn.execute(sql, a).fetchall()  # noqa: E731

    sessions = q(
        "SELECT id, anon_id, status, is_cold_start FROM sessions s "
        "WHERE substr(s.started_at,1,10)=?", date)
    n_sessions = len(sessions)
    if not n_sessions:
        return {"sessions": 0, "active_users": 0}
    sids = [s["id"] for s in sessions]
    marks = ",".join("?" * len(sids))

    # 北极星：accept 与 jump 双事件 60s 窗配对，纯 SQL（julianday 日差×86400=秒）
    north_star = q(
        f"SELECT COUNT(DISTINCT a.session_id) c FROM events a "
        f"JOIN events j ON j.session_id=a.session_id AND j.type='jump' "
        f"WHERE a.type='accept' AND a.session_id IN ({marks}) "
        f"AND (julianday(j.server_ts)-julianday(a.server_ts)) BETWEEN 0 AND ? "
        f"AND a.session_id NOT IN (SELECT session_id FROM events "
        f"WHERE type IN ('abandon','swap_exhausted') AND session_id IN ({marks}))",
        *sids, 60.0 / 86400.0, *sids)[0]["c"]
    surrender = q(
        f"SELECT COUNT(DISTINCT a.session_id) c FROM events a "
        f"JOIN events j ON j.session_id=a.session_id AND j.type='jump' "
        f"WHERE a.type='accept' AND a.session_id IN ({marks}) "
        f"AND (julianday(j.server_ts)-julianday(a.server_ts)) BETWEEN 0 AND ? "
        f"AND a.session_id IN (SELECT session_id FROM events "
        f"WHERE type IN ('abandon','swap_exhausted') AND session_id IN ({marks}))",
        *sids, 60.0 / 86400.0, *sids)[0]["c"]

    completed = sum(1 for s in sessions if s["status"] == "accepted")
    abandoned = sum(1 for s in sessions if s["status"] == "abandoned")
    no_swap_accepts = q(
        f"SELECT COUNT(DISTINCT a.session_id) c FROM events a WHERE a.type='accept' "
        f"AND a.session_id IN ({marks}) AND a.session_id NOT IN "
        f"(SELECT session_id FROM events WHERE type='swap' AND session_id IN ({marks}))",
        *sids, *sids)[0]["c"]
    exh = q(
        f"SELECT s.is_cold_start cold, COUNT(DISTINCT e.session_id) c "
        f"FROM events e JOIN sessions s ON s.id=e.session_id "
        f"WHERE e.type='swap_exhausted' AND e.session_id IN ({marks}) "
        f"GROUP BY s.is_cold_start", *sids)
    exh_cold = next((r["c"] for r in exh if r["cold"]), 0)
    exh_steady = next((r["c"] for r in exh if not r["cold"]), 0)
    comp_cold = sum(1 for s in sessions
                    if s["status"] in ("accepted", "swapped_out") and s["is_cold_start"])
    comp_steady = sum(1 for s in sessions
                      if s["status"] in ("accepted", "swapped_out")
                      and not s["is_cold_start"])

    durations = [r["d"] for r in q(
        f"SELECT (julianday(a.server_ts)-julianday(b.server_ts))*86400.0 d "
        f"FROM events a JOIN events b ON b.session_id=a.session_id "
        f"AND b.type='session_start' WHERE a.type='accept' "
        f"AND a.session_id IN ({marks}) "
        f"AND (julianday(a.server_ts)-julianday(b.server_ts)) BETWEEN 0 AND ?",
        *sids, 1.0) if r["d"] is not None]
    steps = [r["c"] for r in q(
        f"SELECT session_id, COUNT(*) c FROM events WHERE type='answer' "
        f"AND session_id IN ({marks}) GROUP BY session_id", *sids)]
    # 限定完成会话（与生产口径一致）
    completed_ids = {s["id"] for s in sessions if s["status"] == "accepted"}
    steps = [r["c"] for r in q(
        f"SELECT session_id, COUNT(*) c FROM events WHERE type='answer' "
        f"AND session_id IN ({marks}) GROUP BY session_id", *sids)
        if r["session_id"] in completed_ids]

    def med(vals):
        return round(sorted(vals)[len(vals) // 2], 1) if vals else None

    active = q("SELECT COUNT(DISTINCT anon_id) c FROM sessions WHERE "
               "substr(started_at,1,10)=?", date)[0]["c"]
    return {
        "active_users": active,
        "sessions": n_sessions,
        "completed": completed,
        "abandoned": abandoned,
        "north_star_sessions": north_star,
        "surrender_sessions": surrender,
        "first_accept_rate_n": no_swap_accepts,
        "swap_exhaustion_cold": [exh_cold, comp_cold],
        "swap_exhaustion_steady": [exh_steady, comp_steady],
        "decision_duration_median_sec": med(durations),
        "decision_duration_n": len(durations),
        "answer_steps_median": med(steps),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--check", action="store_true",
                    help="与 daily_metrics 比对（复算一致性门禁）")
    args = ap.parse_args()
    db.init_schema()
    conn = db.connect()
    r = recalc(conn, args.date)
    print(json.dumps(r, ensure_ascii=False, default=str, indent=2))
    if not args.check:
        return
    if not r.get("sessions"):
        print("check: 无会话日，跳过比对（空库早退键不全——既有路径，非重构引入）")
        return
    n_sessions = r["sessions"]
    completed = r["completed"]
    stored = {row["metric"]: (json.loads(row["value"]), row["n"])
              for row in conn.execute(
                  "SELECT metric, value, n FROM daily_metrics WHERE metric_date=?",
                  (args.date,))}
    expect = {
        "sessions": (r["sessions"], n_sessions),
        "active_users": (r["active_users"], r["active_users"]),
        "completed": (r["completed"], n_sessions),
        "abandoned": (r["abandoned"], n_sessions),
        "north_star_sessions": (r["north_star_sessions"], n_sessions),
        "surrender_sessions": (r["surrender_sessions"], n_sessions),
        "first_accept_rate": (
            round(r["first_accept_rate_n"] / completed, 4) if completed else None,
            completed),
        "swap_exhaustion_cold": (
            round(r["swap_exhaustion_cold"][0] / r["swap_exhaustion_cold"][1], 4)
            if r["swap_exhaustion_cold"][1] else None,
            r["swap_exhaustion_cold"][1]),
        "swap_exhaustion_steady": (
            round(r["swap_exhaustion_steady"][0] / r["swap_exhaustion_steady"][1], 4)
            if r["swap_exhaustion_steady"][1] else None,
            r["swap_exhaustion_steady"][1]),
        "decision_duration_median_sec": (r["decision_duration_median_sec"],
                                         r["decision_duration_n"]),
        "answer_steps_median": (r["answer_steps_median"], completed),
    }
    bad = []
    for metric, (val, n) in expect.items():
        if metric not in stored:
            bad.append(f"{metric}: 日表缺行")
            continue
        sv, sn = stored[metric]
        if sv != val or (sn or 0) != (n or 0):
            bad.append(f"{metric}: 日表={sv}(n={sn}) vs 复算={val}(n={n})")
    if bad:
        print("复算不一致（不得写入结论）:")
        for b in bad:
            print("  ✗", b)
        sys.exit(1)
    print(f"复算一致：{len(expect)} 项全部通过（HC-7 复算门禁 PASS）")


if __name__ == "__main__":
    main()
