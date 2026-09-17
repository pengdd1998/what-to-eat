"""LLM 网关——全仓唯一的模型调用出口（收口改造 批1，2026-09-05）。

职责边界：本模块只管「怎么调用」——路由解析（route→环境变量对）、请求构造、
超时预算、重试、错误分类与 JSONL 留痕；prompt 内容与业务降级决策归调用方
（app/llm.py），熔断与 llm_calls 表留痕也在调用方（ADR-004 / 迭代日志语义）。

- 唯一入口 call(agent, task, prompt, *, model, route, params)：任何模块要调
  模型一律走这里；禁止在别处再构造 chat/completions 请求或 SDK 客户端。
- 路由表：primary=LLM_BASE_URL/LLM_API_KEY（主供小米 MiMo，ADR-004）；
  glm/qwen=对照备选（仅在显式传对应 route 时才读取对应环境变量；主供切换
  拍板权归人，本模块永不做自动切换）。
- 超时/重试：单次逻辑调用总预算 6s（＝原 llm.py 硬超时，禁放大）；限流/5xx/
  瞬时网络错且剩余预算足够时重试 1 次；超时/解析失败/内容过滤/其余 4xx 不重试。
- 失败不抛异常：一律返回 ok=False 的结果 dict，由调用方走降级链（菜库兜底，
  「功能降级可用」，§1.1）。
- 密钥红线（SUP-02/PIPL）：api_key 只用于构造 Authorization 头，禁入日志/
  返回值/代码字面量；prompt 不落盘，只记 sha256 前 16 位（prompt_hash）；
  error_detail 只记脱敏类别码，禁带响应体原文。

JSONL 留痕（本地文件，不引入观测平台 SDK）：每次 HTTP 尝试一行，路径默认
logs/llm-gateway-<UTC日期>.jsonl（WTE_LLM_LOG_PATH 覆盖整路径）；写日志失败
不影响调用。schema 字段缺一不可：
  timestamp | agent | task | prompt_hash | model | params | input_tokens |
  output_tokens | latency_ms | success | error_class
  error_class 固定枚举：超时/限流/内容过滤/解析失败/未知（成功时为 null）；
  附加字段 request_id/attempt/error_detail 用于关联重试与定位（均为脱敏码）。
"""
import hashlib
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

HARD_DEADLINE_S = 6.0     # 单次逻辑调用总预算（原 llm.py 硬超时 §1.1）
MIN_RETRY_BUDGET_S = 1.0  # 剩余预算低于此值不发起重试（防预算击穿）
MAX_ATTEMPTS = 2          # 首次＋至多 1 次重试（实时路径 P95 ≤3s 不允许更多）

ROUTES = {  # 路由键 → (base_url 环境变量, api_key 环境变量)
    "primary": ("LLM_BASE_URL", "LLM_API_KEY"),
    "glm": ("GLM_BASE_URL", "GLM_API_KEY"),     # 对照备选（AGENTS.md）
    "qwen": ("QWEN_BASE_URL", "QWEN_API_KEY"),  # 切换建议在案待拍板，禁自动启用
}

# error_class 固定枚举（收口任务红线：只用这五个值）
EC_TIMEOUT = "超时"
EC_RATE_LIMIT = "限流"
EC_CONTENT_FILTER = "内容过滤"
EC_PARSE = "解析失败"
EC_UNKNOWN = "未知"

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_log_lock = threading.Lock()


class _ContentFilter(Exception):
    """200 响应内嵌 error.code=content_filter 的哨兵异常（仅分类用）。"""


def _log_path() -> str:
    override = os.environ.get("WTE_LLM_LOG_PATH", "")
    if override:
        return override
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return os.path.join(_REPO_ROOT, "logs", f"llm-gateway-{day}.jsonl")


def _append_jsonl(record: dict) -> None:
    """单行追加写；任何失败静默吞掉——观测不给主链路添故障。"""
    try:
        line = json.dumps(record, ensure_ascii=False)
        with _log_lock:
            os.makedirs(os.path.dirname(_log_path()), exist_ok=True)
            with open(_log_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        pass


def _classify(e: Exception):
    """异常 → (error_class, 脱敏 detail, 可否重试)。"""
    if isinstance(e, _ContentFilter):
        return EC_CONTENT_FILTER, "resp_content_filter", False
    if isinstance(e, urllib.error.HTTPError):
        body = b""
        try:
            body = e.read(2048)  # 只用于分类，不落日志（脱敏）
        except Exception:
            pass
        text = body.decode("utf-8", "ignore").lower()
        if e.code == 429:
            return EC_RATE_LIMIT, "http_429", True
        if "content_filter" in text or "content filter" in text:
            return EC_CONTENT_FILTER, f"http_{e.code}_content_filter", False
        if e.code >= 500:
            return EC_UNKNOWN, f"http_{e.code}", True
        return EC_UNKNOWN, f"http_{e.code}", False
    if isinstance(e, urllib.error.URLError):
        reason = getattr(e, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return EC_TIMEOUT, "urlerror_timeout", False
        return EC_UNKNOWN, "urlerror_" + type(reason).__name__, True
    if isinstance(e, (TimeoutError, socket.timeout)):
        return EC_TIMEOUT, "socket_timeout", False
    if isinstance(e, (ValueError, KeyError, IndexError, TypeError)):
        return EC_PARSE, type(e).__name__, False
    return EC_UNKNOWN, type(e).__name__, False


def _record(rid: str, attempt: int, agent: str, task: str, prompt: str,
            model: str, route: str, params: dict, timeout_s: float,
            in_tok, out_tok, latency_ms: int, success: bool,
            error_class, error_detail) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "agent": agent,
        "task": task,
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
        "model": model,
        "params": {**params, "route": route, "attempt": attempt,
                   "max_attempts": MAX_ATTEMPTS, "timeout_s": round(timeout_s, 2)},
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "latency_ms": latency_ms,
        "success": success,
        "error_class": error_class,
        "request_id": rid,
        "error_detail": error_detail,
    }


def call(agent: str, task: str, prompt: str, *, model: str,
         route: str = "primary", params: dict = None) -> dict:
    """唯一入口。返回 dict：ok/content/input_tokens/output_tokens/latency_ms/
    attempts/error_class/error_detail；失败不抛异常（调用方走降级链）。"""
    params = dict(params or {})
    rid = uuid.uuid4().hex[:12]
    t0 = time.monotonic()
    env_pair = ROUTES.get(route)
    base_url = os.environ.get(env_pair[0], "") if env_pair else ""
    api_key = os.environ.get(env_pair[1], "") if env_pair else ""
    if not (base_url and api_key and model):
        # 路由未配置＝网关拒绝发起，记一行留痕（不算模型调用，token 为空）
        rec = _record(rid, 0, agent, task, prompt, model, route, params, 0.0,
                      None, None, 0, False, EC_UNKNOWN, "route_unconfigured")
        _append_jsonl(rec)
        return {"ok": False, "content": None, "input_tokens": None,
                "output_tokens": None, "latency_ms": 0, "attempts": 0,
                "error_class": EC_UNKNOWN, "error_detail": "route_unconfigured"}
    # 关思维链是实时路径硬前提（ADR-004/PoC-4），但参数是厂商方言：
    # qwen → enable_thinking:false；MiMo/其余 → thinking.type=disabled
    if params.get("disable_thinking", True):
        no_think = ({"enable_thinking": False} if model.startswith("qwen")
                    else {"thinking": {"type": "disabled"}})
    else:
        no_think = {}
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": params.get("temperature", 0.7),
        **no_think,
    }).encode()
    url = base_url.rstrip("/") + "/chat/completions"
    attempt = 0
    while True:
        attempt += 1
        timeout_s = max(0.5, HARD_DEADLINE_S - (time.monotonic() - t0))
        t1 = time.monotonic()
        ok, retryable = False, False
        err_cls = err_detail = None
        content, in_tok, out_tok = None, None, None
        try:
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {api_key}")
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read())
            if isinstance(data, dict) and data.get("error"):
                # 200 但内嵌 error 体：content_filter 哨兵，其余交给下方取键失败分类
                if "content_filter" in json.dumps(data["error"]).lower():
                    raise _ContentFilter()
            content = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage") or {}
            in_tok = usage.get("prompt_tokens")
            out_tok = usage.get("completion_tokens")
            ok = True
        except Exception as e:
            err_cls, err_detail, retryable = _classify(e)
        latency_ms = int((time.monotonic() - t1) * 1000)
        _append_jsonl(_record(rid, attempt, agent, task, prompt, model, route,
                              params, timeout_s, in_tok, out_tok, latency_ms,
                              ok, err_cls, err_detail))
        if ok:
            return {"ok": True, "content": content, "input_tokens": in_tok,
                    "output_tokens": out_tok, "latency_ms": latency_ms,
                    "attempts": attempt, "error_class": None,
                    "error_detail": None}
        if (retryable and attempt < MAX_ATTEMPTS and
                HARD_DEADLINE_S - (time.monotonic() - t0) >= MIN_RETRY_BUDGET_S):
            continue
        return {"ok": False, "content": None, "input_tokens": None,
                "output_tokens": None,
                "latency_ms": int((time.monotonic() - t0) * 1000),
                "attempts": attempt, "error_class": err_cls,
                "error_detail": err_detail}
