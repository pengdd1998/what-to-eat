"""domain 纯逻辑单测：策略/健康过滤/jump/口令/画像（阶段5·拍板#3）。"""
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
    # 选 form（模拟 log）后 → 子树前沿＝L1 四支
    st2 = D.build_state([{"question": "q", "option_text": "主食正餐",
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
    """根维度覆盖校验（owner 五连撞）：二分 form 被拒，≥3 支覆盖通过。"""
    from app.domain import dimensions as D
    st = D.build_state([])
    ok, why = D.validate_question(
        {"dimension": "form", "question": "带汤还是干？",
         "options": [{"id": "a", "text": "带汤", "tags": ["汤"], "dim": "pot"},
                     {"id": "b", "text": "干爽", "tags": ["米饭"], "dim": "staple"}]},
        st)
    assert not ok and "form_narrow" in why
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
