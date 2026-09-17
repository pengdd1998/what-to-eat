"""内存滑动窗限流（§4.1 SUP-03；D-4：单机内存实现，刷量时升级）。"""
import threading
import time
from collections import OrderedDict, deque

_lock = threading.Lock()
_windows: "OrderedDict[str, deque]" = OrderedDict()
_calls = 0
_SWEEP_EVERY = 4096        # 每 N 次调用做一次全量清扫（W-15：消无界增长）


def _sweep(now: float, window_s: float) -> None:
    """丢弃空窗口/整体过期的键（被丢弃键下次访问重建＝计数重置，可接受）。"""
    for k in [k for k, q in _windows.items() if not q or now - q[-1] > window_s]:
        del _windows[k]


def allow(key: str, limit: int, window_s: float = 60.0) -> bool:
    global _calls
    now = time.monotonic()
    with _lock:
        q = _windows.setdefault(key, deque())
        while q and now - q[0] > window_s:
            q.popleft()
        _calls += 1
        if _calls % _SWEEP_EVERY == 0:
            _sweep(now, window_s)
        if len(q) >= limit:
            return False
        q.append(now)
        return True
