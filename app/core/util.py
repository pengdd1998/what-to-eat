"""core/util——通用工具单源（阶段3重组：原 5 处 now_iso / 双 JSON 提取统一）。"""
import json
from datetime import datetime, timezone


def now_iso() -> str:
    """UTC ISO 时间戳（存储/事件口径；业务判断时钟用 providers.env_ctx.cn_now）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def extract_json(text: str):
    """从可能带 ```json 围栏/前后杂讯的 LLM 输出里截取首个 { 到末个 } 并解析。"""
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
