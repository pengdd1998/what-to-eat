#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PoC-4 供应商延迟/错误率探针（T1.5/未决 #6；ADR-003 B 判断 1 数据同源复用）。

走生产适配器路径（app.llm.generate_recommendation：含熔断检查与 llm_calls
留痕），N 次真实调用，报告 P50/P95/P99、错误率、token 用量与成本估算。
注意：ADR-003 B 判断 1 的正式口径为 19:00–21:00 核心时段——非核心时段跑的
结果标注 [非核心时段]，W2 D1 前需在核心时段复测一轮。
用法：python scripts/poc4_probe.py [--n 20] [--model mimo-v2.5-pro]
"""
import argparse
import json
import os
import statistics
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("WTE_DB_PATH", tempfile.mktemp(suffix=".db"))

from app.core import db  # noqa: E402
from app.llm import service as llm  # noqa: E402

PROMPTS = [
    {"tonight_tags": ["要快", "预算30以下"], "flavor_summary": "近期接受:兰州牛肉拉面"},
    {"tonight_tags": ["想喝汤", "想吃热乎"], "flavor_summary": "无历史信号"},
    {"tonight_tags": ["不吃辣", "清淡"], "flavor_summary": "近期负反馈:水煮牛肉"},
    {"tonight_tags": ["重口味"], "flavor_summary": "近期接受:螺蛳粉,酸辣粉"},
    {"tonight_tags": [], "flavor_summary": "无历史信号"},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--model", default=None, help="覆盖 config 中的 model")
    args = ap.parse_args()

    db.init_schema()
    cfg = {"provider": "openai_compatible", "model": args.model or "mimo-v2.5",
           "temperature": 0.7, "disable_thinking": True, "cost_per_call_usd": 0.01,
           "daily_call_cap": 10_000, "daily_cost_cap_usd": 100}
    db.set_config("llm", cfg)

    latencies, errors, samples = [], [], []
    for i in range(args.n):
        ctx = PROMPTS[i % len(PROMPTS)]
        import time
        t0 = time.monotonic()
        out = llm.generate_recommendation(db.connect(), ctx)
        dt = (time.monotonic() - t0) * 1000
        if out is None:
            errors.append(dt)
        else:
            latencies.append(dt)
            if len(samples) < 3:
                samples.append(out)
        print(f"  #{i+1:>2}  {dt:7.0f}ms  {'ok' if out else 'FAIL/降级'}", flush=True)

    def pct(v, p):
        if not v:
            return None
        v = sorted(v)
        return v[min(len(v) - 1, int(len(v) * p / 100))]

    n = args.n
    ok = len(latencies)
    report = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": cfg["model"], "n": n, "ok": ok,
        "error_rate": round(len(errors) / n, 4),
        "latency_ms_p50": pct(latencies, 50), "latency_ms_p95": pct(latencies, 95),
        "latency_ms_p99": pct(latencies, 99),
        "pass_p95_le_3000": (pct(latencies, 95) or 0) <= 3000 if ok else False,
        "pass_error_rate_lt_1pct": len(errors) / n < 0.01,
        "samples": samples,
        "note": "非核心时段（正式判读须 19:00–21:00 复测）",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    rows = db.connect().execute(
        "SELECT COUNT(*) c, SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) ok, "
        "SUM(tokens_in+tokens_out) tokens FROM llm_calls").fetchone()
    print(f"llm_calls 留痕: {rows['c']} 条 / ok={rows['ok']} / tokens={rows['tokens'] or 0}")


if __name__ == "__main__":
    main()
