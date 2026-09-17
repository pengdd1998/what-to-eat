"""LLM 监控看板数据聚合＋服务端 SVG（llm-monitoring-plan §4，Admin 面专属）。

零 JS 零构建：折线/柱状/堆叠全部服务端拼 SVG 字符串，模板内联输出。
数据源：趋势读 daily_metrics（聚合压力留给 cron）；当日概览/明细实时只读
SQL（db.connect()，不触 SQLite 单连接写红线）。prompt 原文永不进本模块。
"""
import json
from datetime import datetime, timedelta, timezone

from ..core import db

PALETTE = ["#e8b93e", "#7bc8a4", "#e88d5a", "#8aa8d8", "#c98ad8", "#d87d7d"]


def overview(days: int = 14) -> dict:
    """看板数据总装：概览卡＋四区。"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    trend = _trend(days)
    today_card = _today_card(today)
    detail = _detail_rows(today)
    audit = _audit_rows()
    return {"today": today, "days": days, "trend": trend,
            "card": today_card, "detail": detail, "audit": audit}


def _trend(days: int) -> dict:
    """daily_metrics 拉趋势（每 metric 一条 {date, value} 序列，空日补 None）。"""
    conn = db.connect()
    start = (datetime.now(timezone.utc) - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    dates = [(datetime.now(timezone.utc) - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
             for i in range(days)]
    out = {"dates": dates}
    for metric in ("llm_p95_ms", "llm_p50_ms", "llm_cost_usd", "llm_calls",
                   "llm_success_rate", "quiz_question_llm_rate",
                   "quiz_finalize_local_rate"):
        rows = {r["metric_date"]: _num(r["value"])
                for r in conn.execute(
                    "SELECT metric_date, value FROM daily_metrics "
                    "WHERE metric=? AND metric_date>=?", (metric, start))}
        out[metric] = [rows.get(d) for d in dates]
    return out


def _num(v):
    try:
        f = float(json.loads(v)) if isinstance(v, str) and v.startswith(("{", "[", '"')) else float(v)
        return f
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _today_card(today: str) -> dict:
    conn = db.connect()
    r = conn.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(cost_usd),0) cost FROM llm_calls "
        "WHERE substr(ts,1,10)=?", (today,)).fetchone()
    ok = conn.execute(
        "SELECT COUNT(*) c FROM llm_calls WHERE substr(ts,1,10)=? AND status='ok'",
        (today,)).fetchone()["c"]
    lats = [x[0] for x in conn.execute(
        "SELECT latency_ms FROM llm_calls WHERE substr(ts,1,10)=? AND status='ok' "
        "ORDER BY latency_ms", (today,))]
    p95 = lats[max(0, int(0.95 * len(lats)) - 1)] if lats else None
    month = conn.execute(
        "SELECT COALESCE(SUM(cost_usd),0) c FROM llm_calls WHERE substr(ts,1,7)=?",
        (today[:7],)).fetchone()["c"]
    breaker = conn.execute(
        "SELECT COUNT(*) c FROM audit_log WHERE action='llm_circuit_break' "
        "AND substr(ts,1,10)=?", (today,)).fetchone()["c"]
    m = conn.execute(
        "SELECT value FROM daily_metrics WHERE metric='quiz_question_llm_rate' "
        "AND metric_date=?", (today,)).fetchone()
    return {"calls": r["c"], "cost": round(r["cost"], 4), "p95": p95,
            "success_rate": round(ok / r["c"], 4) if r["c"] else None,
            "month_cost": round(month, 4),
            "budget_pct": round(month / 40 * 100, 1),
            "breaker": breaker,
            "question_llm_rate": _num(m["value"]) if m else None}


def _detail_rows(today: str, limit: int = 50):
    conn = db.connect()
    return [dict(r) for r in conn.execute(
        "SELECT ts, vendor, task, scene, latency_ms, tokens_in, tokens_out, "
        "cost_usd, status, error_class, attempts FROM llm_calls "
        "ORDER BY id DESC LIMIT ?", (limit,))]


def _audit_rows(limit: int = 20):
    conn = db.connect()
    return [dict(r) for r in conn.execute(
        "SELECT ts, actor, action, detail FROM audit_log WHERE "
        "action LIKE 'llm%' OR target='links' ORDER BY id DESC LIMIT ?",
        (limit,))]


# ---------- SVG 生成器（服务端拼字符串，空态安全） ----------
def svg_line(values, w=560, h=160, color="#e8b93e", ref_line=None,
             ref_label=None, fmt="{:.0f}"):
    """折线图：values 含 None（空日断线）；ref_line＝水平参考线（如 3000ms）。"""
    pts = [v for v in values if v is not None]
    if not pts:
        return f'<svg width="{w}" height="{h}" class="empty"><text x="{w//2}" y="{h//2}" text-anchor="middle" fill="#888">暂无数据</text></svg>'
    vmax = max(max(pts), ref_line or 0) * 1.08 or 1
    pad, bw = 34, w - 50
    xs = lambda i: pad + bw * i / max(len(values) - 1, 1)
    ys = lambda v: h - 24 - (h - 44) * (v / vmax)
    segs, cur = [], []
    for i, v in enumerate(values):
        if v is None:
            if len(cur) > 1:
                segs.append(" ".join(cur))
            cur = []
        else:
            cur.append(f"{xs(i):.1f},{ys(v):.1f}")
    if len(cur) > 1:
        segs.append(" ".join(cur))
    parts = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" class="chart">']
    for gi in range(1, 4):
        gy = 24 + (h - 48) * gi / 4
        parts.append(f'<line x1="{pad}" y1="{gy:.0f}" x2="{w-16}" y2="{gy:.0f}" stroke="#333" stroke-width="0.5"/>')
        parts.append(f'<text x="{pad-4}" y="{gy+3:.0f}" text-anchor="end" font-size="9" fill="#888">{fmt.format(vmax*(1-gi/4))}</text>')
    if ref_line and vmax > ref_line:
        parts.append(f'<line x1="{pad}" y1="{ys(ref_line):.1f}" x2="{w-16}" y2="{ys(ref_line):.1f}" stroke="#d87d7d" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{w-18}" y="{ys(ref_line)-3:.1f}" text-anchor="end" font-size="9" fill="#d87d7d">{ref_label}</text>')
    for seg in segs:
        parts.append(f'<polyline points="{seg}" fill="none" stroke="{color}" stroke-width="2"/>')
    parts.append(f'<text x="{pad}" y="12" font-size="10" fill="#aaa">max {fmt.format(max(pts))} · 末 {fmt.format(pts[-1])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_bars(values, w=560, h=160, color="#7bc8a4", ref_line=None,
             ref_label=None, fmt="{:.2f}"):
    """柱状图（日费用/日调用）；ref_line＝月预算日均参考。"""
    pts = [v for v in values if v is not None]
    if not pts:
        return svg_line([], w, h)
    vmax = max(max(pts), ref_line or 0) * 1.08 or 1
    pad, bw = 34, w - 50
    n = len(values)
    bw_bar = bw / n * 0.66
    ys = lambda v: h - 24 - (h - 44) * (v / vmax)
    parts = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" class="chart">']
    if ref_line and vmax > ref_line:
        parts.append(f'<line x1="{pad}" y1="{ys(ref_line):.1f}" x2="{w-16}" y2="{ys(ref_line):.1f}" stroke="#d87d7d" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{w-18}" y="{ys(ref_line)-3:.1f}" text-anchor="end" font-size="9" fill="#d87d7d">{ref_label}</text>')
    for i, v in enumerate(values):
        if v is None:
            continue
        x = pad + bw * i / max(n - 1, 1) - bw_bar / 2
        parts.append(f'<rect x="{x:.1f}" y="{ys(v):.1f}" width="{bw_bar:.1f}" '
                     f'height="{h-24-ys(v):.1f}" fill="{color}" rx="1"/>')
    parts.append(f'<text x="{pad}" y="12" font-size="10" fill="#aaa">max {fmt.format(max(pts))} · 末 {fmt.format(pts[-1])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_stack(series, labels, w=560, h=160):
    """堆叠柱（error_class 分布 / llm-local 占比）。series＝[{值按日}]，labels 同序。"""
    totals = [sum(v for v in col if v is not None) for col in zip(*series)]
    if not any(totals):
        return svg_line([], w, h)
    vmax = max(totals) * 1.08 or 1
    pad, bw = 34, w - 50
    n = len(totals)
    bw_bar = bw / n * 0.66
    parts = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" class="chart">']
    x = pad
    for i, total in enumerate(totals):
        x = pad + bw * i / max(n - 1, 1) - bw_bar / 2
        y = h - 24
        for si, s in enumerate(series):
            v = s[i]
            if not v:
                continue
            hh = (h - 44) * v / vmax
            y -= hh
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw_bar:.1f}" '
                         f'height="{hh:.1f}" fill="{PALETTE[si % len(PALETTE)]}" rx="1"/>')
    parts.append('<g font-size="10">')
    lx = pad
    for si, lab in enumerate(labels):
        parts.append(f'<rect x="{lx}" y="4" width="9" height="9" fill="{PALETTE[si % len(PALETTE)]}"/>')
        parts.append(f'<text x="{lx+12}" y="12" fill="#aaa">{lab}</text>')
        lx += 14 + 10 * len(lab)
    parts.append("</g></svg>")
    return "".join(parts)
