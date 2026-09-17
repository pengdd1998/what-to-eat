# app/AGENTS.md — 代码区细则（L1 模块级）

> 基座 v1.0 · 2026-09-04 · 只收根级 AGENTS.md 没有的代码区规则；溯源见 `docs/reverse/rule-placement.md`

## 分层与入口（2026-09-15 阶段3重组后）
- 六包结构：`core/`（db/ratelimit/events/umami/util/audit，基础设施）→ `llm/`（gateway=唯一 HTTP 出口＋service）→ `providers/`（env_ctx/ipsearch 环境上下文）→ `domain/`（strategy/quiz/memory/identity/jump 纯逻辑）→ `web/`（pages/schemas/support/quiz_api/identity_api/go/misc_api 路由层）→ `cron/`（CLI 分发＋子任务）。
- **依赖方向单向**：web → domain → llm/providers → core；core 禁 import web/domain/llm；domain 禁 import web（阶段3验收项 F）。
- 页面路由（`web/pages.py`）只做渲染，业务全走 `/api/*`；公共面＝`app.main:app`（:8000 薄装配）与 Admin 面＝`app.admin:admin_app`（:8001）两入口冻结，admin 路由禁出现在公共面。

## 数据与写入
- 应用代码 SQL 写路径一律 `db.tx()`；迁移文件放 `migrations/NNNN_*.sql`（expand-only，细则走 `/db-migration`）。
- cron 任务（`app/cron/`）仅 INSERT 聚合表/探活表/审计表，禁止 UPDATE/DELETE 业务表；入口 `python -m app.cron` 冻结。
- Umami（`app/core/umami.py`）＝events 表游标重放副本，禁止引入独立队列；统计口径以 SQLite `events` 为准。
- 新埋点事件必须先入 FR-15 枚举（`app/core/events.py`）再上报；`client_event_id` 幂等约束禁绕过。

## 安全与频控（2026-09-07 放行，源＝工程审查 V-3/V-4，候选编号 CC-N1/N2）
- 生产模式（`WTE_ENV=prod`）密钥缺失或走 dev 兜底 → **拒绝启动**（勿改回静默回退）；非 prod → stderr 告警＋audit `insecure_secret_fallback`（守卫在 main/admin 双面 startup，动 startup 必须保留）。〔CC-N1〕
- 新增交互通道（re-ask 类请求型端点）**必须带服务端频控＋耗尽留痕**（409＋事件，参照 `RE_ASK_LIMIT`/`swap_exhausted` 模式）——禁止出现无上限的请求型端点。〔CC-N2〕

## LLM 与策略
- 实时生成上下文禁传 anon_id 原文——只传 `tonight_tags`＋口味摘要＋日轮换假名（`app/llm/service.py` ctx 结构，PIPL）。
- 健康建议双层拦截位置：prompt 层（`llm.py` 系统 prompt）＋输出黑名单（`strategy.py` `HEALTH_BLACKLIST`）——改文案禁拆任一层。
- 改 `strategy.py`/`llm.py` 前先读 `docs/adr/adr-004-llm-vendor-xiaomi-mimo.md`＋`docs/execution/iteration-log-W1.md` 最新节（降级链与预算语义的历史裁决都在那）。
- 推荐结果必带 `source`（pool|realtime|library），降级＝`source=library` 单列观测、不算不可用。

## config 行为键（改行为优先调 config）
`form`（undecided/A/C，翻转归人）、`swap_limits`（cold 3/steady 2）、`llm.disable_thinking/daily_call_cap/daily_cost_cap_usd`、探活清单、全局兜底开关——完整清单与三道闸见 `app/admin.py` 头注与方案 §1.3。
