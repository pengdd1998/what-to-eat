"""薄味觉记忆层（FR-09/10，SC-3 参数化；T1.8）。

写入：accept=+1 / swap=-0.5 / negative=-1 / visit_bad=-1（弃答=0 不写入）。
读取：最近 20 条滚动窗口 [假设] ＋ 指数衰减（半衰期 2 周 [假设]）——读取侧计算，
不物化。dish_ref＝dish_slug（跨形态稳定键，v3.1 评审 2）。
"""
from datetime import datetime, timezone
from typing import Dict, List

DEFAULTS = {
    "window": 20,          # 滚动窗口条数
    "half_life_days": 14,  # 半衰期
    "weights": {"accept": 1.0, "swap": -0.5, "negative": -1.0, "visit_bad": -1.0},
}


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def write_memory(conn, anon_id: str, dish_slug: str, signal: str,
                 config: dict = None) -> None:
    params = {**DEFAULTS, **(config or {})}
    conn.execute(
        "INSERT INTO memory_events(anon_id, dish_ref, signal, weight, created_at) "
        "VALUES(?,?,?,?,?)",
        (anon_id, dish_slug, signal, params["weights"][signal], _now()))


def read_memory(conn, anon_id: str, config: dict = None) -> List[Dict]:
    """返回窗口内逐条衰减后得分＋聚合视图：negative_score / dish_score。"""
    params = {**DEFAULTS, **(config or {})}
    rows = conn.execute(
        "SELECT dish_ref, signal, weight, created_at FROM memory_events "
        "WHERE anon_id=? ORDER BY id DESC LIMIT ?",
        (anon_id, params["window"])).fetchall()
    now = datetime.now(timezone.utc)
    items = []
    for r in rows:
        age_days = max((now - _parse_ts(r["created_at"])).total_seconds() / 86400.0, 0)
        decayed = r["weight"] * (0.5 ** (age_days / params["half_life_days"]))
        items.append({"dish": r["dish_ref"], "signal": r["signal"],
                      "weight": r["weight"], "decayed": round(decayed, 4)})
    dish_score: Dict[str, float] = {}
    for it in items:
        dish_score[it["dish"]] = dish_score.get(it["dish"], 0.0) + it["decayed"]
    # 近期负反馈菜（排除用）：窗口内 signal∈{negative,visit_bad} 且衰减后仍 < -0.25
    negative_dishes = {it["dish"] for it in items
                       if it["signal"] in ("negative", "visit_bad") and it["decayed"] < -0.25}
    return {
        "items": items,
        "dish_score": {k: round(v, 4) for k, v in dish_score.items()},
        "negative_dishes": sorted(negative_dishes),
        "signal_count": len(items),  # FR-05 冷/稳态判定的"有效偏好信号次数"代理
    }


def effective_signal_count(conn, anon_id: str, config: dict = None) -> int:
    return read_memory(conn, anon_id, config)["signal_count"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
