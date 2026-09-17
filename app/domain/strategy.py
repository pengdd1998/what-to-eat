"""推荐策略模块——形态开关所在（§1.1，唯一按终裁分叉的模块；T1.4）。

config.form: "A"（PyThin 池为主）| "C"（RuleFloor 规则打分）| "undecided"
（终裁前占位＝降级链末端行为；D6 终裁后 Admin config 翻转，切换语义＝两层：
形态切换是代码级开关＋一次发版，非热切换——v3.1 评审 1）。

降级链（两形态共同，§1.1）：LLM 不可用/池未命中/规则空集 → 本地菜库兜底，
计为功能降级可用（source=library），单列观测，不算不可用。
"""
import hashlib
import json
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

from ..llm import service as llm_mod

TAG_REASONS = {
    "要快": "出餐快不磨叽",
    "不吃辣": "不辣不刺激",
    "想喝汤": "热汤落胃",
    "清淡": "清淡有滋味",
    "想吃热乎": "热乎现做",
    "预算30以下": "三十以内管饱",
    "重口味": "味道带劲",
    "想慢享": "适合慢慢吃",
    "想吃冷的": "清爽冰凉",
}

# FR-20/D-13：健康建议输出拦截黑名单（U8 草案 §五同源；prompt 层已兜一半）
HEALTH_BLACKLIST = ("减脂", "减肥", "瘦身", "热量", "热量低", "卡路里", "控糖",
                    "低GI", "低 GI", "低卡", "健康餐", "刮油", "代餐",
                    "增肌", "轻断食", "排毒", "养生", "调理", "营养师", "医生建议",
                    "体重")
# 阶段4：strategy(14词)与quiz(12词)互有遗漏→并集单源（R-22 只统一词表，双层拦截结构不变）


def filter_health_advice(copy: str, fallback: str) -> str:
    """命中黑名单→换中性模板（双层拦截的输出层；漏网≥1 例触发 D-13 还债）。"""
    return fallback if any(w in copy for w in HEALTH_BLACKLIST) else copy


def time_slot_for(dt: datetime) -> str:
    """时段判定（U6 未定稿的占位映射：午 11–14 / 晚 17–21 / 夜 21–24，缺省晚）。"""
    h = dt.hour
    if 11 <= h < 14:
        return "午"
    if 21 <= h < 24:
        return "夜"
    return "晚"


@dataclass
class RecommendContext:
    session_id: str
    anon_id: str
    attempt: int = 0                       # 同会话第几次取结果（换一位）
    tonight_tags: List[str] = field(default_factory=list)
    time_slot: str = "晚"
    flavor_summary: str = ""               # 匿名口味摘要（LLM 脱敏上下文用）
    negative_dishes: List[str] = field(default_factory=list)  # 记忆负反馈剔除
    dish_scores: dict = field(default_factory=dict)           # dish_slug → 衰减分


@dataclass
class Recommendation:
    dish_slug: str
    dish_name: str
    copy: str
    source: str                            # pool | realtime | library（§1.2）
    meta: dict


def _rng(session_id: str, attempt: int) -> random.Random:
    return random.Random(hashlib.sha256(
        f"{session_id}:{attempt}".encode()).hexdigest())


def _neutral_copy(dish_name: str, tags: List[str]) -> str:
    reasons = "，".join(TAG_REASONS[t] for t in tags[:2] if t in TAG_REASONS)
    return f"{dish_name}——{reasons or '今晚就它'}，就它了。"


def _library_rows(conn) -> list:
    rows = conn.execute(
        "SELECT dish_slug, dish_name, tags, base_score FROM dish_library "
        "WHERE active=1").fetchall()
    if not rows:
        raise RuntimeError("dish_library empty: seed migrations missing")
    return rows


class RecommendationStrategy:
    def recommend(self, ctx: RecommendContext) -> Recommendation:
        raise NotImplementedError


class LibraryDirectStrategy(RecommendationStrategy):
    """降级链末端：dish_library 直给（两形态共有兜底，FR-06 直给语义）。"""

    def __init__(self, conn):
        self.conn = conn

    def recommend(self, ctx: RecommendContext) -> Recommendation:
        rows = [r for r in _library_rows(self.conn)
                if r["dish_slug"] not in ctx.negative_dishes]
        if not rows:  # 记忆剔除后空集 → 忽略剔除（兜底必须给得出 1 家）
            rows = _library_rows(self.conn)
        weights = [max(r["base_score"], 0.0) for r in rows]
        if sum(weights) <= 0:
            weights = None
        row = _rng(ctx.session_id, ctx.attempt).choices(
            rows, weights=weights, k=1)[0]
        tags = json.loads(row["tags"])
        copy = filter_health_advice(_neutral_copy(row["dish_name"], tags),
                                    _neutral_copy(row["dish_name"], []))
        return Recommendation(dish_slug=row["dish_slug"],
                              dish_name=row["dish_name"], copy=copy,
                              source="library",
                              meta={"tags": tags, "attempt": ctx.attempt})


class RuleFloorStrategy(RecommendationStrategy):
    """C 形态：规则打分 over dish_library＋空集放宽级联（C卡 C-R2，D-16 保真上限）。"""

    def __init__(self, conn):
        self.conn = conn

    def recommend(self, ctx: RecommendContext) -> Recommendation:
        # 需求向→属性向归一（图谱§5.2/§11.8）：tonight_tags 可能混有需求向词
        # （想喝汤/想吃热乎等），strict 子集匹配前先归一，防与属性向菜库 tags 错配。
        from .dimensions import to_attr_tags
        t_attr = to_attr_tags(set(ctx.tonight_tags) - {"不重样"})
        rows = [dict(dish_slug=r["dish_slug"], dish_name=r["dish_name"],
                     tags=set(json.loads(r["tags"])), base_score=r["base_score"])
                for r in _library_rows(self.conn)]
        pool = [r for r in rows if r["dish_slug"] not in ctx.negative_dishes]
        relaxed = None
        if not pool:                       # 级联 2：仅时段＋记忆仍空 → 忽略记忆
            pool, relaxed = rows, "memory_ignored"
        strict = [r for r in pool if t_attr.issubset(r["tags"])]
        if not strict and relaxed is None:  # 级联 1：全失配 → 放宽（仅记忆过滤）
            strict, relaxed = pool, "tags_dropped"

        def score(r) -> float:
            overlap = len(t_attr & r["tags"])
            penalty = min(abs(ctx.dish_scores.get(r["dish_slug"], 0.0)), 0.5)
            return r["base_score"] + 0.2 * overlap - penalty

        ranked = sorted(strict, key=lambda r: (-score(r), r["dish_slug"]))
        row = ranked[ctx.attempt % len(ranked)]  # 换一＝分数带内轮换（确定性）
        return Recommendation(
            dish_slug=row["dish_slug"], dish_name=row["dish_name"],
            copy=self._template_copy(t_attr, row), source="library",
            meta={"tags": sorted(row["tags"]), "attempt": ctx.attempt,
                  "rule_relaxed": relaxed})

    def _template_copy(self, t_attr: set, row: dict) -> str:
        key = "+".join(sorted(t_attr)) if t_attr else "default"
        tpl = self.conn.execute(
            "SELECT text FROM template_copy WHERE scene=? ORDER BY id DESC LIMIT 1",
            (key,)).fetchone()
        neutral = _neutral_copy(row["dish_name"], sorted(t_attr))
        if tpl:
            return filter_health_advice(
                tpl["text"].replace("{dish}", row["dish_name"]), neutral)
        return neutral


class PyThinStrategy(RecommendationStrategy):
    """A 形态：dish_pool 命中（slot×组合⊇今晚标签）→ 未命中实时生成 → 菜库兜底。"""

    def __init__(self, conn):
        self.conn = conn

    def recommend(self, ctx: RecommendContext) -> Recommendation:
        # 需求向→属性向归一（图谱§5.2/§11.8）：tonight_tags 可能混有需求向词
        # （想喝汤/想吃热乎等），strict 子集匹配前先归一，防与属性向菜库 tags 错配。
        from .dimensions import to_attr_tags
        t_attr = to_attr_tags(set(ctx.tonight_tags) - {"不重样"})
        rows = [dict(r) for r in self.conn.execute(
            "SELECT dish_slug, dish_name, tag_combo, copy FROM dish_pool "
            "WHERE active=1 AND time_slot=?", (ctx.time_slot,)).fetchall()]
        serving = [r for r in rows
                   if t_attr.issubset(set(json.loads(r["tag_combo"])))
                   and r["dish_slug"] not in ctx.negative_dishes]
        if serving:
            row = serving[_rng(ctx.session_id, ctx.attempt).randrange(len(serving))]
            copy = filter_health_advice(
                row["copy"], _neutral_copy(row["dish_name"], sorted(t_attr)))
            return Recommendation(dish_slug=row["dish_slug"],
                                  dish_name=row["dish_name"], copy=copy,
                                  source="pool",
                                  meta={"time_slot": ctx.time_slot,
                                        "tag_combo": json.loads(row["tag_combo"]),
                                        "attempt": ctx.attempt})
        # 池未命中 → 实时生成（U2 未定稿时 provider=stub → None → 菜库兜底）
        gen = llm_mod.generate_recommendation(self.conn, {
            "tonight_tags": sorted(t_attr),
            "flavor_summary": ctx.flavor_summary,
            "daily_alias": "u-" + hashlib.sha256(
                ctx.anon_id.encode()).hexdigest()[:8],  # 假名占位（日轮换 T1.8 补）
        })
        if gen and gen.get("dish_name"):
            copy = filter_health_advice(str(gen.get("copy", "")),
                                        _neutral_copy(gen["dish_name"], sorted(t_attr)))
            return Recommendation(
                dish_slug=str(gen.get("dish_slug") or gen["dish_name"]),
                dish_name=gen["dish_name"], copy=copy, source="realtime",
                meta={"attempt": ctx.attempt, "time_slot": ctx.time_slot})
        return LibraryDirectStrategy(self.conn).recommend(ctx)


def get_strategy(conn, form: str) -> RecommendationStrategy:
    if form == "A":
        return PyThinStrategy(conn)
    if form == "C":
        return RuleFloorStrategy(conn)
    return LibraryDirectStrategy(conn)  # undecided（终裁前）＝降级链末端
