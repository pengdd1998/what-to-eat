"""302 跳板（RSK-3 默认解；T1.7）——HMAC 无状态 go_token，不落库、事件即档案。

语义（§1.1/§2.2）：
- POST /accept 记 accept 事件（server_ts）→ 返回 go_token（TTL 10 分钟 [假设]）
- GET /go/{token} 记 jump 事件，以 token 哈希为幂等键、首个 jump 生效
  （刷新/群转发不重复计数——北极星不可被无意识刷高，v3.1 评审 13）
- 北极星双事件 60 秒窗口＝两事件 server_ts 差（服务端时钟，SUP-06）
"""
import hashlib
import hmac
import os
import time

SECRET = os.environ["GO_SECRET"] if os.environ.get("GO_SECRET") else \
    "dev-only-insecure-secret"  # 生产由环境变量注入 ≥32 字节随机值（SUP-02）
TTL_SECONDS = 600


def make_token(session_id: str, dish_slug: str, ts: int = None) -> str:
    ts = int(ts if ts is not None else time.time())
    body = f"{session_id}.{dish_slug}.{ts}"
    sig = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def verify_token(token: str):
    """返回 (session_id, dish_slug, ts) 或 None（签名不符/过期/格式错）。"""
    parts = token.split(".")
    if len(parts) != 4:
        return None
    session_id, dish_slug, ts_str, sig = parts
    try:
        ts = int(ts_str)
    except ValueError:
        return None
    body = f"{session_id}.{dish_slug}.{ts_str}"
    expect = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expect):
        return None
    if time.time() - ts > TTL_SECONDS:
        return None
    return session_id, dish_slug, ts


def token_fingerprint(token: str) -> str:
    """幂等键：token 哈希（events.client_event_id，首 jump 生效）。"""
    return "jump_" + hashlib.sha256(token.encode()).hexdigest()[:40]
