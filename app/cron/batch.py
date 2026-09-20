"""cron/batch（阶段3拆分自 app/cron.py）。"""
import json
import os
from datetime import datetime, timezone

from ..core import db
from .common import _today, _write_metric, notify


def batch() -> dict:
    """周更批产管道（T1.5；U2 已定稿 qwen，ADR-004 修订）。

    流程：属性组合（过滤语义冲突对，K=60/时段容量口径见 poc1-m0-prior-rerun）
    × 菜库匹配菜 → qwen 逐条生成文案（生产网关，disable_thinking 方言自动分派）
    → dish_pool **staged（active=0）**，人工抽检后 Admin 激活。
    单条失败/健康词命中 → 模板文案兜底（合成路径保留，池量不缺）。
    env：WTE_BATCH_LLM=0 强制合成；WTE_BATCH_LIMIT=n 限组合数（冒烟用）。
    """
    from ..llm.service import _load_dotenv
    from ..llm.gateway import call as gw_call
    from ..llm.service import log_call
    from ..domain.strategy import HEALTH_BLACKLIST, _neutral_copy
    import itertools
    import os
    import time as _time

    _load_dotenv()                               # 批产凭据（key 仅内存，SUP-02）
    conn = db.connect()
    cfg = db.get_config("llm", {})
    model = cfg.get("model", "qwen3.8-flash")
    use_llm = os.environ.get("WTE_BATCH_LLM", "1") != "0"
    limit = int(os.environ.get("WTE_BATCH_LIMIT", "0")) or None

    with db.tx() as t:
        cur = t.execute(
            "INSERT INTO batch_runs(form, started_at, status) "
            "VALUES('A', ?, 'running')",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
        batch_id = cur.lastrowid

    rows = conn.execute(
        "SELECT dish_slug, dish_name, tags FROM dish_library WHERE active=1"
    ).fetchall()
    attr = [t for t in ("不吃辣", "想喝汤", "预算30以下", "清淡", "重口味",
                        "想吃热乎", "想吃冷的", "要快", "想慢享")]
    conflicts = {frozenset(p) for p in (
        ("不吃辣", "重口味"), ("想吃热乎", "想吃冷的"),
        ("清淡", "重口味"), ("想喝汤", "想吃冷的"))}
    combos = [sorted(c) for n in (1, 2)
              for c in itertools.combinations(attr, n)
              if frozenset(c) not in conflicts]
    if limit:
        combos = combos[:limit]
    slots = ["午", "晚", "夜"]
    lib = [(r["dish_slug"], r["dish_name"], set(json.loads(r["tags"])))
           for r in rows]

    def pick(combo, k=2):
        want = set(combo)
        scored = sorted(((len(tags & want), slug, name)
                         for slug, name, tags in lib), key=lambda x: -x[0])
        top = [(slug, name) for s, slug, name in scored if s > 0][:k]
        return top or [(slug, name) for _, slug, name in scored[:1]]

    def qwen_copy(dish, combo, slot):
        prompt = (f"晚餐推荐文案。时段：{slot}。菜名：{dish}。"
                  f"今晚标签：{'、'.join(combo)}。"
                  "写一句 15–35 字、口语化、带情绪的推荐语；"
                  "禁止健康/减脂/营养表述。只输出推荐语本身。")
        res = gw_call("app.cron.batch", "batch_copy", prompt, model=model,
                      route="primary",
                      params={"temperature": 0.8, "disable_thinking": True})
        # 落 llm_calls（2026-09-16 N1 修复：批产成本进看板/日结口径——
        # 原直连网关不落库，月费用系统性低估，而批产恰是成本大头）
        log_call(db.connect(), "qwen", "batch", res["latency_ms"],
                 per_call if res["ok"] else 0.0,
                 "ok" if res["ok"] else "error",
                 task="batch_copy", error_class=res.get("error_class"),
                 attempts=res.get("attempts"), model=model)
        if not res["ok"]:
            return None
        txt = (res["content"] or "").strip().strip('"').strip()
        if not txt or any(w in txt for w in HEALTH_BLACKLIST) or len(txt) > 60:
            return None
        return txt

    items_in = items_out = llm_ok = 0
    cost = 0.0
    per_call = float(cfg.get("cost_per_call_usd", 0.01))
    for slot in slots:
        for combo in combos:
            for slug, name in pick(combo):
                items_in += 1
                copy = qwen_copy(name, combo, slot) if use_llm else None
                if copy:
                    llm_ok += 1
                    cost += per_call
                else:
                    copy = _neutral_copy(name, sorted(combo))
                with db.tx() as t:
                    t.execute(
                        "INSERT OR IGNORE INTO dish_pool(dish_slug, dish_name, "
                        "city, time_slot, tag_combo, copy, batch_id, active) "
                        "VALUES(?,?,?,?,?,?,?,0)",
                        (slug, name, "sz", slot,
                         json.dumps(combo, ensure_ascii=False),
                         copy, batch_id))
                    cur = t.execute(
                        "SELECT changes() AS c").fetchone()["c"]
                    items_out += cur
                _time.sleep(0.25)              # 限速：对供应商友好
    with db.tx() as t:
        t.execute("UPDATE batch_runs SET finished_at=?, items_in=?, items_out=?, "
                  "cost_usd=?, status='staged' WHERE id=?",
                  (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   items_in, items_out, round(cost, 4), batch_id))
    return {"batch_id": batch_id, "items_in": items_in, "items_out": items_out,
            "llm_ok": llm_ok, "cost_usd": round(cost, 4), "status": "staged",
            "model": model, "note": "抽检后经 Admin 激活（SC-7）"}
