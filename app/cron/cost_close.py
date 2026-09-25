"""cron/cost_close（阶段3拆分自 app/cron.py）。"""
import json
import os
from datetime import datetime, timezone

from ..core import db
from .common import _today, _write_metric, notify


def cost_close() -> dict:
    """23:59 LLM 成本/用量日结＋Umami 对账（游标滞后＝副本健康度）。"""
    date = _today()
    conn = db.connect()
    row = conn.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(cost_usd),0) cost FROM llm_calls "
        "WHERE substr(ts,1,10)=?", (date,)).fetchone()
    lats = [r[0] for r in conn.execute(
        "SELECT latency_ms FROM llm_calls WHERE substr(ts,1,10)=? AND "
        "status='ok' ORDER BY latency_ms", (date,)).fetchall()]
    p95 = lats[max(0, int(0.95 * len(lats)) - 1)] if lats else 0   # P1-3（W-14）
    mrow = conn.execute(
        "SELECT COALESCE(SUM(cost_usd),0) cost FROM llm_calls "
        "WHERE substr(ts,1,7)=?", (date[:7],)).fetchone()           # 月累计（SC-2）
    ev_total = conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
    cursor = int(db.get_config("umami", {}).get("cursor", 0))
    lag = max(ev_total - cursor, 0)   # clamp：游标含 id 空洞可越过总数，负值无意义

    # ===== LLM 监控日结扩展（llm-monitoring-plan §3.4，9 项）=====
    ok_n = len(lats)
    err_rows = conn.execute(
        "SELECT COALESCE(error_class,'未知') ec, COUNT(*) c FROM llm_calls "
        "WHERE substr(ts,1,10)=? AND status='error' GROUP BY ec",
        (date,)).fetchall()
    err_dist = {r["ec"]: r["c"] for r in err_rows}
    success_rate = round(ok_n / row["c"], 4) if row["c"] else None
    p50 = lats[max(0, len(lats) // 2)] if lats else 0
    soft_to = round(sum(1 for x in lats if x > 3000) / ok_n, 4) if ok_n else None
    retry_rows = conn.execute(
        "SELECT COUNT(*) c FROM llm_calls WHERE substr(ts,1,10)=? AND "
        "COALESCE(attempts,1) > 1", (date,)).fetchone()
    retry_rate = round(retry_rows["c"] / row["c"], 4) if row["c"] else None
    tk = conn.execute(
        "SELECT COALESCE(SUM(tokens_in),0) i, COALESCE(SUM(tokens_out),0) o "
        "FROM llm_calls WHERE substr(ts,1,10)=?", (date,)).fetchone()
    # 能力质量（L4）：出题 LLM 占比 / 收口本地兜底率＋拒因分布
    q_total = conn.execute(
        "SELECT COUNT(*) c FROM quiz_session WHERE substr(created_at,1,10)=? "
        "AND state='done'", (date,)).fetchone()["c"]
    q_llm = q_local = 0
    for r in conn.execute(
            "SELECT question_log, result FROM quiz_session "
            "WHERE substr(created_at,1,10)=? AND state='done'", (date,)):
        try:
            for _q in json.loads(r["question_log"] or "[]"):
                if _q.get("source", "llm") == "local":
                    q_local += 1
                else:
                    q_llm += 1
        except json.JSONDecodeError:
            pass
    q_steps = q_llm + q_local
    q_llm_rate = round(q_llm / q_steps, 4) if q_steps else None
    fin_local = fin_total = 0
    fin_reasons = {}
    for r in conn.execute(
            "SELECT result FROM quiz_session "
            "WHERE substr(created_at,1,10)=? AND state='done'", (date,)):
        try:
            fin = json.loads(r["result"] or "{}")
        except json.JSONDecodeError:
            continue
        fin_total += 1
        if fin.get("source") == "local":
            fin_local += 1
            fin_reasons[fin.get("local_reason", "call_failed")] = \
                fin_reasons.get(fin.get("local_reason", "call_failed"), 0) + 1
    fin_local_rate = round(fin_local / fin_total, 4) if fin_total else None

    # OB-12 磁盘/库体积判定（P0-3，monitoring-workbench-plan §3）：
    # 与 /api/health 同算法同视角（容器内挂载卷）；阈值常量起步
    import shutil as _shutil
    _du = _shutil.disk_usage(os.path.dirname(os.path.abspath(db.DB_PATH)) or "/")
    disk_pct = round(100 * (_du.total - _du.free) / _du.total, 1)
    db_bytes = sum(
        os.path.getsize(db.DB_PATH + suf) for suf in ("", "-wal", "-shm")
        if os.path.exists(db.DB_PATH + suf))
    db_size_mb = round(db_bytes / 1048576, 1)
    # F5（回归轮上调 2026-09-25）：出题拒因分布——「调用成功但题被丢」的
    # 结构化归因（parse/搭配健康/validate 细因/强制下钻拒）；网络失败在
    # llm_calls 已有 error 行，不在此口径。reason 取前两段聚合计数。
    q_rej = {}
    for r in conn.execute(
            "SELECT detail FROM audit_log WHERE action='quiz_q_reject' "
            "AND substr(ts,1,10)=?", (date,)):
        try:
            reason = json.loads(r["detail"]).get("reason", "?")
        except (json.JSONDecodeError, TypeError):
            reason = "?"
        key = ":".join(str(reason).split(":")[:2])
        q_rej[key] = q_rej.get(key, 0) + 1
    with db.tx() as t:
        _write_metric(t, date, "llm_calls", row["c"], row["c"])
        _write_metric(t, date, "llm_cost_usd", round(row["cost"], 4), row["c"])
        _write_metric(t, date, "llm_p95_ms", p95, row["c"])
        _write_metric(t, date, "llm_month_cost_usd", round(mrow["cost"], 4),
                      row["c"])
        _write_metric(t, date, "umami_lag_events", lag, ev_total)
        _write_metric(t, date, "llm_success_rate", success_rate, row["c"])
        _write_metric(t, date, "llm_p50_ms", p50, ok_n)
        _write_metric(t, date, "llm_soft_timeout_rate", soft_to, ok_n)
        _write_metric(t, date, "llm_retry_rate", retry_rate, row["c"])
        _write_metric(t, date, "llm_error_dist", err_dist, row["c"])
        _write_metric(t, date, "llm_tokens_in_sum", tk["i"], row["c"])
        _write_metric(t, date, "llm_tokens_out_sum", tk["o"], row["c"])
        _write_metric(t, date, "quiz_question_llm_rate", q_llm_rate, q_steps)
        _write_metric(t, date, "quiz_finalize_local_rate", fin_local_rate,
                      fin_total)
        _write_metric(t, date, "quiz_reject_reasons", q_rej, sum(q_rej.values()))
        _write_metric(t, date, "disk_pct", disk_pct, None)
        _write_metric(t, date, "db_size_mb", db_size_mb, None)
    # ===== 告警四条（plan §5.1，拍板 B 建议值起步）=====
    if mrow["cost"] > 40:                        # SC-2 月线 $40 → P2（X6 实接）
        notify("LLM 月成本超 $40", f"月累计 ${mrow['cost']:.2f}", "P2")
    if ev_total - cursor > 0 and ev_total - cursor > 5000:
        notify("Umami 游标滞后异常", f"lag={ev_total - cursor}", "P2")
    if success_rate is not None and row["c"] >= 20 and success_rate < 0.9:
        notify("LLM 成功率告警", f"{date} 成功率 {success_rate}（n={row['c']}）", "P2")
    if q_llm_rate is not None and q_steps >= 10 and q_llm_rate < 0.7:
        notify("出题 LLM 占比走低",
               f"{date} llm_rate={q_llm_rate}（n={q_steps}）拒因={q_rej}", "P2")
    if fin_local_rate is not None and fin_total >= 10 and fin_local_rate > 0.3:
        notify("收口本地兜底率偏高", f"{date} local_rate={fin_local_rate} 拒因={fin_reasons}", "P2")

    # P2-2：应用错误聚合（audit app_error 计数→日结；429 已实时 UPSERT）
    app_500 = conn.execute(
        "SELECT COUNT(*) c FROM audit_log WHERE action='app_error' "
        "AND substr(ts,1,10)=?", (date,)).fetchone()["c"]
    r429 = conn.execute(
        "SELECT value FROM daily_metrics WHERE metric_date=? AND "
        "metric='app_429_count'", (date,)).fetchone()
    app_429 = int(float(r429["value"])) if r429 else 0
    with db.tx() as t:
        _write_metric(t, date, "app_500_count", app_500, None)
        _write_metric(t, date, "app_429_count", app_429, None)
    if app_500 > 10:
        notify("P2: 应用 500 偏多", f"{date} n={app_500}", "P2")
    if app_429 > 500:
        notify("P2: 429 限流计数异常（被刷信号）", f"{date} n={app_429}", "P2")

    if disk_pct > 80:                            # OB-12 阈值（预期：当前 82~90 持续触发）
        notify("P2: 磁盘水位 %.1f%%（>80%%）" % disk_pct,
               "db=%.1fMB；磁盘 90%% 升级待办在案" % db_size_mb, "P2")
    if db_size_mb > 500:
        notify("P2: SQLite 库体积 %.1fMB（>500MB，OB-12）" % db_size_mb, "", "P2")

    # P95 连续 3 日 >3000ms（软超时观察项自动化收口）
    p95_hist = [r["value"] for r in conn.execute(
        "SELECT value FROM daily_metrics WHERE metric='llm_p95_ms' AND "
        "metric_date>=date(?, '-2 day') AND metric_date<? ORDER BY metric_date",
        (date, date))] + [json.dumps(p95)]
    try:
        vals = [float(json.loads(v)) for v in p95_hist]
        if len(vals) == 3 and all(v > 3000 for v in vals):
            notify("LLM P95 连续 3 日超软超时", f"近3日 {vals}", "P2")
    except (ValueError, json.JSONDecodeError):
        pass
    return {"date": date, "llm_calls": row["c"], "cost_usd": row["cost"],
            "llm_p95_ms": p95, "llm_month_cost_usd": round(mrow["cost"], 4),
            "umami_lag": ev_total - cursor,
            "llm_success_rate": success_rate, "quiz_question_llm_rate": q_llm_rate,
            "quiz_finalize_local_rate": fin_local_rate,
            "quiz_reject_reasons": q_rej,
            "disk_pct": disk_pct, "db_size_mb": db_size_mb,
            "app_500_count": app_500, "app_429_count": app_429}
