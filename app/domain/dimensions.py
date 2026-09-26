"""维度树——收敛导航的状态结构（2026-09-15 上下文漂移方案，owner 方向拍板）。

两类节点：
- 分类链（有父子）：父维度收敛后，后续只能在子树内继续——兄弟取值结构上不可再出
  （根治「第 1 步选带汤主食、第 2 步选项出现米饭」式漂移）；
- 正交维度（无父子，横向）：任何步骤可问（未问过即可），不改变分类路径。

角色分工：LLM 每步从「可用维度集」中**选一个维度**出题（导航智能＋趣味），引擎负责
计算可用集、验收（维度合法/选项 tags 兼容/搭配/健康）、收口终裁——约束从 prompt
软文本升级为结构化枚举。tags 全程与菜池（LOCAL_DISHES/dish_pool）词表对齐。
"""
import json


# ---------- 树定义（分类链：单根纵深；tags 对齐菜池词表） ----------
CHAIN = {
    # 图谱 v1.5 附录 G 唯一编译口径（2026-09-25 替换，owner 指令「优化完善维度树」）：
    # v1.5 消歧三原则——①L3 去继承词（子节点不重复父支词：rice-meat 不再带「米饭」、
    # filled 子级不带「带馅」）；②跨支身份词归唯一节点（「凉拌」只在 light-cold/dry-cold、
    # 「鱼鲜」只在 meat-fish、「烤」只在 meat-grill/snack-skewer）——兄弟互斥判定与
    # 本地收口链特征加权不再被跨支共享词稀释；③L2 瘦身（light 去凉拌、light-snack 去
    # 酥脆/开胃/烤、light-dimsum 去带馅/鲜、noodle-dry 去凉拌、meat-grill 去鱼鲜）。
    "id": "form", "name": "餐食形态", "tags": [],
    "children": [
        {"id": "staple", "name": "谷物主食系", "tags": ["面食", "米饭"],
         "children": [
             {"id": "noodle-soup", "name": "汤面·汤粉", "tags": ["面食", "米粉", "汤"],
              "optional_children": [
                  {"id": "noodle-rich", "name": "浇头豪横", "tags": ["肉", "汤"]},
                  {"id": "noodle-clear", "name": "清汤简约", "tags": ["清淡", "鲜"]},
                  {"id": "noodle-sour-spicy", "name": "酸辣开胃", "tags": ["酸辣", "开胃"]},
              ]},
             {"id": "rice-bowl", "name": "米饭系", "tags": ["米饭"],
              "optional_children": [
                  {"id": "rice-meat", "name": "荤盖浓香", "tags": ["肉", "浓郁", "下饭"]},
                  {"id": "rice-light", "name": "素/蛋清爽", "tags": ["蔬菜", "清淡"]},
                  {"id": "rice-fried", "name": "炒饭锅气", "tags": ["炒", "镬气"]},
              ]},
             {"id": "filled", "name": "带馅面食", "tags": ["带馅", "面食"],
              "optional_children": [
                  {"id": "filled-boil", "name": "水煮", "tags": ["汤"]},
                  {"id": "filled-fry", "name": "煎烙", "tags": ["香", "酥脆"]},
                  {"id": "filled-steam", "name": "蒸制", "tags": ["清淡"]},
              ]},
             {"id": "noodle-dry", "name": "干香主食", "tags": ["面食", "饼类"],
              "optional_children": [
                  {"id": "dry-hot", "name": "热拌浓酱", "tags": ["浓郁", "香"]},
                  {"id": "dry-cold", "name": "凉吃爽口", "tags": ["凉拌", "清爽"]},
                  {"id": "dry-wrap", "name": "饼卷堡夹", "tags": ["饼类", "肉"]},
              ]},
         ]},
        {"id": "meat", "name": "硬菜小炒系", "tags": ["肉"],
         "children": [
             {"id": "meat-stir", "name": "家常小炒", "tags": ["炒", "肉", "镬气"],
              "optional_children": [
                  {"id": "stir-rice", "name": "下饭重口", "tags": ["下饭", "微辣"]},
                  {"id": "stir-soft", "name": "家常温和", "tags": ["酸甜", "不辣"]},
              ]},
             {"id": "meat-braise", "name": "烧炖卤", "tags": ["炖卤", "肉", "暖"],
              "optional_children": [
                  {"id": "stew-pork", "name": "红烧肉系", "tags": ["浓郁", "甜口"]},
                  {"id": "stew-chicken", "name": "黄焖鸡系", "tags": ["微辣", "下饭"]},
                  {"id": "stew-beef", "name": "牛腩系", "tags": ["汤", "暖"]},
              ]},
             {"id": "meat-grill", "name": "烤煎炸", "tags": ["烤", "肉"],
              "optional_children": [
                  {"id": "grill-chicken", "name": "烤鸡炸鸡系", "tags": ["香", "酥脆"]},
                  {"id": "grill-beef-pork", "name": "牛猪排系", "tags": ["浓郁"]},
                  {"id": "grill-fish", "name": "烤鱼类", "tags": ["鱼鲜", "微辣"]},
              ]},
             {"id": "meat-fish", "name": "鱼鲜水煮", "tags": ["鱼鲜", "汤"],
              "optional_children": [
                  {"id": "fish-suancai", "name": "酸菜鱼系", "tags": ["酸辣", "开胃"]},
                  {"id": "fish-tomato", "name": "番茄鱼汤系", "tags": ["番茄", "酸甜"]},
                  {"id": "fish-boil", "name": "水煮沸腾系", "tags": ["麻辣", "爆辣"]},
              ]},
         ]},
        {"id": "pot", "name": "汤锅烫煮系", "tags": ["汤", "暖"],
         "children": [
             {"id": "pot-soup", "name": "炖汤煲汤", "tags": ["汤", "暖"],
              "optional_children": [
                  {"id": "soup-meat", "name": "肉汤浓煲", "tags": ["肉", "暖"]},
                  {"id": "soup-fish-tofu", "name": "鱼头豆腐砂锅", "tags": ["鱼鲜", "鲜"]},
                  {"id": "soup-veg", "name": "素汤清汤", "tags": ["蔬菜", "清淡"]},
              ]},
             {"id": "pot-tang", "name": "烫煮自选", "tags": ["烫煮", "汤"],
              "optional_children": [
                  {"id": "tang-malatang", "name": "麻辣烫/冒菜", "tags": ["麻辣"]},
                  {"id": "tang-chuan", "name": "串串/钵钵鸡", "tags": ["麻辣", "凉拌"]},
                  {"id": "tang-hotpot", "name": "一人小火锅", "tags": ["暖", "烫煮"]},
              ]},
             {"id": "pot-congee", "name": "粥品", "tags": ["粥", "暖", "清淡"],
              "optional_children": [
                  {"id": "congee-meat", "name": "肉粥砂锅粥", "tags": ["肉", "鲜"]},
                  {"id": "congee-plain", "name": "清粥小菜", "tags": ["清淡"]},
              ]},
         ]},
        {"id": "light", "name": "轻食小食系", "tags": ["清爽"],
         "children": [
             {"id": "light-cold", "name": "凉拌系", "tags": ["凉拌", "清爽"],
              "optional_children": [
                  {"id": "cold-meat", "name": "荤凉", "tags": ["肉", "开胃"]},
                  {"id": "cold-veg", "name": "素凉", "tags": ["蔬菜"]},
              ]},
             {"id": "light-salad", "name": "冷轻食", "tags": ["清爽", "冰凉"],
              "optional_children": [
                  {"id": "salad-poke", "name": "波奇/谷物碗", "tags": ["鱼鲜"]},
                  {"id": "salad-sandwich", "name": "三明治/饭团", "tags": ["饼类"]},
              ]},
             {"id": "light-snack", "name": "小食解馋", "tags": ["小食", "解馋"],
              "optional_children": [
                  {"id": "snack-fried", "name": "炸物系", "tags": ["酥脆", "香"]},
                  {"id": "snack-lu", "name": "卤味系", "tags": ["炖卤", "开胃"]},
                  {"id": "snack-skewer", "name": "串串烤物", "tags": ["烤"]},
              ]},
             {"id": "light-dimsum", "name": "点心蒸笼", "tags": ["点心", "清淡"],
              "optional_children": [
                  {"id": "dimsum-canopy", "name": "小笼蒸饺", "tags": ["带馅"]},
                  {"id": "dimsum-rice-noodle", "name": "肠粉", "tags": ["鲜"]},
              ]},
         ]},
    ],
}

# 正交维度（横向）：取值封闭，任何未锁状态可问
ORTHOGONAL = [
    {"id": "spice", "name": "辣度", "values": ["不辣", "微辣", "中辣", "爆辣"]},
    {"id": "texture", "name": "浓淡", "values": ["清淡", "浓郁"]},   # 图谱§4.1：清爽≈清淡近义、暖迁 temp
    {"id": "protein", "name": "蛋白主料", "values": ["牛肉", "猪肉", "鸡鸭", "鱼鲜"]},
    {"id": "temp", "name": "温度", "values": ["热乎", "温热", "冰凉"]},
    {"id": "pace", "name": "节奏", "values": ["要快", "慢享"]},
]
# 正交近义/迁移容错（图谱§4.1：旧会话取值归一；仅纯正交语义词——
# 「清爽/暖」等词同时存在于链 tags，须先从链启发中剔除防截胡）
# 需求向→属性向映射（图谱§5.2）：菜库 dish_library.tags 是用户需求向，
# 链/本地池是属性向——本地收口打分前按此归一，否则两套词表无法交集。
NEED_TO_ATTR = {
    "想喝汤": ("汤",), "想吃热乎": ("暖", "热乎"), "想吃冷的": ("冰凉", "清爽"),
    "要快": ("要快",), "想慢享": ("慢享",),
    "重口味": ("浓郁",), "不吃辣": ("不辣",), "清淡": ("清淡",),
}


def to_attr_tags(tags) -> set:
    """菜库需求向 tags → 属性向集合（未知词原样保留，容错自造词）。"""
    out = set()
    for t in tags or []:
        t = str(t)
        if t in NEED_TO_ATTR:
            out.update(NEED_TO_ATTR[t])
        else:
            out.add(t)
    return out


ORTHO_ALIASES = {"清爽": ("texture", "清淡"), "暖": ("temp", "热乎")}
# 链 tags 别名（LLM 选项自造词→词表词；重放 005 实证「汤水」不入表致链失锁）
CHAIN_TAG_ALIASES = {"汤水": "汤", "带汤": "汤", "汤面": "面食", "盖饭": "米饭",
                     "硬货": "肉"}

# 兄弟互斥的独有 tags（校验用：某选项 tags 命中兄弟独有词＝跨类漂移）
_BY_ID = {n["id"]: n for n in CHAIN["children"]}
for _c in CHAIN["children"]:
    for _g in _c.get("children", []) + _c.get("optional_children", []):
        _BY_ID[_g["id"]] = _g
        for _gg in _g.get("optional_children", []):
            _BY_ID[_gg["id"]] = _gg


def _find(node, nid):
    if node["id"] == nid:
        return node
    for ch in node.get("children", []) + node.get("optional_children", []):
        r = _find(ch, nid)
        if r:
            return r
    return None


def find_node(nid):
    """按 id 找分类链节点（含根）。"""
    return _find(CHAIN, nid) if nid else None


# ---------- 状态机：从 question_log 重建收敛状态 ----------
def build_state(log):
    """从答题 log 重建收敛状态：分类链路径＋正交锁定。

    log 步骤格式：{"question", "option_text", "tags": [..], "dim": "节点id"}。
    tags 为空的历史步骤（旧会话）按词表启发归类（容错，不抛错）。
    """
    chain_ids, ortho = [], {}
    for x in log or []:
        tags = {t if t not in CHAIN_TAG_ALIASES else CHAIN_TAG_ALIASES[t]
                for t in (x.get("tags") or [])}
        dim = x.get("dim") or ""
        if not dim:                            # 步级 dim 缺失（旧会话）：选项内提取
            for o in x.get("options") or []:
                if isinstance(o, dict) and o.get("dim"):
                    dim = o["dim"]
                    break
        node = find_node(dim)
        # F2 修复（真机 D 流程实证 2026-09-24）：dim 是已知正交维度＝本题测的
        # 就是正交轴，其 tags（清淡/暖…）不再启发挂链——「清淡」曾误挂 pot-congee
        # 把用户选的主食路径系统性改写成粥。仅 dim 完全缺失（旧会话）才启发。
        if node is None and not dim:
            # 无任何 dim 信息（旧会话）→ 启发（纯正交语义词不进链防截胡）
            # F2 补完（生产 F4 排查实证 2026-09-25）：剔除集不只 ORTHO_ALIASES
            # 近义词，须含全部正交取值域词——「清淡」撞 pot-congee、「冰凉」撞
            # light-salad 的链 tags，本地题库 texture 题选项无 dim（生产可达），
            # 正交答案曾被挂上假链（假链→可用维度错位→兜底重问乱象放大器）。
            ortho_words = set(ORTHO_ALIASES)
            for od in ORTHOGONAL:
                ortho_words.update(od["values"])
            rest = tags - ortho_words
            node = _guess_chain_node(rest) if rest else None
        # F4-残修复（9/26，真机 P5 实证）：dim=form 的条目＝LLM 首题方向词
        # 被覆写为 form 的存量路径——按已表达方向（tags∩L1 tags 或文案别名）
        # 下沉 L1，用户首问选择入链（不再留链尾 [form] 给兜底步索引乱带偏）
        if node is not None and node["id"] == CHAIN["id"]:
            sink = _sink_l1(tags, x.get("option_text", ""))
            if sink is not None:
                node = sink
        if node:
            # 同支相容守卫（2026-09-16 重放 005 实证）：链非空时启发归类节点必须
            # 在链尾子树内（或为链尾祖先）——跨支启发结果跳过不入链，防链污染
            if chain_ids:
                tip = find_node(chain_ids[-1])
                tip_tree = {a["id"] for a in _subtree(tip)} if tip else set()
                node_tree = {a["id"] for a in _subtree(node)}
                if node["id"] not in tip_tree and chain_ids[-1] not in node_tree:
                    continue
            if node["id"] not in chain_ids:
                chain_ids.append(node["id"])
            continue
        for od in ORTHOGONAL:                  # 正交：tags ∩ 取值域
            hit = sorted(tags & set(od["values"]))
            if hit and od["id"] not in ortho:
                ortho[od["id"]] = hit[0]
                continue
            for alias, (aid, val) in ORTHO_ALIASES.items():   # 旧取值容错归一
                if alias in tags and aid not in ortho:
                    ortho[aid] = val
                    break
    return {"chain": chain_ids, "ortho": ortho}


_ORTHO_IDS = frozenset(od["id"] for od in ORTHOGONAL)


def tail_ortho_streak(log) -> int:
    """log 尾部连续正交题步数（F4 链下钻判定用）。

    单步判正交：dim 是正交维度 id（LLM 正交题选项 dim 归一为题维度），
    或无 dim 且 tags 命中任一正交取值域（本地正交题）。链题 dim 恒为
    链节点 id，与正交 id 无交集，不会误判。
    """
    n = 0
    for x in reversed(log or []):
        dim = x.get("dim") or ""
        if dim:
            if dim in _ORTHO_IDS:
                n += 1
                continue
            break                     # 链节点 id＝链题，连击终止
        tags = set(x.get("tags") or [])
        if any(tags & set(od["values"]) for od in ORTHOGONAL):
            n += 1
            continue
        break                         # 无 dim 无正交命中＝旧会话/未知，保守终止
    return n


def _subtree(node):
    """节点及其全部子孙（含 optional）——同支相容守卫用。"""
    out = [node]
    for ch in node.get("children", []) + node.get("optional_children", []):
        out.extend(_subtree(ch))
    return out


def _guess_chain_node(tags):
    """无 dim 标注时的 tags 启发归类（取 tags 重合度最高的链节点）。"""
    best, best_n = None, 0
    for nid in ("noodle-soup", "rice-bowl", "filled", "noodle-dry",
                "meat-stir", "meat-braise", "meat-grill", "meat-fish",
                "pot-soup", "pot-tang", "pot-congee",
                "light-cold", "light-salad", "light-snack", "light-dimsum",
                "staple", "meat", "pot", "light"):
        node = _BY_ID.get(nid)
        n = len(tags & set(node["tags"]))
        if n > best_n:
            best, best_n = node, n
    return best


def available_dims(state):
    """可用维度集＝分类链子树前沿 ∪ 未锁正交维度。

    返回 [{"id","name","kind":"chain"/"ortho","tags"/"values"}]，供 prompt 注入与校验。
    """
    chain = state["chain"]
    out = []
    if not chain:
        out.append({"id": CHAIN["id"], "name": CHAIN["name"],
                    "kind": "chain", "tags": []})
    else:
        tip = chain[-1]
        node = find_node(tip)
        for ch in node.get("children", []) + node.get("optional_children", []):
            out.append({"id": ch["id"], "name": ch["name"],
                        "kind": "chain", "tags": ch["tags"]})
    locked_ortho = set(state["ortho"])
    for od in ORTHOGONAL:
        if od["id"] not in locked_ortho:
            out.append({"id": od["id"], "name": od["name"],
                        "kind": "ortho", "values": od["values"]})
    return out


def chain_depth(state):
    """分类链锁定深度（form 根计 1，每深入一层 +1；未锁＝0）。"""
    return len(state["chain"])


def should_finalize(state, step, min_required=None):
    """收口引擎终裁：分类链走到叶或深≥3，且正交≥1 → 信息足够；或超步数强收。

    （链未到叶时即使正交已锁也继续细分——防「主食正餐」粗粒度收口。）
    """
    tip = find_node(state["chain"][-1]) if state["chain"] else None
    # optional_children（可选细化层）不计入收口义务：链到「实质叶」＋必锁正交即可收；
    # 必锁集只认 spice/texture（图谱§4 工程约束：正交扩 5 支后防步数被吃掉，
    # protein/temp/pace 是加分项不是义务）。
    real = (tip or {}).get("children", [])   # 普通 children＝必走层；optional 不计（图谱语义）
    chain_done = bool(state["chain"]) and (not real or len(state["chain"]) >= 3)
    must_locked = any(k in state["ortho"] for k in ("spice", "texture"))
    if chain_done and must_locked:
        return True
    return step >= MAX_ASK_STEPS


MAX_ASK_STEPS = 6     # 导航式出题的强制收口步数（漏斗后步数确定，防极端循环）


# ---------- 验收器：LLM 出题合规 ----------
# L1 别名表（validate form 覆盖判定＋build_state form 根条目下沉共用；
# 2026-09-26 自 validate_question 内提取为模块级单源）
_L1_ALIAS = {"staple": ("主食", "谷物", "饭", "面"),
             "meat": ("硬菜", "肉", "炒菜", "小炒"),
             "pot": ("汤锅", "汤水", "汤", "烫煮", "粥"),
             "light": ("轻食", "小食", "凉", "点心", "清爽")}


def _sink_l1(tags, option_text: str):
    """form 根条目下沉：按已表达方向锁定 L1（F4-残修复，9/26）。

    LLM form 题选项 dim 曾被整体覆写为 form（quiz.py 9/17 既有），用户首问
    表达的方向（硬菜→meat）不入链 → 链停 [form]，后续强制期兜底按步索引
    乱选分支（真机 P5：选硬菜被带偏 pot-soup 端牛肉拉面）。双保险之一：
    存量会话/无 dim 选项在此按 tags∩L1 tags 或文案别名下沉；新会话由
    quiz 层保留选项 dim 直接锁 L1（两路径链深语义对齐本地题库路径）。
    """
    text = str(option_text or "")
    for l1 in CHAIN["children"]:
        if tags & set(l1.get("tags") or []):
            return l1
    for l1 in CHAIN["children"]:
        if any(a in text for a in _L1_ALIAS.get(l1["id"], ())):
            return l1
    return None


def validate_question(out, state, min_form_branches=2):
    """校验 LLM 出题：返回 (True, 归一化题) 或 (False, 原因)。

    检查：dimension ∈ 可用集；选项 2~4 个且各带 tags；chain 维度选项与兄弟
    独有 tags 无跨类；ortho 维度选项 tags 命中取值域；form 选项覆盖大方向
    分支数 ≥ min_form_branches（owner 拍板放宽 2026-09-25：3→2——生产拒因
    form_narrow:2 ×13＝43% 本地兜底主源；config quiz.form_branch_min 可翻回）。
    搭配/健康词由 quiz 层拦截。
    """
    if not isinstance(out, dict):
        return False, "not_dict"
    dim = str(out.get("dimension", "")).strip()
    dims = {d["id"]: d for d in available_dims(state)}
    if dim not in dims:
        return False, f"dim_not_available:{dim}"
    d = dims[dim]
    opts = out.get("options")
    if not isinstance(opts, list) or not (2 <= len(opts) <= 4):
        return False, "bad_options_count"
    # 根维度覆盖校验（2026-09-16 owner 五连撞实证：LLM 路径依赖用「汤vs干」二分，
    # 4 大系砍成 2 支＝首问即卡死）：form 出题须 ≥3 选项且覆盖 ≥3 个 L1 分支
    # （选项 dim 或 tags 命中均可）；不满足→拒，本地四方向题兜底。
    if dim == CHAIN["id"]:
        # L1 覆盖判定（2026-09-16 拒因取证：LLM 按指引给「主食/硬菜/汤锅/轻食」
        # 但精确词表交集计 0 误拒）——dim 命中 OR 别名/名称子串匹配。
        # 9/26 审查缺陷①修复：本循环先于逐元素 isinstance 校验裸遍历 opts，
        # 混合类型（首元素 dict＋后续 str/null）曾 AttributeError→/next 500
        # 击穿「验收不过→本地兜底」红线——补元素守卫。
        covered = set()
        for o in opts:
            if not isinstance(o, dict):
                return False, "bad_option"
            odim = str(o.get("dim", "") or "")
            if odim in _L1_ALIAS:
                covered.add(odim)
                continue
            otext = str(o.get("text", ""))
            otags = "".join(str(t) for t in (o.get("tags") or []))
            for lid, aliases in _L1_ALIAS.items():
                if any(a in otext or a in otags for a in aliases):
                    covered.add(lid)
                    break
        # 分支下限 owner 拍板放宽（2026-09-25）：≥3 → ≥2（默认 2，可经
        # config quiz.form_branch_min 翻回 3 无需改码）；选项数下限同步
        _minfb = max(2, int(min_form_branches or 2))
        if len(opts) < _minfb or len(covered) < _minfb:
            return False, f"form_narrow:{len(covered)}"
    norm = []
    for o in opts:
        if not isinstance(o, dict) or not o.get("text"):
            return False, "bad_option"
        tags = [str(t)[:12] for t in (o.get("tags") or [])][:6]
        if not tags:
            return False, "option_no_tags"
        ts = set(tags)
        if d["kind"] == "ortho":
            if not (ts & set(d["values"])):
                return False, f"ortho_mismatch:{d['id']}"
        else:
            node = find_node(dim)
            # F3 修复（真机 A/C 实证 2/2）：兄弟互斥先行——选项 tags 命中兄弟
            # 独有 tags 时拒绝（「干拌的（凉拌）」挂 noodle-soup＝跨支漂移）
            if node and node.get("tags"):
                dim_tags = set(node["tags"])
                sibs = []
                for l1 in CHAIN["children"]:
                    branch_ids = {l1["id"]} | {c["id"] for c in
                        l1.get("children", []) + l1.get("optional_children", [])}
                    if dim in branch_ids:
                        continue              # dim 所属支整体排除（含 dim 自身）
                    sibs += l1.get("children", []) + l1.get("optional_children", [])
                # 兄弟【独有】tags＝兄弟有而「dim 自身」没有的 tag。
                # 修正（评审 sess_1702b6b7 发现 1 实锤）：原实现把兄弟 tags 并入
                # own_tree_tags → sib_exclusive 恒空集、互斥校验恒放行。
                # 共享语义豁免只认 dim 自身 tags（如 noodle-soup 的「汤」）——
                # 子树 tag 豁免会让「凉拌/干拌」借 noodle-rich 的「肉」漏网。
                own_only = set(dim_tags)
                sib_exclusive = set()
                for sib in sibs:
                    sib_exclusive |= set(sib.get("tags") or []) - own_only
                # F9 根因修复（回归轮 2026-09-25）：此内层循环曾复用外层变量名 o
                # ——遮蔽后 norm 选项的 id/text 取自末位选项而 tags 取自当前选项
                # ＝「同文案不同 tags」双胞胎按钮的制造机（自 F3 落地即存在；
                # 上轮「米粉标米饭」观察 B 同源）。改独立名 so。
                # 9/26 审查缺陷①修复：内层在逐元素 isinstance 校验（外层）之前
                # 遍历全部选项——混合类型（dict＋str/null）曾 so.get →AttributeError
                # →/next 500；补元素守卫跳过（拒由外层循环统一裁决）。
                for so in opts:
                    if not isinstance(so, dict):
                        continue
                    ots = set(so.get("tags") or [])
                    cross = ots & sib_exclusive
                    o_dim_node = (find_node(str(so.get("dim") or "")) if so.get("dim") else None)
                    # 豁免（9/26 审查缺陷②修复）：选项 dim 声明 dim **子树内**
                    # 节点（含自身＝同层、子级＝细划）→ 不拒；指向子树外
                    # （兄弟支）＝LLM 导航声明错误 → 拒。原实现只认同节点，
                    # 「本支子级 dim＋跨支独有词」的合法细划曾被误拒
                    # （v1.5 去跨支词后 dry-cold 的凉拌必落 sib_exclusive）。
                    if cross and o_dim_node and \
                            o_dim_node["id"] not in {n["id"] for n in _subtree(node)}:
                        return False, f"SiblingConflict:exclusive={sorted(cross)}"
            # v1.5 层级语义（2026-09-25 树替换配套）：L3 已去继承词，选项用
            # 子维度更细 tags（如 noodle-dry 题选项带 dry-cold 的「凉拌」、
            # meat-grill 题带 grill-fish 的「鱼鲜」）＝dim 自身子树内合法——
            # 按子树 tags 并集判交；出子树（跨支漂移）仍拒。form 豁免
            # （其有专门 l1_alias 覆盖门，且空 tags 为设计态）。
            if dim != CHAIN["id"]:
                sub_tags = {t for n in _subtree(node) for t in (n.get("tags") or [])} \
                    if node else set()
                if sub_tags and not (ts & sub_tags):
                    return False, f"chain_mismatch:{dim}"
        norm.append({"id": str(o.get("id", ""))[:24], "text": str(o["text"])[:20],
                     "tags": tags,
                     # F4-残配套（9/26）：透传选项自带 dim——form 题选项声明 L1
                     # 时由 quiz 层保留（用户首问方向直接入链）
                     **({"dim": str(o.get("dim"))[:40]} if o.get("dim") else {})})
    # F9 修复（回归轮 P1/P3 实证 2026-09-25）：同文案双胞胎选项拒——两个
    # 按钮文字一模一样而 tags 互相矛盾（其一还带兄弟支 tag），用户等于少
    # 一个选项且错标 tags 会污染链状态。拒→本地题库兜底。
    texts = [o["text"] for o in norm]
    if len(set(texts)) != len(texts):
        return False, f"dup_option_text:{dim}"
    return True, {"dimension": dim, "question": str(out.get("question", ""))[:60],
                  "options": norm}


# ---------- finalize 一致性：菜名 vs 已锁分类链（关键词级） ----------
_DISH_HINTS = {
    # 图谱 v1.5 附录 B 全量对照表（2026-09-25 整表替换）：L3 行只保留强身份节点
    # （noodle 三兄弟/rice-fried/dry-wrap/stew-beef/grill-fish），其余 L3 不设行——
    # 链钻到 L3 时按最近有词祖先（L2）收口＝一致集更宽（F8-b 窄链同族收益）。
    # 分配三原则（附录 B 头注）：漏词＝误杀（宽词优先）；跨支可共用（面/煲/饼）；
    # 本表职责＝收口对齐，跨类漂移由 validate/_guess_chain_node 前置防线拦。
    # ---- staple 谷物主食系 ----
    "noodle-soup": ("面", "粉", "米线", "馄饨", "云吞", "泡馍", "粿条"),
    "noodle-rich": ("牛肉", "肥牛", "牛杂", "排骨", "叉烧"),
    "noodle-clear": ("清汤", "阳春", "上汤"),
    "noodle-sour-spicy": ("酸辣", "螺蛳", "酸汤"),
    "rice-bowl": ("饭", "煲仔", "丼", "拌饭", "盖浇", "麻婆"),  # 麻婆＝下饭心智（图谱§6.1 川湘行仲裁：麻婆豆腐→rice-bowl）
    "rice-fried": ("炒饭",),
    "filled": ("饺", "锅贴", "生煎", "包子", "盒子", "馄饨"),  # 烧麦→light-dimsum；馄饨双语境（边界注4）
    "noodle-dry": ("面", "凉皮", "热干", "油泼", "燃面", "意面", "夹馍"),
    "dry-wrap": ("夹馍", "饼", "汉堡", "披萨", "卷", "手抓"),
    # ---- meat 硬菜小炒系 ----
    "meat-stir": ("炒", "小炒", "回锅", "里脊", "木须", "锅包"),  # 泛「炒」保不误杀；炒饭漂移由前置防线拦
    "meat-braise": ("炖", "卤", "煲", "红烧", "焖", "扣肉", "东坡", "水煮牛肉", "水煮肉片"),
    "stew-beef": ("牛腩", "牛肉"),
    "meat-grill": ("烤", "煎", "炸", "鸡排", "牛排", "猪排"),
    "grill-fish": ("烤鱼", "纸包鱼"),          # 先烤后炖心智归烤（附录 D）
    "meat-fish": ("酸菜鱼", "水煮鱼", "沸腾", "番茄鱼", "豆花鱼", "鱼"),
    # ---- pot 汤锅烫煮系 ----
    "pot-soup": ("汤", "煲", "砂锅", "猪肚", "排骨"),
    "pot-tang": ("麻辣烫", "冒菜", "串串", "钵钵", "小火锅", "香锅"),
    "pot-congee": ("粥",),
    # ---- light 轻食小食系 ----
    "light-cold": ("凉拌", "口水鸡", "白切", "拍黄瓜", "大拌菜"),
    "light-salad": ("沙拉", "波奇", "三明治", "饭团", "定食"),
    "light-snack": ("小龙虾", "卤味", "炸鸡架", "关东煮", "烤肠", "串"),
    "light-dimsum": ("小笼", "虾饺", "肠粉", "烧麦", "凤爪", "蒸饺", "蒸蛋"),  # 蒸蛋羹＝蒸制家常（附录 B 边界注 5）
}


def dish_consistent(name: str, state) -> bool:
    """收口菜名与已锁分类链一致（校验链最末有 tags 语义的节点；无锁定→True）。"""
    for nid in reversed(state["chain"]):
        hints = _DISH_HINTS.get(nid)
        if hints:
            return any(h in (name or "") for h in hints)
    return True
