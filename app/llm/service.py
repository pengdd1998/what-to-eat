"""LLM 适配器（X1/U2 未决的占位实现，T1.4/T1.5 共用）。

供应商配置驱动：config["llm"] = {"provider": "stub"|"openai_compatible", ...}。
- stub / 未配置 / 缺 API key / 超预算 → 返回 None，调用方走降级链（池/菜库）——
  功能降级可用、单列观测，不算不可用（§1.1）。
- openai_compatible：HTTP 构造/超时/重试/JSONL 留痕已收口 app/llm_gateway.py
  （全仓唯一模型调用出口）；本模块保留 prompt、熔断与 llm_calls 表留痕
  （key 仅服务端环境变量，SUP-02 禁入前端/入库/入 git）。
双熔断（SUP-03）：日调用数 / 日费用两阈值（config，U2 定稿后收紧）——超限本日
不再发起实时调用并写 audit。PIPL（§4.2）：实时路径仅传脱敏上下文（标签＋匿名
摘要＋日轮换假名，不传 anon_id 原文）。
"""
import json
import os
import time
from datetime import datetime, timezone

from ..core import db   # 相对导入统一（评审观察项2）
from . import gateway as llm_gateway

SOFT_TIMEOUT_S = 3.0   # P95 ≤3s 预算（评审 #7）
HARD_TIMEOUT_S = 6.0   # 硬超时（§1.1；HTTP 执行在 llm_gateway，总预算同值）


def _load_dotenv() -> None:
    """极简 .env 加载（KEY=VALUE，忽略注释；文件 gitignored，SUP-02）。"""
    path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _over_circuit(conn, cfg: dict) -> str:
    """返回熔断原因或空串（日口径，llm_calls 表计数）。"""
    day = _today()
    calls = conn.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(cost_usd),0) cost FROM llm_calls "
        "WHERE substr(ts,1,10)=? AND status!='blocked'", (day,)).fetchone()
    if calls["c"] >= cfg.get("daily_call_cap", 200):
        return f"daily_call_cap:{cfg.get('daily_call_cap')}"
    if calls["cost"] >= cfg.get("daily_cost_cap_usd", 1.5):
        return f"daily_cost_cap:{cfg.get('daily_cost_cap_usd')}"
    return ""


def log_call(conn, vendor: str, scene: str, latency_ms: int, cost: float,
             status: str, tokens=None, *, task=None, error_class=None,
             attempts=None, model=None) -> None:
    """llm_calls 写入（自带短事务；2026-09-16 升公共——batch 直连网关路径
    亦须落库，否则看板成本口径系统性低估）。

    W-1 重构后本函数可能在**不持有 db.tx** 的上下文被调用（推荐已出锁），
    必须自带事务满足 R-03；禁止在已持有 db.tx 的调用方使用（锁不可重入）。
    task/error_class/attempts＝监控三列（0007）；model＝实际模型名（0008）。
    P1 修复（评审 R1 实锤）：签名曾缺 model 形参而 generate/batch 调用点已传
    → 周一批产 TypeError 崩溃、batch_runs 卡 running、model 列 0 写入。
    """
    with db.tx() as c:
        c.execute(
            "INSERT INTO llm_calls(ts,vendor,scene,latency_ms,tokens_in,tokens_out,"
            "cost_usd,status,task,error_class,attempts,model) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(timespec="milliseconds"), vendor,
             scene, latency_ms, tokens[0] if tokens else None,
             tokens[1] if tokens else None, cost, status,
             task, error_class, attempts, model))


def _resolve_cfg(conn) -> dict:
    """config['llm'] ＋ env 凭证合成解析结果（provider/model/base_url/api_key）。"""
    cfg = (json.loads(conn.execute(
        "SELECT value FROM config WHERE key='llm'").fetchone()[0])
        if conn.execute("SELECT 1 FROM config WHERE key='llm'").fetchone() else {})
    provider = cfg.get("provider", "stub")
    base_url = os.environ.get("LLM_BASE_URL", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = cfg.get("model") or os.environ.get("LLM_MODEL", "")
    return {"provider": provider, "cfg": cfg, "base_url": base_url,
            "api_key": api_key, "model": model}


def _fail(reason: str, latency_ms: int = 0, error_class=None) -> dict:
    return {"ok": False, "content": None, "latency_ms": latency_ms,
            "error_class": error_class, "reason": reason}


def _audit_circuit(reason: str) -> None:
    """熔断审计＋当日首次 P2 通知（P0-2：两段式——tx 内判首次写 audit、tx 外发 notify）。"""
    from ..core.audit import audit
    from ..core.notify import notify
    first_today = False
    with db.tx() as c:
        n = c.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action='llm_circuit_break' "
            "AND substr(ts,1,10)=?", (_today(),)).fetchone()[0]
        first_today = (n == 0)
        audit(c, "system:api", "llm_circuit_break", reason, {"day": _today()})
    if first_today:                # 当日去重：只首次触发通知（持锁外做网络 IO）
        notify("P2: LLM 日熔断已触发（%s），今日实时调用关闭、本地兜底生效" % reason,
               "", "P2")


def complete(conn, prompt: str, *, scene: str = "adhoc", agent: str = "app",
              task: str = None) -> dict:
    """通用单轮调用（复刻工程移植——自适应问答/收口引擎共用）。

    返回 {"ok","content","latency_ms","error_class","reason"}，任何失败不抛异常。
    task＝监控粒度（next_question|finalize|...，llm-monitoring-plan §3），
    缺省回落 scene 值（老口径兼容）。
    """
    r = _resolve_cfg(conn)
    cfg = r["cfg"]
    if r["provider"] != "openai_compatible":
        return _fail("provider_stub")
    reason = _over_circuit(conn, cfg)
    if reason:
        _audit_circuit(reason)
        return _fail(reason)
    base_url, api_key, model = r["base_url"], r["api_key"], r["model"]
    if not (base_url and api_key and model):
        return _fail("unconfigured")
    _task = task or scene
    res = llm_gateway.call(
        agent, _task, prompt, model=model, route="primary",
        params={"temperature": cfg.get("temperature", 0.7),
                "disable_thinking": cfg.get("disable_thinking", True)})
    if not res["ok"]:
        log_call(conn, r["provider"], scene, res["latency_ms"], 0.0, "error",
                  task=_task, error_class=res.get("error_class"),
                  attempts=res.get("attempts"), model=model)
        return _fail("call_failed", res["latency_ms"], res.get("error_class"))
    log_call(conn, r["provider"], scene, res["latency_ms"],
              cfg.get("cost_per_call_usd", 0.01), "ok",
              tokens=(res["input_tokens"], res["output_tokens"]),
              task=_task, attempts=res.get("attempts"), model=model)
    return {"ok": True, "content": res["content"],
            "latency_ms": res["latency_ms"], "error_class": None, "reason": ""}


def generate_recommendation(conn, ctx: dict):
    """A 形态冷启动实时生成（脱敏上下文）。返回 dict 或 None（降级）。

    ctx: {"tonight_tags": [...], "flavor_summary": str, "daily_alias": str}
    """
    r = _resolve_cfg(conn)                     # 阶段4：撤本函数内重复的 cfg 解析
    cfg, provider = r["cfg"], r["provider"]
    if provider == "stub":
        return None  # U2 未定稿：占位＝不可用，走降级链
    reason = _over_circuit(conn, cfg)
    if reason:
        _audit_circuit(reason)
        return None
    if not (r["base_url"] and r["api_key"] and r["model"]):
        return None
    prompt = (
        "你是晚餐推荐助手。根据今晚口味标签推荐恰好一道菜。"
        f"今晚标签：{'、'.join(ctx['tonight_tags']) or '无'}。"
        f"用户口味摘要（匿名）：{ctx['flavor_summary']}。"
        "只输出 JSON：{\"dish_name\":str,\"dish_slug\":str,\"copy\":str}，"
        "copy 一句情绪化推荐语；禁止健康/减脂/营养建议。")
    res = llm_gateway.call(
        "app.strategy", "cold_start", prompt, model=r["model"], route="primary",
        params={"temperature": cfg.get("temperature", 0.7),
                "disable_thinking": cfg.get("disable_thinking", True)})
    if not res["ok"]:
        _log_call(conn, provider, "cold_start", res["latency_ms"], 0.0, "error",
                  model=r["model"])
        return None
    _log_call(conn, provider, "cold_start", res["latency_ms"],
              cfg.get("cost_per_call_usd", 0.01), "ok",
              tokens=(res["input_tokens"], res["output_tokens"]),
              model=r["model"])
    content = res["content"]
    # 模型可能带 ```json 围栏或前后杂讯——截取首个 { 到末个 } 再解析（PoC-4 实测）
    s, e = content.find("{"), content.rfind("}")
    if s < 0 or e <= s:
        # 与原实现同语义：ok 行已落，解析失败再落 error 行（熔断计数含 error）
        _log_call(conn, provider, "cold_start", res["latency_ms"], 0.0, "error",
                  model=r["model"])
        return None
    try:
        return json.loads(content[s:e + 1])
    except ValueError:
        _log_call(conn, provider, "cold_start", res["latency_ms"], 0.0, "error",
                  model=r["model"])
        return None


_log_call = log_call   # 兼容别名（2026-09-16 公共化）


def ping() -> dict:
    """LLM 三路由连通性检测（monitoring-workbench-plan §5.1，拍板 #3）。

    只落 audit（action=llm_ping）不落 llm_calls——绕开 scene CHECK＋天然
    不计熔断/月成本。走网关既有超时/重试/JSONL 留痕。
    """
    import os as _os
    from ..core import audit as _audit_mod
    from ..llm import gateway as _gw
    routes = {
        "primary": (None, _os.environ.get("LLM_MODEL", "")),
        "glm": ("GLM_BASE_URL", _os.environ.get("GLM_MODEL", "")),
        "qwen": ("QWEN_BASE_URL", _os.environ.get("QWEN_MODEL", "")),
    }
    out = {}
    for route, (_, model) in routes.items():
        if not model:
            out[route] = {"ok": False, "error_class": "route_unconfigured",
                          "latency_ms": 0}
            continue
        t0 = time.monotonic()
        res = _gw.call("app.admin", "ping", "回复 ok", model=model, route=route,
                       params={"temperature": 0.0, "max_tokens": 8})
        out[route] = {"ok": bool(res["ok"]),
                      "latency_ms": res.get("latency_ms") or int((time.monotonic() - t0) * 1000),
                      "error_class": res.get("error_class")}
    with db.tx() as c:
        from ..core.audit import audit as _a
        _a(c, "system:admin", "llm_ping", "routes", out)
    return out
