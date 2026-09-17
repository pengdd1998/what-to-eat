#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端冒烟（落地方案 §3.2 发布步骤 2 的本地子集；T0.2→T1.x 扩展）。

链路：health → 冷启动会话（3 次换一档）→ 换一至耗尽（护栏 3 口径）
     → accept → /go 302 ＋ jump token 幂等（经 Admin export 验证计数）
     → 负反馈/弃答兜底 → 口令 set/recover → Admin 三道闸（含回滚）
仅标准库；SMOKE_BASE_URL / SMOKE_ADMIN_URL / SMOKE_ADMIN_TOKEN 可覆盖。
"""
import csv
import io
import json
import os
import sys
import urllib.error
import urllib.request
import subprocess as _sp

BASE = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8100")
ADMIN = os.environ.get("SMOKE_ADMIN_URL", "http://127.0.0.1:8103")
ADMIN_TOKEN = os.environ.get(
    "SMOKE_ADMIN_TOKEN",
    "smoke-admin-token-0123456789abcdef0123456789abcdef")
FAILS = []


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 不跟随 302，让上层读到状态码与 Location


opener = urllib.request.build_opener(NoRedirect)


def call(method, path, body=None, base=None, token=None, anon=None):
    req = urllib.request.Request((base or BASE) + path, method=method)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if anon:
        req.add_header("X-Anon-Id", anon)
    try:
        with opener.open(req, data, timeout=10) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            raw = resp.read() or b"{}"
            try:
                return resp.status, headers, json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                return resp.status, headers, {"_raw": raw.decode(errors="replace")[:2048]}
    except urllib.error.HTTPError as e:
        raw = e.read() or b"{}"
        headers = {k.lower(): v for k, v in e.headers.items()}
        try:
            return e.code, headers, json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return e.code, headers, {"_raw": raw.decode(errors="replace")[:2048]}


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILS.append(name)


import uuid
RUN = uuid.uuid4().hex[:6]  # 每次运行独立匿名段——冒烟可重复打在持久库上不互相污染


def uniq(prefix):
    return f"{prefix}{RUN}"


def quiz_flow(anon, max_steps=8):
    """quiz 链全流程（阶段2冒烟迁移）：session→next/answer 循环→finalize。

    返回 (sid, finalize 响应)。answer 后按 should_stop 提前收口（画像充分用户 3 步）。
    漏斗纪律（2026-09-15）：每问断言不属搭配维度（饮料/配菜/加料/收尾）。
    """
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app.domain.quiz import _is_side_dish_question as _side
    from app.domain import dimensions as _D
    st, _, qs = call("POST", "/api/quiz/session", anon=anon)
    assert st == 200, qs
    sid = qs["session_id"]
    _log = []
    for _ in range(max_steps):
        st, _, q = call("GET", f"/api/quiz/{sid}/next", anon=anon)
        assert st == 200, q
        assert not _side(q.get("question", "")), f"搭配类问题漏拦: {q.get('question')}"
        if q.get("done"):
            break
        # 漏斗断言：出题维度必须在可用维度集内（防已答维度重问＝漂移回归）
        _state = _D.build_state(_log)
        _dims = {d["id"] for d in _D.available_dims(_state)}
        assert q.get("source") != "llm" or q.get("options") and (
            not q["options"][0].get("dim") or q["options"][0]["dim"] in _dims), \
            f"维度越界: {q.get('options',[{}])[0].get('dim')} ∉ {_dims}"
        opts = q.get("options") or [{"id": "opt0", "text": ""}]
        st, _, _a = call("POST", f"/api/quiz/{sid}/answer",
                         {"option_id": opts[0]["id"],
                          "option_text": opts[0].get("text", ""),
                          "question": q.get("question", ""),
                          "all_options": opts}, anon=anon)
        assert st == 200, _a
        _log.append({"question": q.get("question", ""),
                     "option_text": opts[0].get("text", ""),
                     "tags": opts[0].get("tags") or [],
                     "dim": opts[0].get("dim") or ""})
        if q.get("should_stop"):
            break
    st, _, fin = call("POST", f"/api/quiz/{sid}/finalize", anon=anon)
    assert st == 200, fin
    return sid, fin


def admin_export(table):
    req = urllib.request.Request(f"{ADMIN}/api/admin/export?table={table}")
    req.add_header("Authorization", f"Bearer {ADMIN_TOKEN}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.read().decode()


def main():
    print(f"== 冒烟 @ {BASE}（admin @ {ADMIN}）==")

    print("[1] health")
    st, _, body = call("GET", "/api/health")
    check("health 200", st == 200)
    check("db_writable", body.get("db_writable") is True)
    check("form 字段存在", "form" in body)

    print("[2] quiz 链主流程：bootstrap→session→问答→finalize（新用户全链）")
    anon1 = uniq("smokequiz")
    st, _, b = call("POST", "/api/identity/bootstrap", anon=anon1)
    check("bootstrap 200 返回身份", st == 200 and b.get("anon_id") == anon1)
    sid, fin = quiz_flow(anon1)
    check("finalize 菜名非空", bool(fin.get("name")))
    check("dish_slug 保留（中文可作深链搜索词）", bool(fin.get("dish_slug")))
    check("go_token 在位（北极星跳板）", bool(fin.get("go_token")))

    print("[3] 再帮我想一个＝新会话（口径变化：原换一上限/re-ask 断言随旧链移除——"
          "quiz 链无服务端次数限制，浏览护栏由产品文案承担，见迭代日志）")
    st, _, qs2 = call("POST", "/api/quiz/session", anon=anon1)
    check("新一轮返回新会话 id", st == 200 and qs2["session_id"] != sid)

    print("[4] accept→/go 302＋jump 幂等（北极星双事件）")
    st, _, acc = call("POST", f"/api/quiz/{sid}/accept",
                      {"dish_slug": fin["dish_slug"]}, anon=anon1)
    check("accept 200 有 token", st == 200 and acc.get("go_token"))
    token = acc["go_token"]
    # token 含中文 slug（2026-09-15 中文修复）：浏览器自动百分号编码，urllib 需显式 quote
    import urllib.parse as _up
    _go = "/go/" + _up.quote(token, safe="")
    st1, h1, _ = call("GET", _go)
    st2, h2, _ = call("GET", _go)
    check("两次 /go 均 302", st1 == 302 and st2 == 302)
    check("Location 含搜索词", "keyword=" in h1.get("location", ""))
    st, _, body = call("GET", "/go/bad.token.here.x")
    check("坏 token 404", st == 404)
    st, raw = admin_export("events")
    rows = list(csv.DictReader(io.StringIO(raw)))
    sess_row = f"sess_quiz_{sid}"
    jumps = [r for r in rows if r["type"] == "jump" and r["session_id"] == sess_row]
    check("jump 事件仅 1 条（幂等）", len(jumps) == 1, f"n={len(jumps)}")
    accs = [r for r in rows if r["type"] == "accept" and r["session_id"] == sess_row]
    check("accept 事件已落库（北极星分子）", len(accs) == 1, f"n={len(accs)}")
    served = [r for r in rows
              if r["type"] == "result_served" and r["session_id"] == sess_row]
    check("result_served source 合法（llm/local——降级可用不算故障）",
          len(served) == 1 and '"source"' in served[0]["payload"])

    print("[5] 味觉记忆（口径变化：原 negative/abandon 断言随旧链移除——"
          "quiz 链负反馈走记忆页三值反馈，弃答＝用户直接离开，见迭代日志）")
    st, _, mem = call("GET", "/api/memory", anon=anon1)
    items = mem.get("items") or []
    check("记忆含本轮推荐（带答题路径回放）",
          len(items) >= 1 and bool(items[0].get("question_log")))
    st, _, _b = call("POST", f"/api/memory/{items[0]['id']}/feedback",
                     {"score": -1}, anon=anon1)
    check("负反馈（不推荐 -1）200", st == 200)

    print("[6] 口令（FR-11）")
    anon = uniq("smokeid")
    st, _, body = call("POST", "/api/identity/passcode",
                       {"action": "set", "anon_id": anon, "passcode": "123456"})
    check("弱口令(纯数字) 422", st == 422)
    st, _, body = call("POST", "/api/identity/passcode",
                       {"action": "set", "anon_id": anon, "passcode": "qingdan-Tang7"})
    check("合格口令 set 204", st == 204)
    st, _, body = call("POST", "/api/identity/passcode",
                       {"action": "recover", "anon_id": anon, "passcode": "wrong-x9"})
    check("错口令 403", st == 403)
    st, _, body = call("POST", "/api/identity/passcode",
                       {"action": "recover", "anon_id": anon,
                        "passcode": "qingdan-Tang7"})
    check("对口令恢复 anon_id", st == 200 and body.get("anon_id") == anon)
    st, _, body = call("POST", "/api/identity/passcode",
                       {"action": "recover", "passcode": "qingdan-Tang7"})
    check("recover 无 anon_id 422（W-2 扫描面收敛）",
          st == 422 and "anon_id" in str(body))

    print("[6.5] cron 日结指标（P1-3：P95＋月累计）")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app.cron import cost_close
    cc = cost_close()
    check("cost_close 含 llm_p95_ms", "llm_p95_ms" in cc)
    check("cost_close 含 llm_month_cost_usd", "llm_month_cost_usd" in cc)
    check("cost_close 含监控 9 项（plan §3.4）",
          "llm_success_rate" in cc and "quiz_question_llm_rate" in cc)
    # 阶段3②教训入烟：crontab 走 `python -m app.cron`，包执行须有 __main__.py；
    # 遍历读任务（aggregate 在冒烟库已有数据→隐藏依赖漏 import 能被抓到）
    _cron_ok = True
    for _t in ("aggregate", "cost_close"):
        _rc = _sp.run([sys.executable, "-m", "app.cron", _t],
                      capture_output=True, text=True, timeout=60, cwd=os.path.join(
                          os.path.dirname(__file__), ".."))
        if _rc.returncode != 0 or not _rc.stdout.strip().startswith("{"):
            _cron_ok = False
            print(f"    cron -m {_t} 失败: {_rc.stderr[-200:]}")
    check("python -m app.cron aggregate/cost_close 可执行（crontab 路径）", _cron_ok)

    print("[7] 回访探针未启用")
    st, _, body = call("POST", "/api/visit-report",
                       {"anon_id": "smokeid000001", "answer": "satisfied"})
    check("visit-report 404（未启用）", st == 404)

    print("[8] Admin 三道闸（内网面）＋LLM 看板")
    st, _, body = call("GET", "/api/admin/config", base=ADMIN)
    check("无 token 401", st == 401)
    st, _, body = call("GET", "/api/admin/config", base=ADMIN, token=ADMIN_TOKEN)
    check("带 token 读 config", st == 200 and "form" in body.get("config", {}))
    st, _, body = call("POST", "/api/admin/config",
                       {"key": "form", "value": "X"}, base=ADMIN, token=ADMIN_TOKEN)
    check("闸1 拒非法值 422", st == 422)
    st, _, body = call("POST", "/api/admin/config",
                       {"key": "form", "value": "C"}, base=ADMIN, token=ADMIN_TOKEN)
    check("form=C 写入成功", st == 200)
    _sid_c, fin_c = quiz_flow(uniq("smokeformc"))
    check("form=C 下 quiz 链仍出结果（阶段2口径：公共面不再按 form 分叉）",
          bool(fin_c.get("name")))
    st, _, body = call("POST", "/api/admin/config",
                       {"key": "form", "value": "undecided"},
                       base=ADMIN, token=ADMIN_TOKEN)
    check("form 还原 undecided", st == 200)
    # LLM 看板（plan §4 P1）：Basic 无凭据 401 带 WWW-Authenticate；带凭据 200 含 SVG
    req = urllib.request.Request(f"{ADMIN}/admin/llm?days=7")
    try:
        urllib.request.urlopen(req, timeout=10)
        st_dash = 200
    except urllib.error.HTTPError as e:
        st_dash = e.code
        dash_www = e.headers.get("WWW-Authenticate", "")
    check("看板无凭据 401＋WWW-Authenticate", st_dash == 401 and "Basic" in dash_www)
    import base64 as _b64a
    req = urllib.request.Request(f"{ADMIN}/admin/llm?days=7")
    req.add_header("Authorization", "Basic " + _b64a.b64encode(
        f"owner:{ADMIN_TOKEN}".encode()).decode())
    dash_html = urllib.request.urlopen(req, timeout=10).read().decode()
    check("看板带凭据 200 含 SVG/概览", "<svg" in dash_html and "LLM 能力看板" in dash_html)
    st, _, ov = call("GET", "/api/admin/llm/overview?days=7", base=ADMIN,
                     token=ADMIN_TOKEN)
    check("overview JSON 键齐全", st == 200 and
          all(k in ov for k in ("trend", "card", "detail", "audit")))

    print("[9] 页面与静态资源（版本漂移教训：页面必须进冒烟）")
    st, _, page = call("GET", "/")
    check("首页 200 含隐私弹窗", st == 200 and "privacy" in str(page))
    full = urllib.request.urlopen(BASE + "/").read().decode()  # 完整 HTML（call 会截断 2048）
    # V-1 结果播报：ark 形态（screen-result+assertive）或旧形态（result+polite）均认
    import re as _re
    check("结果区 aria-live（V-1）",
          bool(_re.search(r'id="(screen-)?result"', full))
          and "aria-live" in full)
    st, raw = admin_export("audit_log")
    if os.environ.get("SMOKE_EXPECT_DEV_FALLBACK"):   # 仅本地 dev 兜底场景（smoke_local.sh 不注入 GO_SECRET）
        fb_rows = [r for r in csv.DictReader(io.StringIO(raw))
                   if r["action"] == "insecure_secret_fallback"]
        check("密钥守卫告警已 audit（V-4，dev 场景）", len(fb_rows) >= 1,
              f"n={len(fb_rows)}")
    else:
        check("密钥守卫不误报（生产有强密钥，无告警行）",
              all(r["action"] != "insecure_secret_fallback"
                  for r in csv.DictReader(io.StringIO(raw))))
    st, _, page = call("GET", "/identity")
    check("身份页 200", st == 200)
    st, _, page = call("GET", "/memory")
    check("味觉记忆页 200（footnav 三 tab 齐活）",
          st == 200 and "味觉记忆" in str(page.get("_raw", "")))
    raw_home = urllib.request.urlopen(BASE + "/", timeout=10).read().decode()
    check("结果屏跳板按钮在位（btn-accept→北极星 accept/jump）",
          "btn-accept" in raw_home)
    # [11] 环境上下文（预取注入：场景时钟/隐式画像/降级链——2026-09-15 方案落地；
    #     直接 import 断言——原 base64 子进程段已展开，包结构变更时同步导入行即可）
    from datetime import datetime as _dt
    from app.providers import env_ctx as _env
    from app.domain import quiz as _quiz
    from app.core import db as _db
    _db.init_schema()
    _scene_cases = [("06:30", "早餐"), ("12:30", "午餐"), ("13:45", "下午茶"),
                    ("20:30", "晚餐"), ("21:00", "宵夜"), ("01:00", "宵夜")]
    _scene_ok = True
    for _hm, _w in _scene_cases:
        _h, _m = map(int, _hm.split(":"))
        _got = _env.scene(_dt(2026, 9, 15, _h, _m, tzinfo=_env.CN_TZ))["name"]
        if _got != _w:
            _scene_ok = False
            print(f"    场景断言失败: {_hm} → {_got}（期望 {_w}）")
    check("环境上下文：场景时钟边界×6（[11]）", _scene_ok)
    check("环境上下文：内网 IP/无城市天气降级（[11]）",
          _env.city("192.168.1.4") is None and _env.weather(None) is None)
    with _db.tx() as _t:
        _t.execute(
            "INSERT INTO recommendation(anon_id,session_id,name,tags,reason,"
            "meal_scenario,question_log,created_at) VALUES(?,?,?,?,?,?,?,?)",
            ("anon_smoke_env1", 1, "测试菜", "[]", "", "午餐",
             '[{"question":"汤干?","option_text":"热汤面"}]',
             "2026-09-15T04:00:00+00:00"))
    _ts = _quiz.taste_summary("anon_smoke_env1")
    check("环境上下文：隐式画像聚合（[11]）",
          "热汤面" in _ts["liked"] and _ts["count"] == 1 and not _ts["profiled"])
    st, _, _b = call("GET", "/static/app.js")
    check("app.js 200", st == 200)
    st, _, _b = call("GET", "/static/marker.html")
    check("marker.html 200（T0.6）", st == 200)
    st, _, _b = call("GET", "/static/manifest.webmanifest")
    check("PWA manifest 200", st == 200)
    st, _, _b = call("GET", "/static/icons/icon-192.png")
    check("PWA icon 200", st == 200)

    print("[10] health 收尾")
    st, _, body = call("GET", "/api/health")
    check("health 仍绿", st == 200 and body.get("db_writable") is True)

    print(f"== 结果：{'全绿' if not FAILS else f'{len(FAILS)} 项失败: {FAILS}'} ==")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
