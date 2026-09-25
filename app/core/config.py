"""core/config——配置缺省单源·静态部分（2026-09-16 观察项1 修复）。

只持**无跨层依赖**的纯静态键（form/swap_limits/links/llm 等）——
memory/scenes/env 等依赖 domain/providers 的值由 web/support 层组装
（组装引用 domain/providers 合法；core 保持零业务依赖红线）。
cron 等非 web 消费方直接引本模块（消 cron→web 跨层引用）。
"""

STATIC_DEFAULTS = {
    "form": "undecided",                       # ADR-003 终裁（W1 D6）后翻转
    "config_version": "t1.x",
    "swap_limits": {"cold": 3, "steady": 2},   # FR-04
    "cold_start_threshold": 5,                 # FR-05 有效偏好信号 <5 次
    # 环境上下文（预取注入 2026-09-15）：场景边界支持跨午夜（hi 以 24+ 小时表示）
    # 画像收敛加速：count≥threshold 时收口下限放宽到 min_steps_profiled（P2）；
    # min_steps 5→4＝owner 拍板观察期（2026-09-15 漏斗收敛改造）
    "quiz": {"profile_threshold": 3, "min_steps": 4, "min_steps_profiled": 3,
               "form_branch_min": 2},   # form 首题大方向分支下限（9/25 owner 放宽 3→2）
    "llm": {"provider": "openai_compatible",      # 主供＝qwen（2026-09-04 owner 拍板"文本模型选用qwen"，ADR-004 修订；MiMo 降第二，env 备选位保留）
            "model": "qwen3.8-flash",
            "temperature": 0.7,
            "disable_thinking": True,              # 关思维链是 ≤3s 硬前提（PoC-4）；参数方言由 llm_gateway 按厂商分派
            "cost_per_call_usd": 0.01,             # [假设·保守] 待控制台实测校准
            "daily_call_cap": 200,                 # 熔断阈值待 PoC-4 后校准（SUP-03）
            "daily_cost_cap_usd": 1.5},
    "links": {"status": "assumed_ok",          # 探活 cron 自动翻转（T1.7）
              "default_platform": "meituan",
              # 深链模板 [假设]——PoC-3 真机验证前不得视为已验证
              "templates": {"meituan":
                            "https://h5.waimai.meituan.com/waimai/mindex/search"
                            "?keyword={kw}"}},
    "visit_probe": {"enabled": False, "probability": 0.3},  # M2 起启用
    "fakedoor": {"enabled": False, "anchor_x": None},       # M3 起启用（FR-17 诚实假门；锚点 X 待 U3）
    # ---- 前端题目内容（config 驱动，热更通道；FR-01/02/08） ----
    "profile_questions": [
        {"text": "口味轻重？", "choices": ["清淡为主", "有味才爽", "看心情"]},
        {"text": "汤水偏好？", "choices": ["爱喝汤", "干香为主", "都行"]},
        {"text": "辣度？", "choices": ["不吃辣", "微辣", "无辣不欢"]},
    ],
    "quiz_q2": {"text": "今天状态更接近？", "choices": ["累，要快", "想犒劳自己"]},
    "umami": {"base_url": None, "website_id": None, "batch": 100, "cursor": 0},
}
