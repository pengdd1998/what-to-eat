"""多步选择题收口引擎（业务域 §2/§3）。

职责边界：驱动「5~8 步轻松选择题 → 一个用餐建议」的收敛流程。
- LLM 生成下一步问题/选项与最终菜名；未配置/失败一律降级到本地题库与本地菜池——
  「功能降级可用」，不算故障（失败不抛异常红线）。
- **三段式红线**：LLM 调用（HTTP≤6s）绝不在持有 db.tx() 写锁内发起。
  顺序＝读上下文（只读）→ 锁外调 LLM → 短事务落库。
- **确定性红线**：结果在会话首算后固化到会话行；刷新/重取不重摇（recommend_seed
  导出本地兜底选择）。
- **健康边界双层拦截**：①prompt 明令禁健康/减脂表述；②解析后再扫关键词过滤。
- **隐私**：LLM 上下文只传口味标签＋匿名口味摘要＋当日轮换假名，绝禁 anon_id 原文。
- **JSON 杂讯**：模型输出可能带 ```json 围栏/前后杂讯——解析前截取首个 `{` 到末个 `}`。
"""
import hashlib
import json
import secrets
from datetime import datetime, timezone

from ..core import db
from ..providers import env_ctx
from ..llm import service as llm

# 量化阈值落 config 的缺省（运行时可覆盖，不硬编码在流程里）
MIN_STEPS = 4          # 缺省最少步数（2026-09-15 owner 拍板 5→4 观察期；config quiz.min_steps 可调）
MAX_STEPS = 8          # 最多几步（超此强制收口）

from .strategy import HEALTH_BLACKLIST as HEALTH_BANNED  # 并集单源（阶段4；双层拦截结构不变）
from . import dimensions

import os as _os
_RTP = {}
try:
    with open(_os.path.join(_os.path.dirname(__file__), "reason_templates.json"),
              encoding="utf-8") as _f:
        _RTP = json.load(_f)
except Exception:
    _RTP = {}                                  # 模板缺失→回退旧文案（降级链）


def _build_reason(name: str, state, scene: str = "") -> str:
    """图谱§8 推荐语：链模板＋正交锁至多 1 句＋场景至多 1 句，≤40 字。"""
    try:
        tpl = _RTP.get("chain_templates", {})
        suffixes = _RTP.get("ortho_suffixes", {})
        scenes = _RTP.get("scene_suffixes", {})
        base = None
        for nid in reversed((state or {}).get("chain", [])):
            if nid in tpl:
                base = tpl[nid].replace("{菜名}", name)
                break
        if not base:
            return f"{name}，就它了，别纠结。"
        parts = [base]
        for dim_id, mapping in suffixes.items():
            val = (state or {}).get("ortho", {}).get(dim_id)
            if not val:
                continue
            line = mapping.get(val) or mapping.get("_any", "").replace("{protein}", val)
            if line:
                parts.append(line)
            break                               # 正交锁至多 1 句
        sfx = scenes.get(scene) or next(
            (v for k, v in scenes.items() if k in scene), None)
        if sfx:
            parts.append(sfx)
        out = "".join(parts)
        return out if len(out) <= 40 else base
    except Exception:
        return f"{name}，就它了，别纠结。"

# ---------- 本地题库（降级态脊柱：保证零 LLM 也能 5~8 步收口） ----------
# 每步：问题 + 选项；option 关联口味标签，供最终本地菜池匹配。
LOCAL_BANK = [
    # 每题挂维度（dim＝测的节点；选项 dim＝该选项锁定的子节点）——本地兜底
    # 与 LLM 题共用约束状态机（2026-09-16 图谱对齐：按可用集选题，不再按步轮换）
    {"dim": "form", "question": "这顿先定个大方向？",
     "options": [
         {"id": "cat-staple", "text": "一碗主食（面/粉/饭）", "tags": ["面食", "米饭"], "dim": "staple"},
         {"id": "cat-meat", "text": "硬菜肉类（炒/烧/烤/卤）", "tags": ["肉", "炖卤"], "dim": "meat"},
         {"id": "cat-soup", "text": "热乎一锅（汤煲/粥/烫煮）", "tags": ["汤", "暖"], "dim": "pot"},
         {"id": "cat-light", "text": "轻食小份（凉菜/小食/点心）", "tags": ["凉拌", "清爽"], "dim": "light"}]},
    {"dim": "staple", "question": "主食想哪种？",
     "options": [
         {"id": "st-noodle", "text": "汤面/汤粉", "tags": ["面食", "汤"], "dim": "noodle-soup"},
         {"id": "st-rice", "text": "米饭盖饭", "tags": ["米饭"], "dim": "rice-bowl"},
         {"id": "st-filled", "text": "饺子包子带馅", "tags": ["带馅"], "dim": "filled"},
         {"id": "st-dry", "text": "拌面/凉面/饼", "tags": ["面食", "凉拌"], "dim": "noodle-dry"}]},
    {"dim": "meat", "question": "硬菜想吃哪种做法？",
     "options": [
         {"id": "mt-stir", "text": "家常小炒（锅气）", "tags": ["炒", "肉"], "dim": "meat-stir"},
         {"id": "mt-braise", "text": "红烧/炖卤", "tags": ["炖卤", "肉"], "dim": "meat-braise"},
         {"id": "mt-grill", "text": "烤/煎炸", "tags": ["烤", "肉"], "dim": "meat-grill"},
         {"id": "mt-fish", "text": "鱼鲜水煮", "tags": ["鱼鲜", "汤"], "dim": "meat-fish"}]},
    {"dim": "pot", "question": "热乎一锅，想要哪种？",
     "options": [
         {"id": "pt-soup", "text": "炖汤煲汤", "tags": ["汤", "暖"], "dim": "pot-soup"},
         {"id": "pt-tang", "text": "麻辣烫/冒菜", "tags": ["烫煮", "麻辣"], "dim": "pot-tang"},
         {"id": "pt-congee", "text": "粥品暖胃", "tags": ["粥", "清淡"], "dim": "pot-congee"}]},
    {"dim": "light", "question": "轻食小份，想要哪类？",
     "options": [
         {"id": "lt-cold", "text": "凉拌系", "tags": ["凉拌", "清爽"], "dim": "light-cold"},
         {"id": "lt-salad", "text": "冷轻食", "tags": ["清爽"], "dim": "light-salad"},
         {"id": "lt-snack", "text": "小食解馋", "tags": ["小食", "解馋"], "dim": "light-snack"},
         {"id": "lt-dimsum", "text": "点心蒸笼", "tags": ["点心", "清淡"], "dim": "light-dimsum"}]},
    {"dim": "spice", "question": "辣度到哪？",
     "options": [
         {"id": "sp-none", "text": "一点都不辣", "tags": ["不辣"]},
         {"id": "sp-mild", "text": "微微提味", "tags": ["微辣"]},
         {"id": "sp-mid", "text": "辣得过瘾", "tags": ["中辣"]},
         {"id": "sp-fire", "text": "越辣越爽", "tags": ["爆辣"]}]},
    {"dim": "texture", "question": "口味浓淡偏向？",
     "options": [
         {"id": "tx-light", "text": "清淡爽口", "tags": ["清淡"]},
         {"id": "tx-rich", "text": "浓郁够味", "tags": ["浓郁"]}]},
]


# 本地菜池（降级态最终建议）：name ＋ 匹配标签。
LOCAL_DISHES = [
    {"name": "番茄鸡蛋盖饭", "tags": ["米饭", "不辣", "酸甜", "下饭"]},
    {"name": "麻婆豆腐饭", "tags": ["米饭", "中辣", "下饭"]},
    {"name": "黄焖鸡米饭", "tags": ["米饭", "微辣", "炖卤", "肉"]},
    {"name": "红烧肉盖饭", "tags": ["米饭", "浓郁", "肉", "甜口"]},
    {"name": "兰州牛肉面", "tags": ["面食", "汤", "不辣", "肉"]},
    {"name": "重庆小面", "tags": ["面食", "爆辣", "开胃"]},
    {"name": "酸辣粉", "tags": ["酸辣", "开胃", "汤"]},
    {"name": "牛肉拉面（汤）", "tags": ["面食", "汤", "暖", "肉"]},
    {"name": "猪肉大葱水饺", "tags": ["面食", "带馅", "不辣"]},
    {"name": "肉夹馍配凉皮", "tags": ["面食", "香", "凉拌"]},
    {"name": "手撕烤鸡饭", "tags": ["烤", "肉", "米饭"]},
    {"name": "香煎牛排时蔬", "tags": ["烤", "肉", "蔬菜"]},
    {"name": "凉拌鸡丝凉面", "tags": ["凉拌", "微辣", "面食", "清爽"]},
    {"name": "口水鸡", "tags": ["凉拌", "中辣", "肉", "开胃"]},
    {"name": "咖喱鸡肉饭", "tags": ["米饭", "浓郁", "微辣", "肉"]},
    {"name": "日式牛丼饭", "tags": ["米饭", "甜口", "肉", "不辣"]},
    {"name": "扬州炒饭", "tags": ["米饭", "均衡", "香"]},
    {"name": "蔬菜豆腐味噌汤定食", "tags": ["清淡", "汤", "蔬菜", "暖"]},
    {"name": "鲜虾云吞面", "tags": ["面食", "汤", "鲜", "不辣"]},
    {"name": "一碗麻辣烫", "tags": ["烫煮", "汤", "麻辣"]},
    {"name": "皮蛋瘦肉粥", "tags": ["粥", "暖", "清淡", "肉"]},
    {"name": "小笼包配粥", "tags": ["点心", "带馅", "清淡"]},
]


from ..core.util import now_iso as _now  # 阶段4：时钟单源


# ---------- 会话 ----------

def create_session(anon_id: str) -> dict:
    seed = secrets.token_hex(8)
    scene = detect_scene()
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO quiz_session(anon_id,recommend_seed,meal_scenario,"
            "created_at,updated_at) VALUES(?,?,?,?,?)",
            (anon_id, seed, scene, _now(), _now()))
        sid = cur.lastrowid
    return get_session(sid, anon_id)


def get_session(sid: int, anon_id: str):
    return db.connect().execute(
        "SELECT * FROM quiz_session WHERE id=? AND anon_id=?",
        (sid, anon_id)).fetchone()


# ---------- 味觉记忆（脱敏上下文素材） ----------

def taste_summary(anon_id: str) -> dict:
    """聚合历史为匿名口味画像：{liked, disliked, liked_by_scene, count, profiled}。

    加权融合（隐式画像升级 2026-09-15）：
    - 显式反馈：对味 +3 / 不推荐 -3（用户主动行为，权重高）；
    - 隐式信号：question_log 里用户每次选择的选项文本各 +1——**完成一轮选餐即有画像**，
      不再依赖用户去记忆页打分（此前只认 feedback 非空，画像长期为空）。
    count＝参与聚合的推荐记录数；profiled＝count ≥ config quiz.profile_threshold
    （画像充分，收口步数可放宽，见 next_question）。
    liked_by_scene：按时段场景拆分的对味标签，让推荐贴合「这时段常吃啥」。
    只含标签与选择文本，无任何身份信息（隐私红线：绝禁 anon_id 进 LLM 上下文）。
    """
    rows = db.connect().execute(
        "SELECT tags, feedback, meal_scenario, question_log FROM recommendation "
        "WHERE anon_id=?", (anon_id,)).fetchall()
    liked, disliked = {}, {}
    liked_by_scene = {}
    for r in rows:
        try:
            tags = json.loads(r["tags"] or "[]")
        except json.JSONDecodeError:
            tags = []
        fb = r["feedback"]
        scene = r["meal_scenario"] or "未知"

        def _add(pool, tag, w):
            pool[tag] = pool.get(tag, 0) + w
            if pool is liked:
                liked_by_scene.setdefault(scene, {})
                liked_by_scene[scene][tag] = liked_by_scene[scene].get(tag, 0) + w

        if fb == 1:
            for t in tags:
                _add(liked, t, 3)
        elif fb == -1:
            for t in tags:
                _add(disliked, t, 3)
        else:
            # 未反馈（或中性 0 不计权重）→ 隐式信号：答题路径里的每次选择
            try:
                qlog = json.loads(r["question_log"] or "[]")
            except json.JSONDecodeError:
                qlog = []
            for step in qlog:
                t = (step.get("option_text") or step.get("choice_text") or "").strip()
                if t and fb != 0:
                    _add(liked, t[:12], 1)
    top = lambda d: [k for k, _ in sorted(d.items(), key=lambda x: -x[1])[:6]]
    scene_summary = {s: top(d) for s, d in liked_by_scene.items()}
    try:
        threshold = int(db.get_config("quiz", {}).get("profile_threshold", 3))
    except Exception:
        threshold = 3
    return {"liked": top(liked), "disliked": top(disliked),
            "liked_by_scene": scene_summary,
            "count": len(rows), "profiled": len(rows) >= threshold}


def _recent_dishes(anon_id: str, limit: int = 5) -> list:
    """最近推荐过的菜名（去重有序）——注入 prompt 让结果避开，兑现「不重样」。"""
    rows = db.connect().execute(
        "SELECT name FROM recommendation WHERE anon_id=? ORDER BY id DESC LIMIT ?",
        (anon_id, limit)).fetchall()
    out = []
    for r in rows:
        if r["name"] and r["name"] not in out:
            out.append(r["name"])
    return out


def _env_block(client_ip: str) -> str:
    """环境块文本（预取注入）：场景＋天气＋周末。env_ctx 异常全吞＝该段「无」。"""
    try:
        env = env_ctx.snapshot(client_ip or "")
    except Exception:
        return ""
    parts = []
    sc = env.get("scene") or {}
    if sc.get("name"):
        parts.append(f"现在是用户的【{sc['name']}】时段")
    if (env.get("calendar") or {}).get("is_weekend"):
        parts.append("周末，用户时间充裕")
    else:
        parts.append("工作日")
    w = (env.get("weather") or {}).get("hint")
    if w:
        parts.append(f"天气：{w}")
    return "；".join(parts)


def _pseudonym() -> str:
    """当日轮换假名（与日期绑定，非身份信息）。日期用中国时区（假名随北京日界翻转）。"""
    day = env_ctx.cn_now().strftime("%m%d")
    return f"食客{day}"


def detect_scene(dt=None) -> str:
    """按中国时区（+8）判定用餐场景：早餐/午餐/下午茶/晚餐/宵夜。

    边界走 config.scenes（env_ctx.SCENES_DEFAULT 兜底），支持跨午夜。
    修复事故 2026-09-15：原实现用容器本地时钟（UTC），中午判宵夜。
    """
    return env_ctx.scene(dt)["name"]


# ---------- LLM JSON 解析（截取首 `{` 到末 `}`） ----------

def _extract_json(text: str):
    """从可能带 ```json 围栏/前后杂讯的输出里截取首个 { 到末个 } 并解析。"""
    if not text:
        return None
    a = text.find("{")
    b = text.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        return json.loads(text[a:b + 1])
    except json.JSONDecodeError:
        return None


def _health_clean(text: str) -> bool:
    """命中违禁词 → True 表示「不合格，需走降级」。"""
    if not text:
        return False
    return any(w in text for w in HEALTH_BANNED)


# 搭配类问题词表（2026-09-15 漏斗收敛）：命中＝问题偏离主菜收敛轴（饮料/配菜/
# 加料/收尾）。语义：LLM 问到搭配，多半是主菜维度已收敛完、开始在边上打转——
# 引擎把它当收口信号处理，不再让用户为搭配花步数。
SIDE_DISH_WORDS = (
    "饮料", "奶茶", "啤酒", "酒水", "喝的", "饮品", "配着喝", "搭配喝", "来一杯",
    "小菜", "配菜", "配料", "配什么", "解腻", "开胃菜", "搭配着吃", "配点什么",
    "提鲜", "灵魂配料",
    "加蛋", "卤蛋", "香菜", "葱花", "小料", "蘸料", "蘸什么", "加不加", "要不要加",
    "收尾", "最后再来点", "饭后", "甜点当",
    "灵魂伴侣", "加个什么", "丰富口感", "加点什么", "再加点",
)


def _is_side_dish_question(text: str) -> bool:
    """问题文本是否属搭配维度（饮料/配菜/加料/收尾）——命中即拦截。"""
    return any(w in (text or "") for w in SIDE_DISH_WORDS)


def _is_repeat(question: str, log: list) -> bool:
    """判断新问题是否与已问问题重复（我方兜底：LLM 偶尔重复问同一维度时拦截降级）。

    判定：与任一已问问题互为子串，或去掉常见疑问词后共享 ≥4 字连续片段/高字符重合。
    """
    if not question:
        return False
    Q = str(question).strip()
    noise = "呢吗啊嘛什么哪种想吃想点要不要来个选"
    core = "".join(c for c in Q if c not in noise)
    for x in log:
        prev = str(x.get("question", "")).strip()
        if not prev:
            continue
        if Q in prev or prev in Q:
            return True
        prev_core = "".join(c for c in prev if c not in noise)
        # 字符集合重合率（中文短问题近似）
        inter = len(set(core) & set(prev_core))
        union = max(1, len(set(core) | set(prev_core)))
        if core and prev_core and inter / union >= 0.6:
            return True
    return False


# ---------- 下一步问题 ----------

def _local_question(step_index: int, state=None, log=None, chain_only=False) -> dict:
    """本地兜底出题：只出「当前可用维度集」内的题（与 LLM 题共用约束状态机）。

    2026-09-16 修复：原按 step 轮换不看约束——「带汤」语境下出「做法」题＝
    本地兜底自身成为偏移源。全部不匹配时出正交题（spice/texture 恒可用）。
    选项带 dim/tags 落库，保证本地题同样推进约束链（与 LLM 题同权）。
    F4 修复（生产 P3 流程实证 2026-09-25）：①跳过已问过的题面（兜底按步
    索引轮换曾重问已答粒度）；②chain_only＝强制下钻期只出链题（与 LLM
    路径的强制下钻同权，防兜底把正交连击续下去）。
    """
    dims = {d["id"] for d in dimensions.available_dims(state)} if state else None
    chain_ids = ({d["id"] for d in dimensions.available_dims(state)
                  if d["kind"] == "chain"} if state else None)
    cands = [b for b in LOCAL_BANK
             if not dims or b["dim"] in dims
             or any(o.get("dim") in dims for o in b["options"])]
    if chain_only and chain_ids:
        forced = [b for b in cands
                  if b["dim"] in chain_ids
                  or any(o.get("dim") in chain_ids for o in b["options"])]
        cands = forced or cands
    asked_q = {x.get("question") for x in (log or [])}
    if asked_q:
        fresh = [b for b in cands if b["question"] not in asked_q]
        cands = fresh or cands
    if not cands:
        cands = [b for b in LOCAL_BANK if b["dim"] in ("spice", "texture")]
    bank = cands[step_index % len(cands)]
    return {"question": bank["question"],
            "options": [{"id": o["id"], "text": o["text"],
                         "tags": o.get("tags", []), **({"dim": o["dim"]} if o.get("dim") else {})}
                        for o in bank["options"]],
            "step": step_index, "source": "local"}


def _stash_pending(sid, q) -> None:
    """next() 生成题暂存（0008 pending_q）——answer() 取 source 入 question_log 后清空。
    L4 口径修复（monitoring-workbench-plan P1-4b）：question_log 由 answer 落库但
    source 在 next 生成，靠本列传递；异常吞（口径修复不得影响出题主链）。"""
    try:
        with db.tx() as t:
            t.execute("UPDATE quiz_session SET pending_q=? WHERE id=?",
                      (json.dumps({"source": q.get("source", "llm")}), sid))
    except Exception:
        pass


def _reject_trace(reason: str, dim: str = "", step: int = -1) -> None:
    """next_question 拒因留痕（F5，回归轮上调 2026-09-25：本地兜底率 43%
    不可归因——强制拒/搭配健康拦截/解析失败此前全静默，与网络超时不可分）。
    audit 短事务一 INSERT，异常全吞＝打点不得影响出题主链。网络失败不在此
    打（llm_calls 已有 error 行天然可归因），此处只记「调用成功但题被丢」。"""
    try:
        from ..core.audit import audit
        with db.tx() as t:
            audit(t, "web", "quiz_q_reject", "next_question",
                  {"reason": str(reason)[:60], "dim": str(dim)[:24], "step": step})
    except Exception:
        pass


def next_question(session, client_ip: str = "") -> dict:
    """导航式出题（2026-09-15 维度树方案）：LLM 从引擎计算的可用维度集中选维度出题。

    引擎职责：约束累积（build_state）→可用维度集→验收（维度合法/选项 tags 兼容/
    搭配/健康）→收口终裁。LLM 职责：维度选择＋问题与选项生成（趣味与场景贴合）。
    任一验收不过→本地题库按步兜底（零额外 LLM 调用，降级链不变）。
    """
    anon_id = session["anon_id"]
    sid_key = session["id"]
    log = json.loads(session["question_log"] or "[]")
    step = session["step_index"]
    state = dimensions.build_state(log)
    try:
        _qcfg = db.get_config("quiz", {})
        min_required = (int(_qcfg.get("min_steps_profiled", 3))
                        if quiz_profiled(anon_id)
                        else int(_qcfg.get("min_steps", MIN_STEPS)))
    except Exception:
        min_required = MIN_STEPS
    min_required = max(2, min(min_required, MAX_STEPS - 1))
    if dimensions.should_finalize(state, step, min_required):
        return {"done": True}                    # 引擎终裁：信息足够，收口
    if step >= MAX_STEPS:
        return {"done": True}

    taste = taste_summary(anon_id)
    recent = _recent_dishes(anon_id)
    scene = session["meal_scenario"] or detect_scene()
    answered = "；".join(f'{x["question"]}→{x["option_text"]}' for x in log) or "（尚未作答）"
    scene_pref = taste.get("liked_by_scene", {}).get(scene) or "无"
    env_line = _env_block(client_ip)
    dedup = (f"【去重】最近已推荐过：{'、'.join(recent)}——结果与选项必须避开这些菜。\n"
             if recent else "")
    dims = dimensions.available_dims(state)
    # F4 修复（生产 P3 流程实证 2026-09-25：LLM 连问正交、链不下沉→步数被
    # 吃满触发兜底重问已答粒度，22 题中 7 题 32% 静默落本地的偏移主源）：
    # 尾部连续 ≥2 问正交且链深 <3 → 本题强制只给链维度（未锁 L1 先锁 L1，
    # 已锁则下钻子级）；LLM 仍选正交 → 验收拒，本地兜底同步只出链题。
    chain_only = (dimensions.tail_ortho_streak(log) >= 2
                  and len(state["chain"]) < 3)
    if chain_only:
        _cdims = [d for d in dims if d["kind"] == "chain"]
        if _cdims:
            dims = _cdims
        else:
            chain_only = False             # 链已到叶：无可下钻，不强制
    dims_json = json.dumps(
        [{"id": d["id"], "name": d["name"],
          **({"取值域": d["values"]} if d["kind"] == "ortho" else {"tags": d["tags"]})}
         for d in dims], ensure_ascii=False)
    locked = json.dumps({"分类路径": state["chain"],
                         "正交锁定": state["ortho"]}, ensure_ascii=False)
    prompt = (
        # ---- 段1 系统规则（全局字节级相同，勿插值） ----
        "你是帮人快速决定「吃什么」的轻量助手，通过几道轻松的选择题帮人收口到一个菜。\n"
        "**导航式出题规则（铁律）**：\n"
        "1. 从【可用维度集】中选**一个**维度出题（填入 dimension 字段，必须原样使用"
        "其中的 id）；\n"
        "2. 问题与 2~4 个互斥选项必须属于该维度：chain 类选项的 tags 必须与该维度"
        "tags 相交；ortho 类选项的 tags 必须取自其取值域；\n"
        "3. 所有选项必须满足【已锁路径】——与已收敛选择冲突的选项严禁出现；\n"
        "4. 措辞口语、有场景感、无警告脸；严禁为凑步数提问；\n"
        "5. 只输出 JSON：{\"dimension\":\"维度id\",\"question\":\"一句居中的问题\","
        "\"options\":[{\"id\":\"短id\",\"text\":\"选项文案\",\"tags\":[\"标签\"]}],"
        "\"should_stop\":true或false}\n"
        "**严禁任何减肥/减脂/低卡/养生/健康类表述**。\n"
        # ---- 段2 会话上下文（同会话内稳定） ----
        f"用户代号：{_pseudonym()}（非真实身份）。\n"
        f"【环境】{env_line or f'现在是用户的【{scene}】时段'}。\n"
        f"【口味记忆】喜欢={taste['liked'] or '无'}；不喜欢={taste['disliked'] or '无'}；"
        f"此时段常选={scene_pref}。\n"
        f"{dedup}"
        f"画像参考：{'充分，可更快收口' if taste.get('profiled') else '一般'}。\n"
        # ---- 段3 每问动态 ----
        f"【已锁路径】{locked}\n"
        f"【可用维度集】{dims_json}\n"
        + ("这是第一步：请从【可用维度集】中**任选一个你认为最合适的维度**出题"
           "（形态/辣度/浓淡/蛋白/温度/节奏皆可，凭你的判断选当下最值得问的）。\n"
           "若选 form（餐食形态）：给 3~4 个选项，各选项 tags 直接用所属大方向"
           "词（主食/硬菜/汤锅/轻食），严禁二分法锁死用户选择。\n"
           if not state["chain"] else "")
        + ("" if not chain_only else
           "分类路径还没收拢——本题必须从 chain 类维度里选一个"
           "（先定大方向或继续往下细分），不要问正交偏好。\n")
        + f"（已完成步数 {step}；用户选择流水：{answered}）\n"
    )
    res = llm.complete(db.connect(), prompt, scene="cold_start", agent="web", task="next_question")  # scene 受 CHECK；task＝监控粒度（0007）
    if res.get("ok"):
        data = _extract_json(res["content"])
        if not isinstance(data, dict):
            _reject_trace("parse_fail", "", step)    # F5：成功调用但题被丢
        else:
            qtext = str(data.get("question", ""))
            if (_health_clean(qtext) or _is_side_dish_question(qtext)):
                data = None                      # 搭配/健康：出题即废，走本地兜底
                _reject_trace("health_or_side_dish",
                              str(data.get("dimension", "")), step)
            else:
                ok_v, norm = dimensions.validate_question(data, state)
                if not ok_v:
                    import sys as _sys
                    print(f"[WTE-DEBUG] validate 拒: {norm}"
                          f" | dim={data.get('dimension')} q={str(data.get('question',''))[:24]}"
                          f" | opts={[(o.get('dim',''), o.get('tags')) for o in (data.get('options') or [])[:4]]}",
                          file=_sys.stderr)
                    _reject_trace(f"validate:{norm}",
                                  str(data.get("dimension", "")), step)
                if ok_v and chain_only and \
                        norm["dimension"] not in {d["id"] for d in dims}:
                    import sys as _sys
                    print(f"[WTE-DEBUG] 强制下钻期正交题拒: dim={norm['dimension']}",
                          file=_sys.stderr)
                    _reject_trace("force_chain_ortho", norm["dimension"], step)
                    ok_v = False
                if ok_v:
                    # 维度归拢启发：LLM 实际问了辣度却标了别的维度（重放 002 实证）
                    # ——归一为 spice 并把选项 tags 规范进取值域，防正交重复提问
                    if (norm["dimension"] != "spice" and "辣" in norm["question"]
                            and any(d["id"] == "spice" for d in dims)):
                        norm["dimension"] = "spice"
                        _SP = (("爆辣", ("爆辣", "爽翻天", "够劲")),
                               ("中辣", ("中辣",)),
                               ("微辣", ("微辣", "稍微", "提味", "提神", "开胃")),
                               ("不辣", ("不辣", "原味", "专心")))
                        for o in norm["options"]:
                            if not (set(o["tags"]) & {"不辣", "微辣", "中辣", "爆辣"}):
                                for v, kws in _SP:
                                    if any(k in o["text"] for k in kws):
                                        o["tags"] = [v]
                                        break
                    opts = [{**o, "dim": norm["dimension"]} for o in norm["options"]]
                    _q = {"question": norm["question"],
                          "options": opts, "step": step,
                          "should_stop": (bool(data.get("should_stop"))
                                          and step >= min_required),
                          "source": "llm"}
                    _stash_pending(sid_key, _q)      # L4 口径修复（0008 pending_q）
                    return _q
    # 降级：本地题库（按约束状态选题，2026-09-16 修复本地题自身偏移源；
    # F4：跳过已问题面＋强制下钻期只出链题）
    q = _local_question(step, state, log, chain_only=chain_only)
    q["should_stop"] = (step >= min_required - 1)
    q["done"] = False
    _stash_pending(sid_key, q)                       # 本地题同记 source=local
    return q


def quiz_profiled(anon_id: str) -> bool:
    return bool(taste_summary(anon_id).get("profiled"))


def answer_option(sid: int, anon_id: str, option_id: str, option_text: str,
                  question: str, from_local_bank: bool, all_options=None) -> dict:
    """记录一步选择；返回更新后的会话（含是否可收口）。

    all_options：本步全部选项 [{id,text}]，连同所选一并落进 question_log——
    味觉记忆据此回放完整答题路径，并高亮用户所选。
    """
    session = get_session(sid, anon_id)
    log = json.loads(session["question_log"] or "[]")
    # 本地题库选项：把 tags 一并记入，供最终本地匹配（F4：题库选题已是约束
    # 驱动非按步索引，兜底取 tags 也按 option_id 全库匹配——步索引取条目已错位）
    tags = []
    if from_local_bank:
        for bank in LOCAL_BANK:
            for o in bank["options"]:
                if o["id"] == option_id:
                    tags = o["tags"]
                    break
            if tags:
                break
    opts = []
    for o in (all_options or []):
        if isinstance(o, dict) and o.get("text"):
            item = {"id": str(o.get("id", ""))[:24], "text": str(o["text"])[:20]}
            if o.get("tags"):                       # 约束累积器依赖（2026-09-15 维度树）
                item["tags"] = [str(t)[:12] for t in o["tags"]][:6]
            if o.get("dim"):
                item["dim"] = str(o["dim"])[:40]
            opts.append(item)
            if o.get("id") == option_id:
                if o.get("tags") and not tags:
                    tags = [str(t)[:12] for t in o["tags"]][:6]   # 所选项 tags 进步级
                pick_dim = o.get("dim") or ""
    # L4 口径：source 取 next() 暂存的 pending_q（老会话 NULL 缺省 llm）
    try:
        _src = (json.loads(session["pending_q"]) or {}).get("source", "llm")
    except (TypeError, json.JSONDecodeError):
        _src = "llm"
    log.append({"step": session["step_index"], "question": question,
                "option_id": option_id, "option_text": option_text,
                "options": opts, "tags": tags, "source": _src,
                **({"dim": str(pick_dim)[:40]} if locals().get("pick_dim") else {})})
    with db.tx() as conn:
        conn.execute(
            "UPDATE quiz_session SET question_log=?, step_index=step_index+1,"
            " pending_q=NULL, updated_at=? WHERE id=? AND anon_id=?",
            (json.dumps(log, ensure_ascii=False), _now(), sid, anon_id))
    return get_session(sid, anon_id)


# ---------- 最终收口 ----------

def _local_recommend(session, state=None) -> dict:
    """确定性本地收口：用 recommend_seed 对匹配到的候选菜池哈希取一个。

    state 传入时先按已锁分类链过滤候选（dish_consistent），保证本地兜底
    也不背离收敛路径（重放 004 实证：纯 tags 打分会选出与链冲突的菜）。
    F8 修复（生产会话 115 实证 2026-09-25）：原实现过滤空集时无过滤放行
    （top 分候选全部越链→兜底端出越链菜）。现改链特征 tags 打分 ×3 加权
    防通用词压分＋一致性分层放宽（top 分一致→全池一致→链前缀逐级回退）。
    F8-b 修复（回归轮 P4 实证 2026-09-25：窄链三次换片全同菜）：「剔最近
    已推荐」并入每一层——层内去重空了即向下一层扩容，不再整层吃回；
    仅全部层去重皆空才回退未去重集（窄链池被近推荐抽干的终态）。
    swap_count 拌哈希保留（多层多候选时轮换）。
    """
    log = json.loads(session["question_log"] or "[]")
    chosen = set()
    for x in log:
        chosen.update(x.get("tags", []))
    # 链特征 tags（打分加权用）：已锁链路径各节点 tags 并集
    chain_tags = set()
    if state is not None:
        for nid in state["chain"]:
            node = dimensions.find_node(nid)
            if node:
                chain_tags.update(node.get("tags") or [])
    # 标签命中分：命中所选标签越多越靠前；同分时用 seed 哈希打破（确定性）
    # 候选源＝本地池（属性向）＋菜库（需求向→to_attr 归一，图谱§5.2 桥）——多样性×3.5
    pool = list(LOCAL_DISHES)
    try:
        lib = db.connect().execute(
            "SELECT dish_name, tags FROM dish_library WHERE active=1").fetchall()
        for r in lib:
            try:
                pool.append({"name": r["dish_name"],
                             "tags": sorted(dimensions.to_attr_tags(json.loads(r["tags"])))})
            except (json.JSONDecodeError, TypeError):
                continue
    except Exception:
        pass                                  # 菜库不可达→本地池兜底（降级链）
    scored = []
    for dish in pool:
        dtags = set(dish["tags"])
        hit = (len(chosen & dtags) + 2 * len(chain_tags & dtags)
               if (chosen or chain_tags) else 0)
        scored.append((hit, dish))
    best = max(s for s, _ in scored) if scored else 0
    # 候选层序（F8 分层放宽＋F8-b 层内去重）：①top 分且链一致 ②全池链一致
    # ③链前缀逐级回退（丢最深一级重试，保持「按链过滤」语义直到有菜——
    # 极窄链在池中无菜时退到最近一级有菜的祖先链）。未锁链＝单层 top 分。
    # 每层先剔最近已推荐，空了向下一层扩容；全层皆空才回退首层非去重集。
    recent = set(_recent_dishes(session["anon_id"]))
    top = [d for s, d in scored if s >= best] or pool
    tiers = [top]
    if state is not None and state["chain"]:
        tiers = [
            [d for d in top if dimensions.dish_consistent(d["name"], state)],
            [d for d in pool if dimensions.dish_consistent(d["name"], state)]]
        sub = list(state["chain"])
        while len(sub) > 1:
            sub = sub[:-1]
            tiers.append([d for d in pool if dimensions.dish_consistent(
                d["name"], {"chain": sub, "ortho": {}})])
    cands = []
    for t in tiers:
        fresh = [d for d in t if d["name"] not in recent]
        if fresh:
            cands = fresh
            break
    if not cands:
        cands = next((t for t in tiers if t), pool)
    h = hashlib.sha256((session["recommend_seed"] + "|" +
                        "|".join(sorted(chosen)) + "|" +
                        str(session["swap_count"] or 0)).encode()).hexdigest()
    pick = cands[int(h, 16) % len(cands)]
    reason = _build_reason(pick["name"], state,
                           session["meal_scenario"] or "")
    return {"name": pick["name"], "tags": pick["tags"], "reason": reason}


def finalize(sid: int, anon_id: str, client_ip: str = "") -> dict:
    """收口一个用餐建议。锁外调 LLM，短事务落库；结果固化（刷新不重摇）。"""
    session = get_session(sid, anon_id)
    if session["state"] == "done" and session["result"]:
        return {"cached": True, **json.loads(session["result"])}
    log = json.loads(session["question_log"] or "[]")
    taste = taste_summary(anon_id)
    recent = _recent_dishes(anon_id)
    scene = session["meal_scenario"] or detect_scene()
    _local_reason = "call_failed"                 # LLM 收口失败缺省拒因（监控 L4）
    answered = "；".join(f'{x["question"]}→{x["option_text"]}' for x in log)
    scene_pref = taste.get("liked_by_scene", {}).get(scene) or "无"
    env_line = _env_block(client_ip)
    dedup = (f"\n**去重铁律**：最近已推荐过：{'、'.join(recent)}——必须换一道没推荐过的菜。"
             if recent else "")
    # prompt 两段式（最长前缀缓存原则）：系统规则在前（与 next_question 的段1
    # 共享前缀语义；finalize 间彼此命中），会话内容在后。
    prompt = (
        # ---- 段1 系统规则（无插值） ----
        "你是帮人快速决定「吃什么」的轻量助手。请根据以下选择，给出**一个**具体菜名。\n"
        "请给贴合用户环境时段的菜（早餐宜粥面清淡、"
        "下午茶宜轻食点心、晚餐宜正餐硬菜、宵夜宜小份解馋）。\n"
        "**菜名铁律**：\n"
        "1. 只给一道菜、一个独立菜名（不要拼盘/不要「A配B加C」的组合写法）；\n"
        "2. 必须是大众熟知、外卖/餐馆里真实能点到的现成菜名（如「麻婆豆腐」「牛肉面」"
        "「黄焖鸡米饭」「小笼包」「酸辣粉」）；\n"
        "3. **严禁自行拼装、杜撰或文学化造句**——不要自创「红油金汤牛腩捞粉配脆笋」这类"
        "你自己组合出来的名字，也不要带形容词修饰的创意菜名；\n"
        "4. name 字段就是那一个菜名本身，别加「推荐你…」「可以试试…」。\n"
        "**推荐语风格锚（参考，不必逐字）**：汤面→「汤底是这碗的主角」；"
        "盖饭→「菜饭一体」；炖卤→「炖得酥烂入味」；汤煲→「先喝口热汤」；"
        "烧烤→「焦香解馋」；凉拌→「凉拌开胃」；粥→「稀软暖胃」。\n"
        "只输出 JSON，不要解释："
        '{"name":"现成菜名","tags":["标签",...],"reason":"一句话收口理由＋可顺带一句搭配'
        '建议（如「配碗汤更满足」），口语、合计不超过40字"}\n'
        "**严禁任何减肥/减脂/低卡/养生/健康类表述**。\n"
        # ---- 段2 会话上下文（每用户/每会话不同） ----
        f"用户代号：{_pseudonym()}（非真实身份）。\n"
        f"【环境】{env_line or f'现在是用户的【{scene}】时段'}。\n"
        f"【口味记忆】喜欢标签={taste['liked'] or '无'}；不喜欢标签={taste['disliked'] or '无'}；"
        f"此时段（{scene}）常选={scene_pref}。\n"
        f"用户的逐步选择：{answered}。\n"
        + dedup)
    result = None
    res = llm.complete(db.connect(), prompt, scene="cold_start", agent="web", task="next_question")  # scene 受 CHECK；task＝监控粒度（0007）
    if res.get("ok"):
        data = _extract_json(res["content"])
        if isinstance(data, dict) and data.get("name"):
            name = str(data["name"]).strip()[:30]
            reason = str(data.get("reason", "")).strip()[:60]
            if not dimensions.dish_consistent(name, dimensions.build_state(log)):
                import sys as _sys
                print(f"[WTE-DEBUG] finalize dish_consistent 拒绝: {name!r} "
                      f"path={dimensions.build_state(log)['chain']}", file=_sys.stderr)
                _local_reason = "dish_conflict"    # 拒因结构化（监控 L4，plan §3.3）
                result = None                      # 菜名与已锁路径冲突→本地池兜底
            elif not (_health_clean(name) or _health_clean(reason)):
                tags = data.get("tags") if isinstance(data.get("tags"), list) else []
                result = {"name": name, "meal_scenario": scene,
                          "tags": [str(t)[:12] for t in tags][:8],
                          "reason": reason or "就它了。", "source": "llm"}
    if result is None:
        result = _local_recommend(session,
                                  dimensions.build_state(log))
        result["meal_scenario"] = scene
        result["source"] = "local"
        # 拒因结构化（监控 L4：区分网络退化 call_failed vs 能力退化）
        result["local_reason"] = _local_reason
    # 短事务落库：会话置 done 并固化结果；写推荐记录（带场景标签＋完整答题路径）
    path = json.dumps(log, ensure_ascii=False)
    with db.tx() as conn:
        conn.execute(
            "UPDATE quiz_session SET state='done', result=?, updated_at=? "
            "WHERE id=? AND anon_id=?",
            (json.dumps(result, ensure_ascii=False), _now(), sid, anon_id))
        conn.execute(
            "INSERT INTO recommendation(anon_id,session_id,name,tags,reason,meal_scenario,"
            "question_log,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (anon_id, sid, result["name"],
             json.dumps(result["tags"], ensure_ascii=False), result["reason"],
             scene, path, _now()))
    return {"cached": False, **result}


def swap(sid: int, anon_id: str, max_swaps: int) -> dict:
    """灯箱换片（P0-1）：结果屏内重收口——不重答、一次点击、剩 n 计数。

    语义：清固化 result＋state 回 answering 允许 finalize 重收（出题 LLM 带
    「换一个方向」注入）；swap_count 递增；FR-15 留 swap 事件（含次序）；
    超上限 409＋swap_exhausted 留痕（不随 409 回滚——旧链纪律）。
    """
    with db.tx() as t:
        # F1 修复（评审 2026-09-23 TOCTOU 实锤）：检查与递增同事务——UPDATE 带
        # state='done' AND swap_count < max 双守卫按 rowcount 判定，并发双击
        # 只有一个线程抢到位（原实现在 tx 外读 used → 交错更新＝超限绕过硬验收）
        cur = t.execute(
            "UPDATE quiz_session SET result=NULL, state='answering', "
            "swap_count=swap_count+1, updated_at=? "
            "WHERE id=? AND anon_id=? AND state='done' "
            "AND swap_count < ?",
            (_now(), sid, anon_id, max_swaps))
        if cur.rowcount == 0:
            # 兼容态：state 已被并发首胜者改为 answering（非耗尽）→ 返回
            # not_finalized 语义外第三态 exhausted=False exhausted=False 双 False
            # 不可表达——返回 exhausted=True 会让前端误显示「用完」。
            # 改为返回第三态 pending：前端静默忽略。
            still = t.execute(
                "SELECT state, swap_count FROM quiz_session WHERE id=?",
                (sid,)).fetchone()
            if still and still["state"] == "answering" and \
                    (still["swap_count"] or 0) < max_swaps:
                return {"exhausted": False, "swaps_left": max_swaps,
                        "pending": True}
            return {"exhausted": True, "swaps_left": 0}
        used = (t.execute("SELECT swap_count FROM quiz_session WHERE id=?",
                          (sid,)).fetchone()[0]) - 1
        t.execute(
            "INSERT INTO events(client_event_id,session_id,anon_id,type,step,"
            "payload,client_ts,server_ts) VALUES(?,?,?,?,?,?,?,?)",
            ("ev_swap_" + secrets.token_hex(8), f"sess_quiz_{sid}", anon_id,
             "swap", used + 1,
             json.dumps({"nth": used + 1, "max": max_swaps}, ensure_ascii=False),
             None, _now()))
    # 清旧推荐记录的 accept 语义不回滚——recommendation 表按次留行，最新行为准
    return {"exhausted": False, "swaps_left": max_swaps - used - 1}


def feedback_recommendation(rec_id: int, anon_id: str, score: int) -> None:
    """三选反馈：对味+1 / 一般0 / 不推荐-1。落库即味觉记忆。"""
    if score not in (1, 0, -1):
        raise ValueError("score must be 1/0/-1")
    with db.tx() as conn:
        cur = conn.execute(
            "UPDATE recommendation SET feedback=?, feedback_at=? "
            "WHERE id=? AND anon_id=?", (score, _now(), rec_id, anon_id))
        if cur.rowcount == 0:
            raise LookupError("recommendation not found")


def list_memory(anon_id: str) -> list:
    rows = db.connect().execute(
        "SELECT id,name,tags,reason,feedback,meal_scenario,question_log,created_at "
        "FROM recommendation WHERE anon_id=? ORDER BY id DESC LIMIT 100",
        (anon_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["tags"] = json.loads(d["tags"] or "[]")
        except json.JSONDecodeError:
            d["tags"] = []
        try:
            d["question_log"] = json.loads(d.get("question_log") or "[]")
        except json.JSONDecodeError:
            d["question_log"] = []
        out.append(d)
    return out
