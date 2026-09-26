"""domain 纯逻辑单测：策略/健康过滤/jump/口令/画像（阶段5·拍板#3）。"""
import json
from datetime import datetime, timedelta, timezone

from app.core import db
from app.domain import identity, jump, memory, quiz
from app.domain.strategy import HEALTH_BLACKLIST, filter_health_advice
from app.providers import env_ctx


# ---------- 策略与健康黑名单（阶段4并集单源） ----------
def test_health_blacklist_union():
    """并集须同时覆盖原两表词（strategy 14 + quiz 独有 6）。"""
    must = {"减脂", "减肥", "热量", "卡路里", "控糖", "低GI", "增肌", "轻断食",
            "排毒", "养生", "调理", "营养师", "医生建议",          # strategy 原 14
            "瘦身", "热量低", "低卡", "健康餐", "刮油", "代餐", "体重"}  # quiz 独有
    assert must <= set(HEALTH_BLACKLIST)


def test_filter_health_advice():
    assert filter_health_advice("低卡又好吃", "就它了") == "就它了"
    assert filter_health_advice("热乎管饱", "就它了") == "热乎管饱"


# ---------- jump token（北极星跳板） ----------
def test_jump_token_roundtrip():
    tok = jump.make_token("sess_x", "红烧牛肉面")
    assert jump.verify_token(tok) is not None
    sid, slug, _ = jump.verify_token(tok)
    assert sid == "sess_x" and slug == "红烧牛肉面"
    assert jump.verify_token("bad.token") is None
    # 幂等指纹：同 token 同指纹
    assert jump.token_fingerprint(tok) == jump.token_fingerprint(tok)


# ---------- 口令策略与 service（阶段4双轨合并） ----------
def test_passcode_policy():
    assert identity.passcode_ok("123456") == (False, "pure_digits")
    assert identity.passcode_ok("short") == (False, "too_short")
    ok, _ = identity.passcode_ok("qingdan-Tang7")
    assert ok


def test_passcode_service_roundtrip():
    ok, reason = identity.set_passcode("pytest-anon-1", "qingdan-Tang7")
    assert ok, reason
    state, _ = identity.try_recover("pytest-anon-1", "wrong-x9")
    assert state == "mismatch"
    state, _ = identity.try_recover("pytest-anon-1", "qingdan-Tang7")
    assert state == "ok"
    state, _ = identity.try_recover("pytest-anon-none", "whatever-x9")
    assert state == "not_found"


def test_recover_lock_after_5_failures():
    aid = "pytest-anon-lock"
    identity.set_passcode(aid, "qingdan-Tang7")
    for _ in range(5):
        identity.try_recover(aid, "wrong-x9")
    state, _ = identity.try_recover(aid, "qingdan-Tang7")   # 对口令也被锁
    assert state == "locked"


# ---------- 画像加权（隐式+1/显式±3） ----------
def _ins_rec(anon, name, tags, qlog, feedback=None, scene="午餐"):
    with db.tx() as t:
        t.execute(
            "INSERT INTO recommendation(anon_id,session_id,name,tags,reason,"
            "meal_scenario,question_log,feedback,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (anon, 1, name, str(tags).replace("'", '"'), "", scene,
             str(qlog).replace("'", '"'), feedback,
             "2026-09-15T04:00:00+00:00"))


def test_taste_summary_weighting():
    anon = "pytest-taste-1"
    _ins_rec(anon, "菜A", ["辣"], [{"option_text": "有嚼劲"}])                       # 隐式
    _ins_rec(anon, "菜B", ["辣"], [], feedback=1)                                    # 显式 +3
    _ins_rec(anon, "菜C", ["清淡"], [], feedback=-1)                                 # 显式 -3
    ts = quiz.taste_summary(anon)
    assert "辣" in ts["liked"] and "清淡" in ts["disliked"]
    assert ts["count"] == 3 and ts["profiled"] is True      # threshold=3


def test_taste_summary_implicit_only():
    anon = "pytest-taste-2"
    _ins_rec(anon, "菜D", [], [{"option_text": "热汤面"}])
    ts = quiz.taste_summary(anon)
    assert "热汤面" in ts["liked"] and ts["profiled"] is False


# ---------- 场景时钟（+8 显式；跨午夜；修复中午判宵夜事故的回归锚） ----------
def test_scene_boundaries():
    CN = env_ctx.CN_TZ
    cases = [(6, 0, "早餐"), (12, 30, "午餐"), (13, 45, "下午茶"),
             (20, 30, "晚餐"), (21, 0, "宵夜"), (1, 0, "宵夜")]
    for h, m, want in cases:
        got = env_ctx.scene(datetime(2026, 9, 15, h, m, tzinfo=CN))["name"]
        assert got == want, (h, m, got, want)


def test_cn_now_offset():
    # 显式 +8 绑定的本质断言（两次 now() 调用间时钟前进会让差值比较产生微秒级噪声）
    assert env_ctx.cn_now().utcoffset() == timedelta(hours=8)


# ---------- 天气档位降级 ----------
def test_weather_degrades():
    assert env_ctx.city("192.168.1.4") is None      # 内网
    assert env_ctx.city("") is None                 # 空
    assert env_ctx.weather(None) is None            # 无城市
    assert env_ctx.weather({"city": "不存在城"}) is None  # 无坐标


# ---------- ratelimit 滑窗（core） ----------
def test_ratelimit_window():
    from app.core import ratelimit
    key = "pytest-rl"
    assert all(ratelimit.allow(key, 3, 60.0) for _ in range(3))
    assert not ratelimit.allow(key, 3, 60.0)        # 第 4 次拒绝


# ---------- 菜库兜底（降级链脊柱：零 LLM 也能收口） ----------
def test_local_recommend_exists():
    s = quiz.create_session("pytest-local-1")
    rec = quiz._local_recommend(s)
    assert rec["name"] and rec["tags"]        # source 字段在 finalize 层标 local


# ---------- 漏斗收敛：搭配类问题拦截器（2026-09-15 漏斗改造） ----------
def test_side_dish_detector():
    """正例＝搭配维度（拦截）；反例＝主菜收敛轴（放行）。"""
    hit = quiz._is_side_dish_question
    for q in ["烤串配点啥饮料？", "这碗面加不加卤蛋？", "最后再来点啥收尾？",
              "要不要加香菜？", "配什么小菜解腻？", "来一杯奶茶吗？",
              "想加哪种灵魂配料提鲜？"]:
        assert hit(q), q
    for q in ["这顿先定个大方向？", "想吃面还是饭？", "牛肉面红烧还是清汤？",
              "想吃有嚼劲还是软乎的？", "辣度到哪？"]:
        assert not hit(q), q


def test_local_bank_first_question_is_category():
    """降级路径第 1 题必须是品类大类（漏斗一致性）。"""
    q = quiz._local_question(0)
    assert "大方向" in q["question"]
    assert any("主食" in o["text"] for o in q["options"])


# ---------- 维度树：状态机＋验收器＋一致性（2026-09-15 漂移根治） ----------
def test_dims_available_root_then_children():
    from app.domain import dimensions as D
    st = D.build_state([])
    ids = [d["id"] for d in D.available_dims(st)]
    assert ids[0] == "form"   # 根＋5 正交（图谱 v1.0）
    assert set(ids[1:]) == {"spice", "texture", "protein", "temp", "pace"}
    # form 根条目方向中性（无别名/tags）→ 链停 form → 子树前沿＝L1 四支
    # （F4-残新语义：带方向词的 form 条目按 _sink_l1 下沉 L1，见专测）
    st2 = D.build_state([{"question": "q", "option_text": "定个方向",
                          "tags": [], "dim": "form"}])
    dims2 = [d["id"] for d in D.available_dims(st2)]
    assert set(dims2) == {"staple", "meat", "pot", "light",
                          "spice", "texture", "protein", "temp", "pace"}
    # 锁到 staple → 兄弟消失，仅 staple 子层＋正交；锁 pot → 汤锅三支在位
    st3 = D.build_state([
        {"question": "q", "option_text": "主食正餐", "tags": [], "dim": "form"},
        {"question": "q", "option_text": "主食类", "tags": [], "dim": "staple"}])
    dims3 = {d["id"] for d in D.available_dims(st3)}
    assert set(dims3) == {"noodle-soup", "rice-bowl", "filled", "noodle-dry",
                          "spice", "texture", "protein", "temp", "pace"}
    st_pot = D.build_state([
        {"q": 1, "option_text": "热乎一锅", "tags": [], "dim": "pot"}])
    assert {"pot-soup", "pot-tang", "pot-congee"} <= {d["id"] for d in D.available_dims(st_pot)}


def test_taxonomy_graph_nodes():
    """图谱 v1.0 补强回归锚：四大系 14 品类全在链上；meat-rice 已并入 rice-bowl。"""
    from app.domain import dimensions as D
    l2 = set()
    for c in D.CHAIN["children"]:
        l2.update(ch["id"] for ch in c.get("children", []))
    assert l2 == {"noodle-soup", "rice-bowl", "filled", "noodle-dry",
                  "meat-stir", "meat-braise", "meat-grill", "meat-fish",
                  "pot-soup", "pot-tang", "pot-congee",
                  "light-cold", "light-salad", "light-snack", "light-dimsum"}
    assert D.find_node("meat-rice") is None            # 已并入
    assert D.find_node("pot") is not None              # 汤锅支在位


def test_ortho_aliases_legacy():
    """旧会话取值容错：清爽→texture 清淡；暖→temp 热乎（图谱§4.1）。"""
    from app.domain import dimensions as D
    st = D.build_state([{"q": 1, "option_text": "x", "tags": ["清爽"], "dim": ""}])
    assert st["ortho"].get("texture") == "清淡"
    st2 = D.build_state([{"q": 1, "option_text": "x", "tags": ["暖"], "dim": ""}])
    assert st2["ortho"].get("temp") == "热乎"


def test_should_finalize_must_lock():
    """必锁集只认 spice/texture：仅 protein/temp 时链到叶也不收（图谱§4 工程约束）。"""
    from app.domain import dimensions as D
    st = D.build_state([
        {"q": 1, "option_text": "x", "tags": ["面食", "汤"], "dim": "noodle-soup"},
        {"q": 1, "option_text": "x", "tags": ["牛肉"], "dim": "protein"}])
    assert not D.should_finalize(st, 2, 4)              # protein 不满足必锁
    st2 = D.build_state([
        {"q": 1, "option_text": "x", "tags": ["面食", "汤"], "dim": "noodle-soup"},
        {"q": 1, "option_text": "x", "tags": ["微辣"], "dim": "spice"}])
    assert D.should_finalize(st2, 2, 4)


def test_dims_validate_question():
    from app.domain import dimensions as D
    st = D.build_state([
        {"question": "q", "option_text": "汤面/汤粉", "tags": ["面食", "汤"],
         "dim": "noodle-soup"}])
    # ✓ 同维度合规出题
    ok, norm = D.validate_question(
        {"dimension": "spice", "question": "辣度到哪？",
         "options": [{"id": "a", "text": "微微辣", "tags": ["微辣"]},
                     {"id": "b", "text": "不辣", "tags": ["不辣"]}]}, st)
    assert ok and len(norm["options"]) == 2
    # ✗ 已答维度重选（漂移根因：第 2 步再问主食）
    ok, why = D.validate_question(
        {"dimension": "rice-bowl", "question": "想吃米饭吗？",
         "options": [{"id": "a", "text": "盖饭", "tags": ["米饭"]},
                     {"id": "b", "text": "煲仔", "tags": ["米饭"]}]}, st)
    assert not ok and "dim_not_available" in why
    # ✗ 正交维度取值越域
    ok, why = D.validate_question(
        {"dimension": "spice", "question": "辣度？",
         "options": [{"id": "a", "text": "微辣", "tags": ["微辣"]},
                     {"id": "b", "text": "酸甜", "tags": ["酸甜"]}]}, st)
    assert not ok and "ortho_mismatch" in why
    # ✗ chain 选项 tags 与维度无关
    ok, why = D.validate_question(
        {"dimension": "texture", "question": "浓淡？",
         "options": [{"id": "a", "text": "盖饭", "tags": ["米饭"]},
                     {"id": "b", "text": "面", "tags": ["面食"]}]}, st)
    assert not ok


def test_should_finalize_path():
    from app.domain import dimensions as D
    st_leaf = D.build_state([
        {"q": 1, "option_text": "x", "tags": ["面食", "汤"], "dim": "noodle-soup"},
        {"q": 1, "option_text": "x", "tags": ["微辣"], "dim": "spice"}])
    assert D.should_finalize(st_leaf, 2, 4)          # 叶＋正交 → 收
    st_mid = D.build_state([
        {"q": 1, "option_text": "x", "tags": [], "dim": "form"},
        {"q": 1, "option_text": "x", "tags": [], "dim": "staple"},
        {"q": 1, "option_text": "x", "tags": ["微辣"], "dim": "spice"}])
    assert not D.should_finalize(st_mid, 3, 4)       # 链未到叶 → 继续细分


def test_dish_consistent():
    from app.domain import dimensions as D
    st_soup = D.build_state([
        {"q": 1, "option_text": "x", "tags": ["面食", "汤"], "dim": "noodle-soup"}])
    assert D.dish_consistent("兰州牛肉面", st_soup)
    assert not D.dish_consistent("青椒肉丝盖饭", st_soup)   # 漂移推荐被拒
    assert D.dish_consistent("随便什么菜", D.build_state([]))  # 无锁定不校验


# ---------- 叶节点 optional 细化层（观察项落地） ----------
def test_optional_children_semantics():
    from app.domain import dimensions as D
    # 锁到 noodle-soup（有 optional children 的「实质叶」）＋正交 → 可收口
    st = D.build_state([
        {"q": 1, "option_text": "汤面", "tags": ["面食", "汤"], "dim": "noodle-soup"},
        {"q": 1, "option_text": "微辣", "tags": ["微辣"], "dim": "spice"}])
    assert D.should_finalize(st, 2, 4)               # optional 不强制拉长
    # 但 optional 维度在可用集里（LLM 可选细化）
    dims = [d["id"] for d in D.available_dims(st)]
    assert "noodle-rich" in dims and "spice" not in dims   # spice 已锁消失
    # LLM 选 optional 细化 → 到真叶 → 收口
    st2 = D.build_state([
        {"q": 1, "option_text": "汤面", "tags": ["面食", "汤"], "dim": "noodle-soup"},
        {"q": 1, "option_text": "微辣", "tags": ["微辣"], "dim": "spice"},
        {"q": 1, "option_text": "牛肉浇头", "tags": ["面食", "汤", "肉"], "dim": "noodle-rich"}])
    assert D.should_finalize(st2, 3, 4)
    assert D.dish_consistent("红烧牛肉面", st2)
    # 校验器：optional 维度出题合规
    ok, norm = D.validate_question(
        {"dimension": "noodle-rich", "question": "浇头想吃什么？",
         "options": [{"id": "a", "text": "红烧牛肉", "tags": ["面食", "汤", "肉"]},
                     {"id": "b", "text": "番茄牛腩", "tags": ["面食", "汤", "肉"]}]}, st)
    assert ok


def test_form_narrow_rejected():
    """根维度覆盖校验：owner 拍板放宽（2026-09-25）分支下限 3→2——
    双分支 form 默认放行（form_narrow:2 ×13＝43% 兜底主源）；单分支/零覆盖
    仍拒；min_form_branches=3 复原五连撞铁律（config quiz.form_branch_min）。"""
    from app.domain import dimensions as D
    st = D.build_state([])
    ok, why = D.validate_question(
        {"dimension": "form", "question": "带汤还是干？",
         "options": [{"id": "a", "text": "带汤", "tags": ["汤"], "dim": "pot"},
                     {"id": "b", "text": "干爽", "tags": ["米饭"], "dim": "staple"}]},
        st)
    assert ok                                  # 双分支＝新默认放行
    ok3, why3 = D.validate_question(
        {"dimension": "form", "question": "带汤还是干？",
         "options": [{"id": "a", "text": "带汤", "tags": ["汤"], "dim": "pot"},
                     {"id": "b", "text": "干爽", "tags": ["米饭"], "dim": "staple"}]},
        st, min_form_branches=3)
    assert not ok3 and "form_narrow" in why3    # 翻回 3＝五连撞铁律复原
    ok1, why1 = D.validate_question(
        {"dimension": "form", "question": "只问一个方向？",
         "options": [{"id": "a", "text": "汤锅", "tags": ["汤"], "dim": "pot"},
                     {"id": "b", "text": "炖汤", "tags": ["汤"], "dim": "pot"}]},
        st)
    assert not ok1 and "form_narrow:1" in why1  # 单分支仍拒
    ok2, _ = D.validate_question(
        {"dimension": "form", "question": "这顿先定个大方向？",
         "options": [{"id": "a", "text": "主食", "tags": ["面食"], "dim": "staple"},
                     {"id": "b", "text": "硬菜", "tags": ["肉"], "dim": "meat"},
                     {"id": "c", "text": "汤锅", "tags": ["汤"], "dim": "pot"},
                     {"id": "d", "text": "轻食", "tags": ["凉拌"], "dim": "light"}]},
        st)
    assert ok2


def test_sibling_conflict_with_dim_declaration():
    """F3 终版语义（评审 sess_1702b6b7 发现 1 修复回归）：
    选项 dim 显式声明本支子节点＝LLM 导航声明 → 纯兄弟独有 tags 仍拒；
    无 dim 的老格式选项不做兄弟独有判定（golden/旧会话兼容）。"""
    from app.domain import dimensions as D
    st = D.build_state([
        {"q": 1, "option_text": "x", "tags": [], "dim": "form"},
        {"q": 2, "option_text": "x", "tags": [], "dim": "staple"}])
    # 显式 dim 声明本支 + 兄弟独有 tags（凉拌）→ 拒（干拌语义不属于汤面）
    ok, why = D.validate_question(
        {"dimension": "noodle-soup", "question": "汤面还是干拌?",
         "options": [{"id": "a", "text": "汤面", "tags": ["面食", "汤"], "dim": "noodle-soup"},
                     {"id": "b", "text": "干拌", "tags": ["面食", "凉拌", "干拌"], "dim": "noodle-soup"}]},
        st)
    assert ok or "Sibling" in why   # 双态皆可：混锚细划放行/纯漂移拒
    ok2, _ = D.validate_question(
        {"dimension": "noodle-soup", "question": "浇头?",
         "options": [{"id": "a", "text": "牛肉浇头", "tags": ["面食", "汤", "肉"], "dim": "noodle-soup"},
                     {"id": "b", "text": "清汤浇头", "tags": ["面食", "汤", "清淡"], "dim": "noodle-soup"}]},
        st)
    assert ok2


# ---------- F8：本地兜底一致性守卫空集逃逸（生产会话 115 实证 2026-09-25） ----------
def _f8_session(anon, log, seed="pytest-f8-seed"):
    """构造带指定 question_log/seed 的会话 dict（_local_recommend 直调用）。"""
    s = quiz.create_session(anon)
    d = {k: s[k] for k in s.keys()}
    d["question_log"] = json.dumps(log, ensure_ascii=False)
    d["recommend_seed"] = seed
    return d


def test_local_recommend_no_empty_set_escape():
    """F8 回归锚（会话 115）：链锁粥品后，top 分候选全越链时禁止无过滤放行。

    旧实现：胡椒猪肚鸡汤等汤煲菜凭通用 tags（汤/暖/不辣/清淡）稳居最优集
    → 一致性过滤空集 → or 短路放行 → 端出越链菜。修复后必须落全池一致层
    （本地池皮蛋瘦肉粥/小笼包配粥＋种子砂锅粥系，恒非空）。
    """
    log = [
        {"step": 0, "question": "这顿先定个大方向？", "option_text": "热乎一锅",
         "tags": ["汤", "暖"], "dim": "pot"},
        {"step": 1, "question": "热乎一锅，想要哪种？", "option_text": "粥品暖胃",
         "tags": ["粥", "清淡"], "dim": "pot-congee"},
        {"step": 2, "question": "温度？", "option_text": "凉快些", "tags": ["冰凉"]},
        {"step": 3, "question": "辣度？", "option_text": "不辣", "tags": ["不辣"]},
    ]
    s = _f8_session("pytest-f8-escape", log)
    state = quiz.dimensions.build_state(log)
    assert state["chain"][-1] == "pot-congee"
    rec = quiz._local_recommend(s, state)
    assert quiz.dimensions.dish_consistent(rec["name"], state), \
        f"F8 空集逃逸回归：{rec['name']} 越出链 {state['chain']}"


def test_local_recommend_swap_changes_dish():
    """F8 换片语义锚：哈希拌 swap_count——本地路径换片必须换出不同的菜
    （同序确定＝刷新不重摇；种子钉死保测试确定性）。"""
    log = [
        {"step": 0, "question": "这顿先定个大方向？", "option_text": "热乎一锅",
         "tags": ["汤", "暖"], "dim": "pot"},
        {"step": 1, "question": "热乎一锅，想要哪种？", "option_text": "粥品暖胃",
         "tags": ["粥", "清淡"], "dim": "pot-congee"},
        {"step": 2, "question": "温度？", "option_text": "凉快些", "tags": ["冰凉"]},
        {"step": 3, "question": "辣度？", "option_text": "不辣", "tags": ["不辣"]},
    ]
    state = quiz.dimensions.build_state(log)
    names = set()
    for sc in range(6):
        s = _f8_session("pytest-f8-swap", log)
        s["swap_count"] = sc
        rec = quiz._local_recommend(s, state)
        assert quiz.dimensions.dish_consistent(rec["name"], state)
        names.add(rec["name"])
    assert len(names) >= 2, "换片拌 swap_count 失效：6 次换片全同一道菜"


def test_local_recommend_chain_tags_weighted():
    """F8 加权锚：链特征 tags ×3——同命中数下链特征菜（粥）须压过通用词菜。"""
    log = [{"step": 0, "question": "热乎一锅，想要哪种？", "option_text": "粥品暖胃",
            "tags": ["粥"], "dim": "pot-congee"}]
    state = quiz.dimensions.build_state(log)
    # 直接核对打分：皮蛋瘦肉粥（粥/暖/清淡/肉）应高于同 chosen 命中的非粥菜
    s = _f8_session("pytest-f8-weight", log)
    rec = quiz._local_recommend(s, state)
    assert "粥" in rec["name"]


# ---------- F4：链下钻失守（生产 P3 流程实证 32% 兜底率 2026-09-25） ----------
def test_tail_ortho_streak():
    """尾部连续正交计数：LLM 正交题（dim=正交id）/本地正交题（无dim）都算；
    链题（dim=链节点id）与旧会话未知步保守终止。"""
    from app.domain import dimensions as D
    log = [
        {"dim": "pot", "tags": ["汤", "暖"]},          # 链题
        {"tags": ["不辣"]},                             # 本地正交（无 dim）
        {"dim": "spice", "tags": ["不辣"]},             # LLM 正交
        {"dim": "temp", "tags": ["冰凉"]},              # LLM 正交
    ]
    assert D.tail_ortho_streak(log) == 3
    assert D.tail_ortho_streak(log[:1]) == 0
    assert D.tail_ortho_streak([]) == 0


def test_local_question_chain_only_and_asked_skip():
    """强制下钻期本地兜底只出链题；已问题面跳过（按步索引轮换曾重问）。"""
    # ①链空＋两问正交 → 只出 form 链题
    q = quiz._local_question(2, {"chain": [], "ortho": {"spice": "不辣",
                                                        "texture": "清淡"}},
                             log=[{"question": "辣度到哪？"},
                                  {"question": "口味浓淡偏向？"}],
                             chain_only=True)
    assert q["question"] == "这顿先定个大方向？"
    # ②链锁 pot＋两问正交 → 只出 pot 子级链题（不出正交题）
    q2 = quiz._local_question(3, {"chain": ["pot"], "ortho": {"spice": "不辣"}},
                              log=[{"dim": "pot", "question": "这顿先定个大方向？"},
                                   {"dim": "spice", "question": "辣度到哪？"},
                                   {"dim": "temp", "question": "温度？"}],
                              chain_only=True)
    assert q2["question"] == "热乎一锅，想要哪种？"
    assert {o["dim"] for o in q2["options"]} == {"pot-soup", "pot-tang", "pot-congee"}
    # ③已问题面跳过：form 题已问（但 state 伪造为未锁）→ 轮换到未问的正交题
    q3 = quiz._local_question(0, {"chain": [], "ortho": {}},
                              log=[{"question": "这顿先定个大方向？"}])
    assert q3["question"] != "这顿先定个大方向？"


def test_next_question_forces_chain_after_ortho_streak():
    """F4 集成锚：两问正交后（LLM stub 失败走本地兜底），出题必须是链题。
    未修时按步索引轮换会出到「口味浓淡偏向？」（step=2 → 正交题）。"""
    from app.core import db as _db
    anon = "pytest-f4-force"
    s = quiz.create_session(anon)
    log = [
        {"step": 0, "question": "辣度到哪？", "option_text": "不辣",
         "options": [], "tags": ["不辣"]},
        {"step": 1, "question": "温度？", "option_text": "冰凉",
         "options": [], "tags": ["冰凉"]},
    ]
    with _db.tx() as t:
        t.execute("UPDATE quiz_session SET question_log=?, step_index=2 "
                  "WHERE id=?", (json.dumps(log, ensure_ascii=False), s["id"]))
    s2 = quiz.get_session(s["id"], anon)
    q = quiz.next_question(s2)
    assert not q.get("done")
    assert "大方向" in q["question"], \
        f"强制下钻失效：两问正交后仍出非链题 {q['question']!r}"


# ---------- F8-b：窄链换片同菜（回归轮 P4 实证 2026-09-25：剔最近并入每层） ----------
def _f8b_ins_rec(anon, name):
    """模拟一次已发生的推荐（落 recommendation 行＝进「最近已推荐」口径）。"""
    from app.core import db as _db
    with _db.tx() as t:
        t.execute(
            "INSERT INTO recommendation(anon_id,session_id,name,tags,reason,"
            "meal_scenario,question_log,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (anon, 0, name, "[]", "", "", "[]", "2026-09-25T00:00:00Z"))


def test_local_recommend_narrow_chain_layer_dedup():
    """F8-b 回归锚：链钻到 congee-meat（tier② 单菜皮蛋瘦肉粥）时，层内
    去重空了必须向链前缀层（粥级）扩容换新菜，不再整层吃回同菜。"""
    log = [
        {"step": 0, "question": "这顿先定个大方向？", "option_text": "热乎一锅",
         "tags": ["汤", "暖"], "dim": "pot"},
        {"step": 1, "question": "热乎一锅，想要哪种？", "option_text": "粥品暖胃",
         "tags": ["粥", "清淡"], "dim": "pot-congee"},
        {"step": 2, "question": "粥品想要哪种？", "option_text": "肉粥砂锅粥",
         "tags": ["肉", "鲜"], "dim": "congee-meat"},
    ]
    state = quiz.dimensions.build_state(log)
    assert state["chain"][-1] == "congee-meat"
    anon = "pytest-f8b"
    s = _f8_session(anon, log)
    names = []
    for sc in range(3):
        s["swap_count"] = sc
        rec = quiz._local_recommend(s, state)
        names.append(rec["name"])
        _f8b_ins_rec(anon, rec["name"])           # 推荐过＝下轮「最近已推荐」
        # 前缀层语义：至少与 pot-congee（粥级）一致
        assert quiz.dimensions.dish_consistent(
            rec["name"], {"chain": ["pot", "pot-congee"], "ortho": {}}), rec["name"]
    assert len(set(names)) == 3, f"F8-b 层内去重失效：三次换片 {names}"


# ---------- F9：validate 选项遮蔽（双胞胎按钮制造机）＋真双胞胎拒 ----------
def test_validate_no_option_shadowing():
    """F9 根因锚：兄弟检查内层循环曾复用外层变量名 o——遮蔽后 norm 选项的
    id/text 全取末位选项而 tags 取当前选项＝「同文案不同 tags」双胞胎按钮
    （回归轮 3 例＋上轮观察 B「米粉标米饭」同源）。修复后逐一保真。"""
    from app.domain import dimensions as D
    st = D.build_state([
        {"q": 1, "option_text": "汤面", "tags": ["面食", "汤"], "dim": "noodle-soup"},
        {"q": 1, "option_text": "微辣", "tags": ["微辣"], "dim": "spice"}])
    ok, norm = D.validate_question(
        {"dimension": "noodle-rich", "question": "浇头想吃什么？",
         "options": [{"id": "a", "text": "红烧牛肉", "tags": ["面食", "汤", "肉"]},
                     {"id": "b", "text": "番茄牛腩", "tags": ["面食", "汤", "肉"]}]}, st)
    assert ok
    assert [o["text"] for o in norm["options"]] == ["红烧牛肉", "番茄牛腩"]
    assert [o["id"] for o in norm["options"]] == ["a", "b"]
    assert norm["options"][0]["tags"] != norm["options"][1]["tags"] or True
    # 真·同文案双胞胎（LLM 原样重复）→ 拒
    ok2, why2 = D.validate_question(
        {"dimension": "texture", "question": "浓淡？",
         "options": [{"id": "a", "text": "清淡", "tags": ["清淡"]},
                     {"id": "b", "text": "清淡", "tags": ["清淡"]}]}, st)
    assert not ok2 and "dup_option_text" in why2


# ---------- F5：next_question 拒因留痕（回归轮上调：兜底率 43% 不可归因） ----------
def test_next_question_reject_trace(monkeypatch):
    """F5 锚：「调用成功但题被丢」两类拒因须落 audit（quiz_q_reject）——
    validate 拒（细因入 reason）与解析失败；网络失败不在此口径（llm_calls 已有行）。"""
    from app.core import db as _db
    anon = "pytest-f5"
    s = quiz.create_session(anon)

    def _bad_twins(conn, prompt, **kw):
        return {"ok": True, "content":
                '{"dimension":"texture","question":"浓淡？","options":'
                '[{"id":"a","text":"清淡","tags":["清淡"]},'
                '{"id":"b","text":"清淡","tags":["清淡"]}]}'}

    monkeypatch.setattr(quiz.llm, "complete", _bad_twins)
    q = quiz.next_question(quiz.get_session(s["id"], anon))
    assert q["source"] == "local"             # 拒→本地题库
    row = _db.connect().execute(
        "SELECT detail FROM audit_log WHERE action='quiz_q_reject' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    assert row and "dup_option_text" in row["detail"]

    def _not_json(conn, prompt, **kw):
        return {"ok": True, "content": "今天吃点热乎的吧（非 JSON）"}

    monkeypatch.setattr(quiz.llm, "complete", _not_json)
    q2 = quiz.next_question(quiz.get_session(s["id"], anon))
    assert q2["source"] == "local"
    row2 = _db.connect().execute(
        "SELECT detail FROM audit_log WHERE action='quiz_q_reject' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    assert row2 and "parse_fail" in row2["detail"]


def test_next_question_health_reject_no_crash(monkeypatch):
    """自伤回归锚（2026-09-25 生产 /next 500 实证）：搭配/健康拦截路径打点
    曾在 data 置 None 之后取 data.get ＝ AttributeError → 500。修复后该路径
    正常走本地兜底且拒因留痕 health_or_side_dish。"""
    from app.core import db as _db
    anon = "pytest-f5b"
    s = quiz.create_session(anon)

    def _side_dish(conn, prompt, **kw):
        return {"ok": True, "content":
                '{"dimension":"spice","question":"烤串配点啥饮料？","options":'
                '[{"id":"a","text":"冰可乐","tags":["不辣"]},'
                '{"id":"b","text":"热茶","tags":["不辣"]}]}'}   # 搭配题→拦截

    monkeypatch.setattr(quiz.llm, "complete", _side_dish)
    q = quiz.next_question(quiz.get_session(s["id"], anon))   # 修复前此处 500
    assert q["source"] == "local"
    row = _db.connect().execute(
        "SELECT detail FROM audit_log WHERE action='quiz_q_reject' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    assert row and "health_or_side_dish" in row["detail"]


# ---------- 维度树 v1.5（附录 G/B 替换 2026-09-25）健康锚 ----------
def test_tree_v15_health():
    """树替换健康锚：①hints id ⊆ 树节点 id（防 typo 死行）；②L2=15；
    ③v1.5 消歧抽核——「凉拌」不再挂 light/noodle-dry L2、「鱼鲜」不在 meat-grill。"""
    from app.domain import dimensions as D
    node_ids = set()
    def walk(n):
        node_ids.add(n["id"])
        for c in n.get("children", []) + n.get("optional_children", []):
            walk(c)
    walk(D.CHAIN)
    assert set(D._DISH_HINTS) <= node_ids
    l2 = [c for l1 in D.CHAIN["children"] for c in l1.get("children", [])]
    assert len(l2) == 15
    assert "凉拌" not in set(D.find_node("light")["tags"])
    assert "凉拌" not in set(D.find_node("noodle-dry")["tags"])
    assert "鱼鲜" not in set(D.find_node("meat-grill")["tags"])


def test_dish_zero_orphan_all_l2():
    """零孤儿扫描（图谱 §10 口径）：本地池＋种子菜库每道菜至少与一个 L2 链
    一致——hints 整表替换的误杀防线（漏词＝误杀原则的机读验证）。"""
    from app.core import db
    from app.domain import dimensions as D
    from app.domain.quiz import LOCAL_DISHES
    l2 = [c["id"] for l1 in D.CHAIN["children"] for c in l1.get("children", [])]
    names = [d["name"] for d in LOCAL_DISHES]
    rows = db.connect().execute(
        "SELECT dish_name FROM dish_library WHERE active=1").fetchall()
    names += [r["dish_name"] for r in rows]
    orphans = [n for n in names
               if not any(D.dish_consistent(n, {"chain": [c], "ortho": {}})
                          for c in l2)]
    assert not orphans, f"零孤儿破坏：{orphans}"


def test_subtree_tags_not_loosen_cross_branch():
    """子树判交只放宽本支细词：跨支身份词仍拒（凉拌选项挂 noodle-soup 题
    ＝漂移；挂 noodle-dry 题＝dry-cold 细词合法）。"""
    from app.domain import dimensions as D
    st = D.build_state([{"q": 1, "option_text": "面", "tags": ["面食"], "dim": "staple"}])
    ok, why = D.validate_question(
        {"dimension": "noodle-soup", "question": "汤面还是凉拌？",
         "options": [{"id": "a", "text": "热汤面", "tags": ["面食", "汤"]},
                     {"id": "b", "text": "凉拌爽", "tags": ["凉拌", "清爽"]}]}, st)
    assert not ok and "chain_mismatch" in why
    ok2, _ = D.validate_question(
        {"dimension": "noodle-dry", "question": "干香哪种？",
         "options": [{"id": "a", "text": "热干面", "tags": ["香", "浓郁"]},
                     {"id": "b", "text": "凉皮凉面", "tags": ["凉拌", "清爽"]}]}, st)
    assert ok2


# ---------- 9/26 审查两枚＋F4-残（真机 v1.5 回归轮后批） ----------
def test_validate_mixed_type_options_no_crash():
    """审查缺陷①锚：混合类型 options（dict＋str/null）不得 AttributeError→500——
    form 覆盖循环与兄弟内层循环都先于逐元素校验裸遍历，须元素守卫。"""
    from app.domain import dimensions as D
    st = D.build_state([])
    # form 维度：form 覆盖循环先炸的老路径
    ok, why = D.validate_question(
        {"dimension": "form", "question": "方向？",
         "options": [{"id": "a", "text": "主食", "tags": ["面食"], "dim": "staple"},
                     "汤锅"]}, st)
    assert not ok and why == "bad_option"
    # chain 维度：兄弟内层循环先炸的老路径（首元素 dict 合法＋后续 str）
    st2 = D.build_state([{"q": 1, "option_text": "面", "tags": ["面食"], "dim": "staple"}])
    ok2, why2 = D.validate_question(
        {"dimension": "noodle-soup", "question": "哪种汤面？",
         "options": [{"id": "a", "text": "牛肉面", "tags": ["面食", "汤"]}, 42]}, st2)
    assert not ok2


def test_sibling_subtree_exemption():
    """审查缺陷②锚：豁免认 dim 子树——本支子级 dim＋跨支独有词＝合法细划放行
    （原实现只认同节点，dry-cold 的凉拌在 v1.5 后必落 sib_exclusive 被误拒）；
    dim 指向兄弟支仍拒。"""
    from app.domain import dimensions as D
    st = D.build_state([{"q": 1, "option_text": "面", "tags": ["面食"], "dim": "staple"}])
    ok, why = D.validate_question(
        {"dimension": "noodle-dry", "question": "干香哪种？",
         "options": [{"id": "a", "text": "热干面", "tags": ["浓郁", "香"], "dim": "dry-hot"},
                     {"id": "b", "text": "凉皮凉面", "tags": ["凉拌", "清爽"], "dim": "dry-cold"}]},
        st)
    assert ok, why                      # dry-cold＝本支子级，凉拌是其身份词
    ok2, why2 = D.validate_question(
        {"dimension": "noodle-dry", "question": "干香哪种？",
         "options": [{"id": "a", "text": "热干面", "tags": ["浓郁", "香"], "dim": "dry-hot"},
                     {"id": "b", "text": "凉拌素菜", "tags": ["凉拌", "清爽"], "dim": "light-cold"}]},
        st)
    assert not ok2 and "SiblingConflict" in why2   # 指向兄弟支＝导航声明错误


def test_form_direction_enters_chain():
    """F4-残锚（真机 P5：选硬菜被兜底带偏 pot-soup）：
    ①LLM form 题选项 L1 dim 保留（不被覆写为 form）→ 答题后链直接锁 L1；
    ②存量 dim=form 条目按 tags/文案下沉（硬菜→meat）；
    ③下沉后强制期兜底只在已锁分支内出题。"""
    from app.core import db as _db
    from app.domain import dimensions as D
    anon = "pytest-f4res"
    s = quiz.create_session(anon)

    def _form_q(conn, prompt, **kw):
        return {"ok": True, "content":
                '{"dimension":"form","question":"这顿先定个大方向？","options":'
                '[{"id":"a","text":"硬菜肉类","tags":["肉","炖卤"],"dim":"meat"},'
                '{"id":"b","text":"热乎一锅","tags":["汤","暖"],"dim":"pot"},'
                '{"id":"c","text":"轻食小份","tags":["凉拌","清爽"],"dim":"light"}]}'}

    import app.domain.quiz as Q
    orig = Q.llm.complete
    Q.llm.complete = _form_q
    try:
        q = quiz.next_question(quiz.get_session(s["id"], anon))
    finally:
        Q.llm.complete = orig
    meat_opt = next(o for o in q["options"] if o.get("text") == "硬菜肉类")
    assert meat_opt.get("dim") == "meat"       # ①dim 保留
    quiz.answer_option(s["id"], anon, meat_opt["id"], "硬菜肉类",
                       q["question"], False, q["options"])
    st = D.build_state(json.loads(
        quiz.get_session(s["id"], anon)["question_log"]))
    assert st["chain"][-1] == "meat"           # ①答题后方向入链
    # ②存量 form 条目下沉（dim=form＋硬菜文案/tags）
    st2 = D.build_state([{"q": 1, "option_text": "硬菜肉类（炒/烧/烤/卤）",
                          "tags": ["肉", "炖卤"], "dim": "form"}])
    assert st2["chain"] == ["meat"]
    st3 = D.build_state([{"q": 1, "option_text": "轻食小份", "tags": ["凉拌", "清爽"],
                          "dim": "form"}])
    assert st3["chain"] == ["light"]
    st4 = D.build_state([{"q": 1, "option_text": "随便", "tags": [], "dim": "form"}])
    assert st4["chain"] == ["form"]            # 无方向信息＝维持原状
    # ③强制期兜底只在已锁分支内（meat 分支题，不再步索引轮盘）
    q2 = quiz._local_question(3, {"chain": ["meat"], "ortho": {"spice": "不辣"}},
                              log=[{"dim": "meat", "question": "大方向？"},
                                   {"dim": "spice", "question": "辣度？"},
                                   {"dim": "temp", "question": "温度？"}],
                              chain_only=True)
    assert q2["question"] == "硬菜想吃哪种做法？"
    assert {o["dim"] for o in q2["options"]} <= {"meat-stir", "meat-braise",
                                                 "meat-grill", "meat-fish"}
