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
    "id": "form", "name": "餐食形态", "tags": [],
    "children": [
        {"id": "staple", "name": "谷物主食系", "tags": ["面食", "米饭"],
         "children": [
             {"id": "noodle-soup", "name": "汤面·汤粉", "tags": ["面食", "米粉", "汤"],
              "optional_children": [
                  {"id": "noodle-rich", "name": "浇头豪横", "tags": ["面食", "汤", "肉"]},
                  {"id": "noodle-clear", "name": "清汤简约", "tags": ["清淡", "鲜"]},
                  {"id": "noodle-sour-spicy", "name": "酸辣开胃", "tags": ["酸辣", "开胃"]},
              ]},
             {"id": "rice-bowl", "name": "米饭系", "tags": ["米饭"],
              "optional_children": [
                  {"id": "rice-meat", "name": "荤盖浓香", "tags": ["米饭", "肉", "下饭"]},
                  {"id": "rice-light", "name": "素/蛋清爽", "tags": ["米饭", "清淡"]},
                  {"id": "rice-fried", "name": "炒饭锅气", "tags": ["炒", "镬气"]},
              ]},
             {"id": "filled", "name": "带馅面食", "tags": ["带馅", "面食"],
              "optional_children": [
                  {"id": "filled-boil", "name": "水煮（水饺/馄饨）", "tags": ["带馅", "汤"]},
                  {"id": "filled-fry", "name": "煎烙（锅贴/生煎）", "tags": ["带馅", "酥脆"]},
                  {"id": "filled-steam", "name": "蒸制（包子/小笼）", "tags": ["带馅", "清淡"]},
              ]},
             {"id": "noodle-dry", "name": "干香主食", "tags": ["面食", "饼类", "凉拌"],
              "optional_children": [
                  {"id": "dry-hot", "name": "热拌浓酱", "tags": ["面食", "浓郁"]},
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
                  {"id": "stew-pork", "name": "红烧肉系", "tags": ["炖卤", "浓郁", "甜口"]},
                  {"id": "stew-chicken", "name": "黄焖鸡系", "tags": ["微辣", "下饭"]},
                  {"id": "stew-beef", "name": "牛腩系", "tags": ["汤", "暖"]},
              ]},
             {"id": "meat-grill", "name": "烤煎炸", "tags": ["烤", "肉", "鱼鲜"],
              "optional_children": [
                  {"id": "grill-chicken", "name": "烤鸡炸鸡系", "tags": ["酥脆", "香"]},
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
             {"id": "pot-soup", "name": "炖汤煲汤", "tags": ["汤", "暖", "鱼鲜"],
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
        {"id": "light", "name": "轻食小食系", "tags": ["凉拌", "清爽"],
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
             {"id": "light-snack", "name": "小食解馋", "tags": ["小食", "解馋", "酥脆", "开胃", "烤"],
              "optional_children": [
                  {"id": "snack-fried", "name": "炸物系", "tags": ["酥脆", "香"]},
                  {"id": "snack-lu", "name": "卤味系", "tags": ["炖卤", "开胃"]},
                  {"id": "snack-skewer", "name": "串串烤物", "tags": ["烤"]},
              ]},
             {"id": "light-dimsum", "name": "点心蒸笼", "tags": ["点心", "清淡", "带馅", "鲜"],
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
            pure_ortho = tags & set(ORTHO_ALIASES)
            rest = tags - pure_ortho
            node = _guess_chain_node(rest) if rest else None
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
def validate_question(out, state):
    """校验 LLM 出题：返回 (True, 归一化题) 或 (False, 原因)。

    检查：dimension ∈ 可用集；选项 2~4 个且各带 tags；chain 维度选项与兄弟
    独有 tags 无跨类；ortho 维度选项 tags 命中取值域。搭配/健康词由 quiz 层拦截。
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
        # 但精确词表交集计 0 误拒）——dim 命中 OR 别名/名称子串匹配
        l1_alias = {"staple": ("主食", "谷物", "饭", "面"),
                    "meat": ("硬菜", "肉", "炒菜", "小炒"),
                    "pot": ("汤锅", "汤水", "汤", "烫煮", "粥"),
                    "light": ("轻食", "小食", "凉", "点心", "清爽")}
        covered = set()
        for o in opts:
            odim = str(o.get("dim", "") or "")
            if odim in l1_alias:
                covered.add(odim)
                continue
            otext = str(o.get("text", ""))
            otags = "".join(str(t) for t in (o.get("tags") or []))
            for lid, aliases in l1_alias.items():
                if any(a in otext or a in otags for a in aliases):
                    covered.add(lid)
                    break
        if len(opts) < 3 or len(covered) < 3:
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
                # 兄弟【独有】tags＝兄弟有而「dim 及其子树」完全没有的 tag
                # （共享语义如「汤」在 noodle-rich 子树同样存在＝不算干拌信号）
                own_tree_tags = set(dim_tags)
                for sib in sibs:
                    own_tree_tags |= set(sib.get("tags") or [])
                sib_exclusive = set()
                for sib in sibs:
                    sib_exclusive |= set(sib.get("tags") or []) - own_tree_tags
                if ts & sib_exclusive:
                    return False, f"SiblingConflict:exclusive={sorted(ts & sib_exclusive)}"
            if node and node["tags"] and not (ts & set(node["tags"])):
                # 允许 LLM 用子维度更细 tags：与父节点 tags 有交集即可，否则视为漂移
                return False, f"chain_mismatch:{dim}"
        norm.append({"id": str(o.get("id", ""))[:24], "text": str(o["text"])[:20],
                     "tags": tags})
    return True, {"dimension": dim, "question": str(out.get("question", ""))[:60],
                  "options": norm}


# ---------- finalize 一致性：菜名 vs 已锁分类链（关键词级） ----------
_DISH_HINTS = {
    # 图谱附录 B（2026-09-16 补强）：关键词级收口一致性；烤鱼→grill、酸菜鱼→fish 的边界
    "noodle-soup": ("面", "粉", "米线", "馄饨", "云吞"),
    "noodle-rich": ("牛肉", "叉烧", "排骨", "牛杂"),
    "noodle-clear": ("清汤", "阳春", "上汤"),
    "noodle-sour-spicy": ("酸辣", "螺蛳", "酸汤"),
    "rice-bowl": ("饭", "煲仔", "丼", "拌饭"),
    "rice-meat": ("饭",),
    "rice-light": ("饭", "蛋"),
    "rice-fried": ("炒饭", "拌饭"),
    "filled": ("饺", "包子", "馅", "烧麦", "锅贴", "生煎"),
    "filled-boil": ("水饺", "馄饨"),
    "filled-fry": ("锅贴", "生煎", "盒子"),
    "filled-steam": ("包子", "小笼", "烧麦", "蒸饺"),
    "noodle-dry": ("拌面", "凉面", "热干", "燃面", "油泼"),
    "dry-hot": ("热干", "炸酱", "油泼"),
    "dry-cold": ("凉皮", "凉面", "捞汁"),
    "dry-wrap": ("夹馍", "饼", "汉堡", "手抓饼", "卷", "三明治"),
    "meat-stir": ("炒", "小炒", "回锅", "里脊", "鱼香", "木须"),
    "stir-rice": ("小炒", "回锅", "鱼香"),
    "stir-soft": ("番茄炒蛋", "糖醋", "木须"),
    "meat-braise": ("炖", "卤", "煲", "红烧", "焖", "黄焖"),
    "stew-pork": ("红烧肉", "卤肉", "东坡"),
    "stew-chicken": ("黄焖鸡", "焖", "鸡"),
    "stew-beef": ("牛腩", "牛肉", "炖"),
    "meat-grill": ("烤", "煎", "炸", "排"),
    "grill-chicken": ("烤鸡", "鸡排", "炸鸡", "鸡"),
    "grill-beef-pork": ("牛排", "猪排", "烤"),
    "grill-fish": ("烤鱼", "纸包鱼"),
    "meat-fish": ("鱼", "酸菜", "沸腾", "水煮鱼", "豆花鱼"),
    "fish-suancai": ("酸菜鱼", "金汤"),
    "fish-tomato": ("番茄鱼",),
    "fish-boil": ("水煮鱼", "沸腾鱼"),
    "pot-soup": ("汤", "煲", "炖汤", "猪肚", "排骨"),
    "soup-meat": ("牛腩煲", "猪肚鸡", "排骨汤", "老鸭"),
    "soup-fish-tofu": ("鱼头", "豆腐汤"),
    "soup-veg": ("味噌", "上汤", "素汤"),
    "pot-tang": ("麻辣烫", "冒菜", "串串", "钵钵鸡", "小火锅", "关东煮"),
    "tang-malatang": ("麻辣烫", "冒菜"),
    "tang-chuan": ("串串", "钵钵鸡"),
    "tang-hotpot": ("小火锅",),
    "pot-congee": ("粥",),
    "congee-meat": ("砂锅粥", "皮蛋瘦肉", "艇仔"),
    "congee-plain": ("白粥", "清粥"),
    "light-cold": ("凉", "拌", "口水鸡", "大拌菜"),
    "cold-meat": ("口水鸡", "白切", "肺片"),
    "cold-veg": ("凉皮", "拍黄瓜", "大拌菜", "木耳"),
    "light-salad": ("沙拉", "波奇", "三明治", "饭团", "谷物碗"),
    "light-snack": ("小龙虾", "卤", "炸", "串", "鸡架", "烤肠"),
    "snack-fried": ("炸鸡", "鸡架", "炸", "烤肠"),
    "snack-lu": ("卤味", "卤", "拼盘"),
    "snack-skewer": ("串", "烤肠"),
    "light-dimsum": ("小笼", "虾饺", "肠粉", "烧麦", "凤爪", "奶黄"),
    "dimsum-canopy": ("小笼", "蒸饺", "虾饺"),
    "dimsum-rice-noodle": ("肠粉",),
}


def dish_consistent(name: str, state) -> bool:
    """收口菜名与已锁分类链一致（校验链最末有 tags 语义的节点；无锁定→True）。"""
    for nid in reversed(state["chain"]):
        hints = _DISH_HINTS.get(nid)
        if hints:
            return any(h in (name or "") for h in hints)
    return True
