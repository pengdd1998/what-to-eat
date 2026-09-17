# AGENTS.md — 「吃什么」工作区须知

> 约束基座 v1.0 · 2026-09-04 生成 · 源＝规划 v4.1＋实施方案 v3.1＋ADR-001~005＋对账（`docs/reverse/`）
> re-init 触发：依赖大版本升级 / 架构级 ADR 变更 / 漂移复检 >15% / 连续 3 次纠偏指向同一规则缺失

## 项目是什么
晚餐决策收口 H5 工具（微信外手机浏览器 + PWA）：≤3 道自适应题 → 唯一结果＋一句推荐语 →「就吃这个」跳外卖平台。栈＝FastAPI + SQLite(WAL) + Jinja2 SSR 单体：无 SPA 构建链、无 Webfont、动效 CSS-only。阶段与排期以 `docs/product/product-plan.md`(v4.1)、`docs/tech/implementation-plan.md`(v3.1)、`docs/execution/iteration-log-W1.md`（滚动迭代日志）为准。

## 目录
- `app/` — 后端＋模板＋静态资源。两个 ASGI 入口：`app.main:app`（公共面）与 `app.admin:admin_app`（内网面，Bearer ADMIN_TOKEN，仅宿主回环访问）。
- `migrations/` — 编号 SQL，启动按文件名顺序执行（expand-only）。
- `scripts/` — 冒烟/备份/指标重算/PoC 探针；`scripts/cron.md`＝定时任务清单。
- `docs/` — 产品（`docs/product/`）与技术（`docs/tech/`）文档、ADR-001~005（`docs/adr/`）、设计系统（根级 `DESIGN.md`＋`docs/design/`）；`docs/execution/`＝执行归档（迭代日志、PoC 报告、留档数据），改敏感区域前先读；地图见 `docs/README.md`。
- `deploy/Caddyfile` — 边缘（whattoeat.lifestyle）：公网 `/api/admin/*` 一律 403，反代 api:8000。
- `poc/` — 仿真 harness。

## 常用命令
- 全链路冒烟（自动建 venv＋临时库，起 8100/8103 双面跑断言）：`./scripts/smoke_local.sh`
- 本地起服务：`.venv/bin/uvicorn app.main:app --port 8100`；Admin 面：`app.admin:admin_app --port 8103`（需 `ADMIN_TOKEN`）
- 容器：`docker compose up -d --build api`（宿主回环映射等运维入口细节见私有运维注记）
- 定时任务：`python -m app.cron <aggregate|probe|cost_close|batch>`（须带 `WTE_DB_PATH`）
- 无独立 lint/test 框架——冒烟脚本即验收

## 环境变量（.env 已 gitignore；密钥禁入 git/前端/库，SUP-02）
`WTE_DB_PATH`、`GO_SECRET`(≥32B)、`ADMIN_TOKEN`(≥64 字符)、`LLM_BASE_URL`/`LLM_API_KEY`（主供＝小米 MiMo，ADR-004；qwen 切换建议在案待拍板，见迭代日志）。`GLM_*`/`QWEN_*`＝对照备选。`app/llm.py` 自带极简 .env 加载。

## 架构红线
- **双面物理分离**：Admin 只走回环 8001，Caddy 公网 403 是第三层防线；勿在公共面挂 admin 路由。
- **SQLite 单连接＋线程锁**：写一律走 `db.tx()`（BEGIN IMMEDIATE）；WAL/synchronous=FULL/busy_timeout 已设定，勿绕过。
- **降级链是产品原则**：LLM 不可用/超预算/池未命中 → 本地菜库兜底＝“功能降级可用”（source=library 单列观测），不算不可用；改 `strategy.py`/`llm.py` 勿破坏此语义。
- **LLM 硬预算**：`disable_thinking=True` 为实测拍板（开思维链 8–21s 超预算）；软超时 3s/硬 6s；日调用数与日费用双熔断（config `llm.daily_*`）。
- **运行时行为走 config**：`config.form`（undecided/A/C，D6 终裁后 Admin 翻转）、`swap_limits` 等——改行为优先调 config 而非改代码。
- **Dockerfile 教训**：健康检查按服务定义在 compose（api=8000/admin=8001），勿放单一 HEALTHCHECK（曾致 admin 常驻 unhealthy）。
- `forwarded-allow-ips=*` 安全前提＝api 仅回环发布、公网唯一入口 Caddy；改端口发布前先重评。
- **北极星口径 100% 服务端**：accept/jump 双事件 `server_ts` 差 ≤60s 判分子，禁在前端造口径（HC-10）。
- **依赖钉版**：requirements.txt 升级必须容器内验证后再合（曾因本地/容器漂移致公网 500）。
- **拍板权归人**：`config.form` 终裁翻转、LLM 主供切换（qwen 建议在案）等架构级决策，Agent 禁自行执行，只能备材料。

## UI/文案约束
- 硬验收：全程 ≤30s / ≤5 次点击；首屏 P75 ≤2s；换一上限稳态 2/冷启动 3（禁无限浏览）。
- 视觉＝「街角灯箱」（tokens 见 `DESIGN.md`）：墨绿底、芥末黄唯一大色块、3px 描边；暗色第一公民；对比度 ≥4.5:1、触达 ≥44px、prefers-reduced-motion 全尊重、结果播报 aria-live。
- 合规：禁健康/减脂表述；隐私红线＝不收手机号、不做微信授权、不取 GPS 精确位置；IP 推断城市（市级粗粒度、不落库不进日志、仅天气用途）已披露并获 owner 确认（2026-09-15 纠偏，原「三不」含位置）。

## 约定
- 全仓中文（文档/注释/commit）；commit message 带结论与出处（§、ADR、任务号），沿用此风格。
- 方案级决策分叉落 ADR；执行过程与数据归档 `docs/execution/`；迭代日志滚动更新。
- 留档数据（`docs/execution/data/`、`docs/execution/m0/`）只增不改，除非明确要求（`.zcode/` 路径守卫已硬拦截）。
- 改 `app/` 前先读 `app/AGENTS.md`（代码区细则：分层/cron 只 INSERT/Umami 游标/LLM 脱敏/埋点枚举）。
- 领域规程走命令：发布 `/release`、数据库变更 `/db-migration`、故障处置 `/incident`（`.zcode/commands/`）。
- **双正本纪律（ci-cd-plan §2.3）**：代码正本＝公开仓（日常提交/CI/CD）；运维正本＝私有仓（`docs/` 内层嵌套仓跟踪 execution/reverse/ops-private——`cd docs` 后 git 命中内层仓）。**任何层级禁 `git clean -x`**（根目录执行清空敏感子树＋内层仓；docs/ 内执行清公开子树）。
- **commit message 公开化**：结论/出处/任务号保留；基础设施字面量（IP/路径/主机名）与运维敏感细节不入 message（公开仓永久可见）；引用私有档用中性措辞（坐标可留、内容不展开）。
- 文档地图与 ADR 索引见 `docs/README.md`；纠偏回写须走 mini 流程（见 `docs/reverse/rule-placement.md` 演化机制），禁直接堆句子进本文件。
