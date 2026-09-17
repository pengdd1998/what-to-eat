"""埋点事件白名单（FR-15 全集，T1.6）。

事件权威＝SQLite events 表（§2.2），server_ts 为唯一判读时钟（SUP-06）。
SERVER_ONLY：仅服务端写入（前端 batch 提交会被拒，防口径污染）。
"""
from typing import FrozenSet

# T0.2 骨架期白名单：会话起点 / 答题 / 结果呈现。
# T1.6 补齐 FR-15 全集：弃答步位、接受/拒绝/换一（含耗尽标记）、跳转双事件
# （accept 侧＋jump 侧）、链接失效、回访曝光与应答、假门漏斗、推荐曝光标识。
SERVER_ONLY: FrozenSet[str] = frozenset({
    "session_start",      # 会话起点
    "answer",             # 逐题作答（/answer 端点权威记录；禁前端 batch 重复上报）
    "result_served",      # 结果呈现（含 source 与 attempt）
    "accept",             # 北极星第一事件：点击「就吃这个」（服务端记）
    "jump",               # 北极星第二事件：/go/{token} 302 触发（token 哈希幂等）
    "swap",               # 换一（服务端计数）
    "swap_exhausted",     # 达换一上限仍未收口（护栏 3 口径）
    "re_ask",             # 再问一轮（服务端计数；上限 1 次/会话，工程审查 V-3）
    "re_ask_exhausted",   # 再问超限（同 swap_exhausted 留痕语义）
    "abandon",            # 弃答（含步位）
    "fallback_result",    # 弃答兜底直给
})

CLIENT_ALLOWED: FrozenSet[str] = frozenset({
    "negative_feedback",            # 负反馈按钮
    "link_dead",                    # 深链失效标记（前端探知）
    "visit_probe_show",             # 回访曝光（抽样 ≤1 次/人/周）
    "visit_report",                 # 回访应答（满意/不满意；M3 起含自报下单）
    "fakedoor_show",                # 假门曝光（M3）
    "fakedoor_click",               # 假门点击
    "fakedoor_register",            # 假门登记完成（零联系字段）
    "recommend_exposure",           # 推荐曝光内容标识（7 日去重口径）
})

ALLOWED_EVENT_TYPES: FrozenSet[str] = frozenset(SERVER_ONLY | CLIENT_ALLOWED)
