# LLM 能力监控与可视化看板落地方案 v1.1

> 2026-09-16 立项 · 源＝owner 需求（LLM 各项能力指标持续监控跟进＋可视化看板）
> 状态：**已拍板（2026-09-16 owner 按 agent 建议终裁）**——A=HTTP Basic / B=告警阈值建议值起步 / C=vendor 对照备料不启动；进入执行 P0→P1→P2（§6）
> v1.1 变更：①三拍板落定（§4/§5/§6）；②主供口径修正＝qwen3.8-flash（ADR-004 修订节 2026-09-04 拍板、9/8 生产切换；AGENTS.md 环境变量段为旧快照，漂移披露见 §1）
> 关联：ADR-004（主供选择＋9/4 修订节）、实施方案 §1.1（降级链）、迭代日志 W3 D3（P95 3793ms 观察项＋本方案立项拍板）、AGENTS.md 架构红线

## 1. 工程现状盘点（方案依据）

**调用链**（阶段3重组后）：`web` → `domain/quiz.py`（出题/收口）→ `llm/service.py`（双熔断＋`llm_calls` 留痕）→ `llm/gateway.py`（全仓唯一 HTTP 出口，JSONL 留痕）。降级链＝LLM 不可用→本地题/本地池兜底，`source=llm|local` 单列观测。

**已有三份数据源，但都有缺口**：

| 数据源 | 内容 | 缺口 |
|---|---|---|
| `llm_calls` 表 | 每次逻辑调用一行：ts/vendor/scene/latency_ms/tokens_in/out/cost_usd/status | ① **error_class 不入库**（只在 JSONL）；② **无 task 粒度**——出题/收口共用 scene='cold_start'（受 CHECK 约束限制，迁移 0003）；③ **无 attempts**（重试率不可算） |
| 网关 JSONL（`logs/llm-gateway-*.jsonl`） | 每次 HTTP 尝试一行：error_class/detail、attempts、prompt_hash、model/route——字段最全 | 只落文件、无聚合、**无清理策略**（磁盘 87% 观察中） |
| `daily_metrics` 表 | cost_close 日结 4 项（llm_calls/llm_cost_usd/llm_p95_ms/llm_month_cost_usd）＋aggregate 的 rec_llm_hit_rate/quiz_completion_rate 等 | 无成功率/错误分布/P50/超软超时占比/出题兜底率等能力指标；**只能 export CSV 看，无可视化** |

**质量侧存量**：golden 30 用例（`tests/test_golden.py`，测维度树非模型输出——属发布门槛非在线指标）；`quiz_session.question_log` 每题已记 `source=llm|local`、`result` 已固化 `source`——**出题/收口兜底率的数据已在库，只是没聚合**；finalize 的 dish_consistent 拒因目前仅 stderr 打印（`quiz.py:584`）无结构化留痕。

**Admin 面**：纯 API（config/export/batch/audit/wipe），无任何页面。鉴权 Bearer，仅回环 8001＋SSH 隧道＋Caddy 公网 403 三层防线。

**本方案直接服务的三件事**：① LLM P95 3793ms 超软超时 3s＝在案持续观察项（W3 D3），需自动化跟进；② P95 归因需要 vendor 对照证据（现主供＝qwen3.8-flash，ADR-004 修订节 2026-09-04 owner 拍板、9/8 生产切换；MiMo 降第二/GLM 为备选位）——看板备 vendor 维度数据，**对照启动拍板权归人**；③ ICP 备案窗口公网零流量＝安全改造窗（重构窗先例 W2）。
> 漂移披露（2026-09-16 取证）：AGENTS.md 环境变量段「主供＝小米 MiMo……qwen 切换建议在案待拍板」为 9/4 早间旧快照，与 ADR-004 修订节不一致——纠偏走 mini 流程（rule-placement.md），本方案以上述 ADR 修订节为准。

**选型裁决（否决项）**：不引外部观测平台（Grafana/云监控 SDK 等）——网关红线「不引入观测平台 SDK」（`gateway.py` 头注）、单体轻栈原则；现状 CSV export 裸看不可持续。→ 结论：**SQLite 内聚合＋Admin 面 SSR 看板**，零新依赖。

## 2. 指标体系：LLM 能力五层

| 层 | 指标 | 数据源 | 状态 |
|---|---|---|---|
| L1 可用性 | 调用成功率、error_class 五枚举分布（超时/限流/内容过滤/解析失败/未知）、重试发生率、熔断触发次数 | llm_calls（补列）＋audit | **新增** |
| L2 性能 | P50/P95/P99、**超软超时(>3000ms)占比**、重试后总时延 | llm_calls | P95 已有，余新增 |
| L3 成本 | 日调用/日费用、月累计（$40 告警线）、tokens in/out、单调用均价 | llm_calls | 部分已有 |
| L4 能力质量 | **出题 LLM 占比**（question_log source 聚合）、**收口本地兜底率＋拒因分布**（调用失败 vs dish_consistent 拒绝 vs 健康拦截——区分网络退化与能力退化）、降级链分布（rec_source，已有） | quiz_session 载荷 | **新增（数据已在库）** |
| L5 业务映射 | quiz_completion_rate、answer_steps_median、north_star（已有） | daily_metrics | 只读展示 |

判读纪律沿用：任何比例必附 n（daily_metrics.n 字段设计在位），周判读用 Wilson 95% CI（`scripts/recalc_metrics.py` 已有实现可复用）。

## 3. P0：数据补强（expand-only，先行）

1. **迁移 0007**（走 `/db-migration` 规程）：`llm_calls` 三列纯 expand，不触 scene CHECK、无表重建：
   ```sql
   ALTER TABLE llm_calls ADD COLUMN task TEXT;         -- next_question|finalize|cold_start|batch（应用层枚举）
   ALTER TABLE llm_calls ADD COLUMN error_class TEXT;  -- 网关五枚举；成功为 NULL
   ALTER TABLE llm_calls ADD COLUMN attempts INTEGER;  -- 1=首过 2=重试过
   ```
   老行为 NULL＝判读 COALESCE 到旧口径。
2. **service/quiz 贯通**：`service.complete()` 加 `task` 参数透传落库＋`error_class`/`attempts` 回填；`quiz.py:407` 传 `task="next_question"`、`quiz.py:576` 传 `task="finalize"`；`cron/batch.py` 调用点同步补 `task="batch"`。
3. **finalize 拒因结构化**：本地兜底时在 `result` JSON 补 `local_reason`（call_failed|dish_conflict|health_block）——纯载荷字段，替代 stderr 调试打印（打印保留）。
4. **cost_close 日结扩 9 项**（INSERT daily_metrics，口径单一事实源不破）：
   `llm_success_rate`、`llm_p50_ms`、`llm_soft_timeout_rate`、`llm_retry_rate`、`llm_error_dist`（value=JSON 分布，表设计本就兼容）、`llm_tokens_in_sum`/`llm_tokens_out_sum`、`quiz_question_llm_rate`、`quiz_finalize_local_rate`（＋拒因分布入 value）。
5. **验收**：pytest 补落库断言（task/error_class/attempts＋新指标造数直调）；冒烟 cost_close 断言段扩新指标键（`smoke.py:211` 先例）。老 JSONL 不回灌——聚合从上线日起算。

## 4. P1：看板 MVP（Admin 面 SSR）

- **端点**：`GET /api/admin/llm/overview?days=14`（JSON，趋势＋当日）＋ `GET /admin/llm?days=14`（SSR HTML，days 用链接切换 7/14/30——**零 JS**）。
- **鉴权（已拍板 A＝HTTP Basic，2026-09-16）**：浏览器原生弹窗可记住凭据，ADMIN_TOKEN 同值作密码；恒时比较沿用 `hmac.compare_digest`；三层防线不变（回环 8001＋SSH 隧道＋Caddy 公网 403）。备选 `?token=` query 否决（token 入 URL/访问日志留痕面）。看板访问写 audit（与 export 同待遇）。
- **技术形态**：Jinja2 SSR＋服务端生成内联 SVG 折线/柱状——守「无 SPA 构建链/无 Webfont/CSS-only」红线；系统字体栈；暗色第一公民；样式内联在 Admin 模板内（不碰公共面 CSS）。新模板放 `app/templates/admin/llm.html`，Admin app 挂 `Jinja2Templates`。
- **版面（一屏四区）**：
  1. **概览卡**：今日成功率/P95/日费用/月费用占预算比/熔断次数/出题 LLM 占比，每项带昨日对比与 n；
  2. **趋势区**：P50/P95 折线（**3s 软超时参考线**）、日调用/日费用柱（月 $40 预算线）、成功率折线；
  3. **结构区**：error_class 堆叠柱、出题 llm/local 占比、收口 llm/local 占比＋拒因分布；
  4. **明细区**：近 50 条 llm_calls（本表无 prompt 原文，天然脱敏）＋audit 中 LLM 熔断/config 变更记录。
- **数据源**：趋势读 daily_metrics；当日明细实时 SQL（只读走 `db.connect()`，聚合压力留给 cron——SQLite 单连接红线不破）。
- **验收**：Admin 面无凭据 401/带凭据 200 含 SVG；overview JSON 键齐全；公共面零改动（diff 确认）；冒烟 8103 面加看板断言。

## 5. P2：持续跟进机制

1. **告警规则扩展（已拍板 B＝建议阈值起步，2026-09-16；狗粮期按实际 n 校准，常量 owner 可调）**（复用 `notify` Server酱/ntfy，cost_close 内判定）：
   - P95 连续 3 日 >3000ms → P2「软超时持续超线」（**当前观察项自动化收口**）；
   - llm_success_rate <0.9 且 n≥20 → P2；quiz_question_llm_rate <0.7 且 n≥10 → P2（能力退化信号）；quiz_finalize_local_rate >0.3 且 n≥10 → P2；
   - 月 $40 线（已有）。
2. **周判读挂接**：weekly-review 模板补「LLM 五层指标」一节，数据源＝overview API/看板；P95 与步数两个在案持续观察项自此有固定盘面。
3. **JSONL 保留策略**：聚合入表后文件仅作排障——宿主 crontab 一行 `find logs/ -name 'llm-gateway-*.jsonl' -mtime +14 -delete`，入 `scripts/cron.md` 清单（文件清理非业务表写，不触「cron 只 INSERT」红线；呼应磁盘 87% 观察）。
4. **vendor 对照备料（已拍板 C＝备料不启动，2026-09-16；随 P95 归因需要或备案恢复流量后再裁决启动）**：＝用生产同源 prompt 让主供（qwen）与备选在相同条件下双跑、积累可比数据。现存判据（ADR-004 附录）全部来自**一次性人工探针脚本**（背靠背 12 次/30 场排序基准），无持续数据；P95 超标观察项若要区分「qwen 路由问题 vs prompt 过长 vs 系统性」，对照臂是最快证据。备料内容：看板 vendor/route 分组（`llm_calls.vendor` 列＋JSONL `route` 字段天然区分）；GLM 臂现成可用（`route="glm"` 读 GLM_*），MiMo 臂需网关 ROUTES 加一项读 MIMO_*（一行改动）。启动则另出小方案（日 N 次同源 prompt 双跑探针，flash 档费用分/元级）——**对照引入额外调用属架构级行为，拍板权归人**（AGENTS.md 红线）。

## 6. 拍板记录与阶段计划

**拍板（2026-09-16，owner 按 agent 建议终裁；§4/§5 同步更新）**：

| 拍板点 | 内容 | 终裁 |
|---|---|---|
| A | 看板鉴权：Basic vs query token | **HTTP Basic**（ADMIN_TOKEN 同值；query token 否决——入 URL/访问日志） |
| B | 告警阈值初值（§5.1 四条） | **建议值起步**：P95 连续 3 日 >3000ms；成功率 <0.9 且 n≥20；出题 LLM 占比 <0.7 且 n≥10；收口兜底率 >0.3 且 n≥10——狗粮期按实际 n 校准 |
| C | vendor 对照（qwen vs MiMo/GLM 同源双跑探针）是否启动 | **备料不启动**：备案窗流量小、对照数据 n 不足；看板留 vendor 分组＋GLM 臂 route 现成/MiMo 臂一行改动，启动随 P95 归因需要或备案恢复流量后再裁决 |

阶段执行状态（滚动更新）：**P0-P2 全部完成并上线**（2026-09-16，commit cd3f364；生产验证：三列落库/task 落库实证/看板 401+200 6 SVG/告警在位/cost_close 首跑出数）。

| 阶段 | 内容 | 估时 | 门槛 |
|---|---|---|---|
| P0 | 迁移 0007＋task/error_class/attempts 贯通＋cost_close 扩 9 指标 | 0.5~1 天 | pytest＋冒烟全绿，生产 cron -m 直跑验证 |
| P1 | overview API＋SSR 看板 | ~1 天 | 401/200 断言＋公共面零改动 diff |
| P2 | 告警四条＋周判读挂接＋JSONL 清理 | 0.5 天 | 告警演练一条真实触发链路 |

可在 ICP 备案窗口内完成（零流量安全窗，重构窗先例）。

## 7. 红线对照（自查）

双面物理分离（看板仅挂 8001，公共面不动）✓；SQLite 写只走 tx/cron ✓；cron 只 INSERT（扩指标仅 UPSERT daily_metrics；JSONL 清理放宿主）✓；降级链语义零改动（只观测不改行为）✓；LLM 预算红线不动（3s/6s/双熔断原值）✓；无构建链/无 Webfont（SSR＋SVG）✓；prompt 不落库不进看板（llm_calls 本无原文，JSONL 不上看板）✓；依赖钉版（零新依赖）✓；拍板权（A/B/C 显式归 owner，vendor 对照只备料）✓；留档数据不触 ✓。
