"""环境上下文（预取注入架构，provider 插件化）——2026-09-15 方案落地。

每个 provider＝纯函数，返回 dict 或 None（None＝该维度不可用，prompt 该段标「无」）。
环境信息在调用前完全可知（静态可枚举），故服务端预取＋单次注入，不采用 LLM tools
（每步双往返：时延×2＋费用×1.5~2 无信息增益，评估见迭代日志 2026-09-15）。

**本模块无用户身份维度**：anon_id 永不传入；taste/recent 属用户数据域，由 quiz.py 拼装。
隐私（口径变更 owner 已确认 2026-09-15）：IP 仅服务端即时查询市级归属，不落库不进
audit/日志；city 只作天气缓存键，不与任何用户标识关联存储；不获取 GPS 精确定位。

缓存/降级（AGENTS.md 降级链是产品原则）：
- 天气 L1 进程缓存 TTL `env.ttl_min`；失败负缓存 `env.neg_cache_min`（防超时重击）。
- IP 非公网/库缺失/城市不在坐标表/天气超时 → None → prompt「无」，主流程不受影响。
"""
import json
import os
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from ..core import db
from . import ipsearch

CN_TZ = timezone(timedelta(hours=8))     # 中国无夏令时，产品服务大陆用户，+8 显式绑定


def cn_now() -> datetime:
    """业务判断时钟（场景/日历/假名日期）——与容器本地时区解耦（修复中午判宵夜事故）。"""
    return datetime.now(CN_TZ)


# ---------- scene：时段场景（边界 config.scenes，支持跨午夜） ----------
SCENES_DEFAULT = {
    "早餐": [6, 10], "午餐": [10, 13.5], "下午茶": [13.5, 17],
    "晚餐": [17, 21], "宵夜": [21, 30],   # 30＝次日 6 点（跨午夜左闭右开）
}


def scene(now: datetime = None) -> dict:
    dt = now or cn_now()
    h = dt.hour + dt.minute / 60.0
    for name, pair in db.get_config("scenes", SCENES_DEFAULT).items():
        lo, hi = pair
        if lo <= hi:
            if lo <= h < hi:
                return {"name": name}
        elif h >= lo or h < hi:          # 跨午夜区间（hi 以 24+ 小时表示时不会走到）
            return {"name": name}
    return {"name": "宵夜"}


# ---------- calendar：工作日/周末（决策时间预算不同） ----------
def calendar(now: datetime = None) -> dict:
    dt = now or cn_now()
    return {"is_weekend": dt.weekday() >= 5}


# ---------- city：IP→市级归属（ip2region 离线库，进程内常驻） ----------
_SEARCHER = None
_SEARCHER_LOCK = threading.Lock()


def _searcher():
    global _SEARCHER
    if _SEARCHER is None:
        with _SEARCHER_LOCK:
            if _SEARCHER is None:
                path = os.environ.get("WTE_IP2REGION_XDB", "/app/ip2region.xdb")
                if not os.path.exists(path):
                    return None
                try:
                    buff = ipsearch.XdbSearcher.loadContentFromFile(dbfile=path)
                    _SEARCHER = ipsearch.XdbSearcher(contentBuff=buff)
                except Exception:
                    return None
    return _SEARCHER


def city(ip: str) -> "dict | None":
    """IP→{city}。内网/海外/解析失败→None。市名去掉「市」后缀以便查坐标表。"""
    s = _searcher()
    if not s or not ip:
        return None
    try:
        raw = s.search(ip)
    except Exception:
        return None
    if not raw:
        return None
    parts = (raw.split("|") + [""] * 5)[:5]
    name = (parts[3] or "").replace("市", "").strip()
    if not name or name == "0":
        return None
    return {"city": name}


# ---------- weather：Open-Meteo 免费源 → 档位化提示（不注原始 JSON，控 token） ----------
ENV_DEFAULTS = {"weather_enabled": True, "ttl_min": 60, "timeout_s": 1.5,
                "neg_cache_min": 10}

CITY_COORDS = {
    "北京": (39.90, 116.41), "上海": (31.23, 121.47), "广州": (23.13, 113.26),
    "深圳": (22.54, 114.06), "杭州": (30.27, 120.16), "南京": (32.06, 118.80),
    "苏州": (31.30, 120.58), "成都": (30.57, 104.07), "重庆": (29.56, 106.55),
    "武汉": (30.59, 114.31), "西安": (34.34, 108.94), "长沙": (28.23, 112.94),
    "郑州": (34.75, 113.63), "天津": (39.08, 117.20), "合肥": (31.82, 117.23),
    "福州": (26.07, 119.30), "厦门": (24.48, 118.09), "南昌": (28.68, 115.86),
    "济南": (36.65, 117.12), "青岛": (36.07, 120.38), "太原": (37.87, 112.55),
    "石家庄": (38.04, 114.51), "哈尔滨": (45.80, 126.53), "长春": (43.82, 125.32),
    "沈阳": (41.80, 123.43), "大连": (38.91, 121.61), "昆明": (25.04, 102.71),
    "贵阳": (26.65, 106.63), "南宁": (22.82, 108.32), "海口": (20.04, 110.32),
    "三亚": (18.25, 109.51), "兰州": (36.06, 103.83), "西宁": (36.62, 101.78),
    "银川": (38.49, 106.23), "乌鲁木齐": (43.83, 87.62), "呼和浩特": (40.84, 111.75),
    "无锡": (31.49, 120.31), "宁波": (29.87, 121.54), "温州": (28.00, 120.67),
    "东莞": (23.02, 113.75), "佛山": (23.02, 113.12), "珠海": (22.27, 113.58),
    "泉州": (24.87, 118.68), "绍兴": (30.03, 120.58), "嘉兴": (30.75, 120.76),
    "常州": (31.81, 119.97), "烟台": (37.46, 121.45), "洛阳": (34.62, 112.45),
}
_RAINY = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}
_SNOWY = {71, 73, 75, 77, 85, 86}

_weather_cache = {}                       # city -> (ts, hint|None)；None＝负缓存
_WLOCK = threading.Lock()


def _env_cfg() -> dict:
    return db.get_config("env", ENV_DEFAULTS)


def weather(city_info) -> "dict | None":
    cfg = _env_cfg()
    if not city_info or not cfg.get("weather_enabled", True):
        return None
    name = city_info.get("city")
    coord = CITY_COORDS.get(name)
    if not coord:
        return None
    now_ts = time.time()
    with _WLOCK:
        hit = _weather_cache.get(name)
        if hit and now_ts - hit[0] < cfg.get("ttl_min", 60) * 60:
            return {"hint": hit[1]} if hit[1] else None
    hint = _fetch_weather_hint(coord, cfg)          # 网络调用在锁外，持锁只碰缓存
    with _WLOCK:
        _weather_cache[name] = (now_ts, hint)
    return {"hint": hint} if hint else None


def _fetch_weather_hint(coord, cfg: dict):
    """当前温度＋WMO 天气代码 → 一句档位提示；常规天气返回 None（不注入）。"""
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={coord[0]}&longitude={coord[1]}"
           f"&current=temperature_2m,weather_code&timezone=auto")
    try:
        with urllib.request.urlopen(url, timeout=cfg.get("timeout_s", 1.5)) as r:
            cur = (json.loads(r.read().decode()) or {}).get("current", {})
        t = float(cur.get("temperature_2m", 25.0))
        code = int(cur.get("weather_code", 0))
    except Exception:
        return None
    if code in _SNOWY:
        return "正下雪，特别适合热乎带汤的（炖菜/汤面/火锅类）"
    if code in _RAINY:
        return "在下雨，热汤面/粥粉类会很舒服，少生冷"
    if t >= 28:
        return "天气炎热，想吃点清爽凉的（凉面/冷食/清淡口味）"
    if t <= 0:
        return "天很冷，想吃热乎的（热汤/炖菜/暖胃的）"
    if t < 10:
        return "天气偏冷，想吃点热乎带汤的"
    return None


def warm_weather(client_ip: str) -> None:
    """session 创建时后台预热（异常全吞，绝不影响主流程）。"""
    try:
        weather(city(client_ip or ""))
    except Exception:
        pass


def snapshot(client_ip: str = "") -> dict:
    """环境快照（纯环境、无身份维度）。scene/calendar 恒可用，其余可 None。"""
    now = cn_now()
    c = city(client_ip or "")
    return {
        "scene": scene(now),
        "calendar": calendar(now),
        "weather": weather(c),
        "city": c,
    }
