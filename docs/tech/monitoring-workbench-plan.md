# 监控 v2：工作台化落地方案 v1.1

> 2026-09-20 立项 · 源＝owner 指令「参考 Claude Code Router（CCR）的工作台监控，对监控模块给出优化方案」→「采用建议策略，给出详细落地方案文档」
> 状态：**三批全部实施完成并上生产**（2026-09-20：P0-1 hotfix＋批次一~三；生产验证：probe 探活复活全绿/看板工作台 12 SVG＋小时桶＋筛选＋KPI/0008 两列落库）——ping 生产实况：BASE_URL 已配、**LLM/GLM/QWEN 三 MODEL 名未配**（route_unconfigured 属缺省预期，待 owner 提供后即真实探测）
> v1.1 变更（复审采纳）：①§0 补记评审增量发现 A（probe 兜底告警改翻转触发）＋B（跳转下线与 probe 关联披露）；②§3 P0-1 实现与测试按 A 更新（四锚）；③实施表/风险表同步
> 前作：`docs/tech/llm-monitoring-plan.md` v1.1（P0-P2 已完成上线，2026-09-16 cd3f364）；本方案为其续篇，覆盖面从 LLM 扩到全监控（深链探活/磁盘/应用错误/判读流程）
> 关联：ADR-004（LLM 主供）、`docs/reverse/constraint-candidates.md` OB-10~14、`.zcode/commands/db-migration.md`、`.zcode/commands/incident.md`、AGENTS.md 架构红线

## 0. 拍板记录（2026-09-20）

| # | 拍板点 | 终裁 |
|---|---|---|
| 1 | probe.py 实伤是否先行单独修 | **先行单独修**（一行 import＋测试，独立 commit，可不等整批部署） |
| 2 | `llm_calls` 加 model 列（迁移 0008）时机 | **本轮做**，走 `/db-migration` 规程（expand-only＋生产副本预演＋冒烟全绿） |
| 3 | LLM ping 是否计入日调用熔断 | **不计入**——ping 不落 `llm_calls`、只落 audit（见 §5.1，顺带绕开 scene CHECK 约束），熔断计数与月成本口径天然不含诊断流量 |
| 4 | 熔断触发告警分级 | **P2**（与 incident.md「P1 仅三类」铁律对齐：降级链下功能仍可用，当日触达即可） |

另：实施前盘点新实证两处实伤（§2 之 ②⑨），属修复类无方案分叉，随批次顺修；其中 ⑨ 触及出题主链（quiz.py next/answer），已在本方案内以冒烟全绿为门槛，如 owner 对主链改动有保留可单独裁示降级为「只修聚合注释」。

**评审采纳（2026-09-20 开发评估两增量发现，owner 已确认）**：
- **A（中）probe 兜底告警改翻转触发**：原实现为电平触发（`probe.py:65-81` 条件满足即执行），深链持续不可用时将每日重复 P1 notify＋每日重写一行 `probe_auto_fallback` audit。改为只认 `links.status` 非 dead→dead 的**翻转**才发 P1＋写 audit（config 幂等重写保留，无害），持续 dead 静默——与既有「恢复 P2」（ok 翻转）对称成对。随 P0-1 落地。
- **B（低）跳转下线与 probe 的关联披露**：第三方外卖跳转已于 2026-09-16 拍板移除（前端无 `/go` 入口、后端机制保留可逆），深链探活的**用户面影响已降为零**——probe 保全的是后端机制可逆性而非用户可用性。不改变修复价值（防线本该工作），且是 A 降噪的论证前提：持续死链不值得 P1 级重复打扰。

## 1. 对标结论与范围

CCR 工作台＝「概览仪表盘（10 指标＋时间分桶）＋请求日志（多维筛选＋单条详情）＋Agent 观测（执行链路 trace）＋连通性检测」四件套。逐项映射本仓现状后的差距即本方案范围；**设计原则：借形态、不借栈**——继续零 JS SSR＋服务端 SVG、零新依赖、SQLite 内聚合（v1.1 已否决外部观测平台，不重议）。

| CCR 概念 | 本仓差距（=本方案条目） |
|---|---|
| 仪表盘「今天」按小时分桶 | 当日无趋势，最长滞后一天（P1-1） |
| 请求日志多维筛选 | 明细固定 50 条无筛选、无 model 维度（P1-2/P1-4） |
| Agent 执行链路面板 | question_log 在库无渲染出口（P1-5） |
| 连通性检测 | LLM 侧无健康探测；深链探活已坏（P0-1/P2-1） |
| 预算余量告警 | 熔断触发不通知（P0-2） |

明确不做（防过度工程，CCR/LiteLLM 有而本仓不借）：可拖拽组件网格、实时 WebSocket 流、分享卡片、请求/响应 body 留存（prompt_hash 脱敏是隐私红线下更优解）、Prometheus/Grafana/OTel、供应商自动摘除（只有降级链没有多活）、CCR 当日清理保留策略（daily_metrics 长期保留是判读资产）。

## 2. 实伤与缺口清单（方案依据，均已代码实证）

1. **probe.py urllib NameError（P0-1）**：`app/cron/probe.py:43/45` 引用 `urllib.request`，但全文件仅有 L26 函数内 `from urllib.parse import quote`（只绑定 `quote`，不绑定 `urllib` 名字）→ 每条链路 3 次尝试全部 NameError 被 L49 `except Exception` 吞成 `fail`，**对照百度同红 → `ctrl_green` 恒假 → 自动兜底与 P1 告警永不触发**。自阶段 3 拆分（dd14951 前后）起深链探活完全失明，`probe_results` 全为假 fail。tests/smoke 均无 probe 覆盖。
2. **common.py notify 潜伏 NameError（P0-2 顺修）**：`app/cron/common.py:38/50` 的 `except` 分支引用 `sys.stderr`，全文件无 `import sys`——告警通道网络失败时 except 内自身 NameError 向上炸断 cron 主流程（cost_close 六条告警、probe P1、backup P2 全部暴露于此）。
3. **熔断无通知（P0-2）**：`service.py:95-99` `_audit_circuit` 只写 audit_log；双熔断打穿当天只能次日看板/日结发现。
4. **OB-12 未落地（P0-3）**：磁盘>80%/库>500MB→P2 在约束清单标记「确定」但无判定代码；磁盘水位目前只能人工盯（生产 82~90% 波动，95% 部署会失败）。
5. **告警链未入档（P0-4）**：cron-run.sh wrapper（五任务失败 P1 的唯一闭环）只存在于宿主；SERVERCHAN_SENDKEY/NTFY_TOPIC 不在 `.env.example`；JSONL 清理只靠宿主 crontab 口口相传。
6. **趋势滞后一天（P1-1）**：看板趋势全读 23:59 cost_close 日结的 daily_metrics，当日只有概览卡实时。
7. **明细无筛选、无 model（P1-2/P1-4）**：`llm_dash._detail_rows` 固定最近 50 条；模型名只在 JSONL，`vendor` 列语义混杂（实时调用恒 `openai_compatible`，batch 落 `qwen`）——v1.1 §5.4 vendor 对照备料实际不可用。
8. **已聚合未可视化（P1-3）**：`svg_stack`（llm_dash.py:159）死代码；error_class 分布/重试率/软超时率/tokens 双和已在 daily_metrics，只能 CSV export 裸看。
9. **L4 出题占比口径失真（P1-4b，本轮新实证）**：`question_log` 条目由 answer() 落库（quiz.py:510-516），**不带 `source` 字段**；cost_close 按 `_q.get("source","llm")` 聚合（cost_close.py:55）→ `quiz_question_llm_rate` 恒 1.0，看板「出题 LLM 占比」KPI 自上线起报假数（收口侧 `result.source` 是真实落库的，`quiz_finalize_local_rate` 不受影响）。
10. **trace 无出口（P1-5）**：定位「为什么这题走了本地兜底」只能连库手查 question_log。
11. **应用侧错误不可见（P2-2）**：unhandled 500 只 stderr（main.py:56-64）；429 限流计数无指标出口。
12. **周判读无模板（P2-3）**：weekly-review 的「LLM 五层指标」节靠手写快照（v1.1 §5.2 承诺未落地）。

## 3. 批次一 P0：修伤＋告警闭环

### P0-1 probe.py 修复（拍板 #1：先行单独修）

- **改动**：`app/cron/probe.py` 顶部 import 块（L2-7）加一行 `import urllib.request`；兜底分支（L65-81）按评审发现 A 改**翻转触发**——`all_red and ctrl_green` 且 `links.get("status") != "dead"` 才 P1 notify＋写 audit `probe_auto_fallback`（config 幂等重写保留），持续 dead 次日运行静默（恢复 P2 分支已有翻转判定，不动）。HEAD→GET→GET 三试、对照判定逻辑均原样。
- **测试**：新增 `tests/test_probe.py`（pytest，conftest 临时库夹具自动跑全迁移、菜库已 seed）：
  - monkeypatch `urllib.request.urlopen` 为假响应（status 200）＋monkeypatch `notify`——**断言 urlopen 真实被调用**（call_count>0 即 NameError 修复的回归锚）＋probe_results 全 ok、无兜底翻转；
  - urlopen 全抛异常 → 全 fail 且**对照同红** → 断言 `links.status` 未被置 dead、无 P1 notify（对照语义回归锚）；
  - 仅链路抛异常、对照 200 → 断言自动置 dead＋audit `probe_auto_fallback`＋P1 notify（兜底链路回归锚）；
  - **持续态去重锚（评审 A）**：links.status 已为 dead 时再次全红运行 → 无新 P1 notify、无新增 `probe_auto_fallback` audit 行（config 重写无害不 assert）。
- **生产验证**：部署后宿主 `python -m app.cron probe` 直跑一次，`probe_results` 应出现真实状态（不再恒 fail）。
- **风险**：修复后首次真实探活结果未知——若美团深链确实已不可用，会出现真实的 P1 告警＋自动全局兜底（**仅首日一次**，持续态经评审 A 去重），属设计内行为（runbook §5.2.6 人工复核；且跳转已下线、用户面影响为零，见 §0 发现 B）。

### P0-2 notify 收口＋熔断即时通知（拍板 #4：P2 级）

- **收口**：`app/cron/common.py` 的 `notify` 迁至新文件 `app/core/notify.py`（**顺修 `import sys` 缺失**）；`common.py` 改 `from ..core.notify import notify` 再导出，cron 四个调用点零改动。依赖方向 llm/core → core 合规。
- **熔断通知**：`service.py:_audit_circuit` 改两段式——
  1. tx 内写 audit 前先查当日是否已有 `llm_circuit_break`（`SELECT COUNT(*) ... WHERE action='llm_circuit_break' AND substr(ts,1,10)=?`），返回「是否当日首次」；
  2. **tx 外**（SQLite 单连接红线：禁持锁做网络 IO）对首次触发调 `notify("P2: LLM 日熔断已触发（{reason}），今日实时调用关闭、本地兜底生效", "", "P2")`。
  `complete()` 与 `generate_recommendation()` 共用此函数，两路径同时受益。notify 双通道失败只打 stderr 不抛，不影响降级链返回。
- **测试**：pytest 造数凑满 `daily_call_cap` → `complete()` 返回 fail 且 reason 含 `daily_call_cap`、audit 落行、notify 恰好 1 次；第二次调用不再 notify（当日去重锚）。

### P0-3 OB-12 磁盘/库体积告警

- **改动**：`app/cron/cost_close.py` 告警区（L96-117 后）加两条判定＋两个指标：
  - `shutil.disk_usage(os.path.dirname(os.path.abspath(db.DB_PATH)) or "/")`（与 `/api/health` 同算法同视角：容器内挂载卷）；>80% → P2 notify；
  - 库体积＝`DB_PATH`＋`-wal`＋`-shm` 三文件字节数和；>500MB → P2 notify（OB-12 阈值，常量起步、注释标出处）；
  - daily_metrics 写 `disk_pct`、`db_size_mb`（判读资产，看板 P1 批次顺带展示）。
- **已知效应（预期内）**：当前生产磁盘 82~90%，上线首日即触发 P2 并持续日报，直到「磁盘 90% 升级待办」完成——这正是把人工盯盘自动化。
- **测试**：cost_close 返回值/指标键断言（smoke §6.5 扩键）。

### P0-4 告警链入档

- `docs/ops-private/bin/cron-run.sh`（私有正本）：实施时从宿主取回现状脚本入档；若与 `docs/ops-private/README.md` 描述有漂移以宿主为准回写文档。
- `.env.example` 追加（公开仓只进变量名）：`SERVERCHAN_SENDKEY=`、`NTFY_TOPIC=`（注释：cron/熔断告警双通道，任配其一即生效）。
- `scripts/cron.md`：补 wrapper 正本位置指针（中性措辞指 ops-private）＋告警 env 名；JSONL 宿主清理行已有说明补「实装证据见 ops-private」。

**批次一验收**：pytest 全绿＋`./scripts/smoke_local.sh` 全绿（§6.5 扩 disk_pct/db_size_mb 键断言）＋生产 `python -m app.cron probe` 直跑真实出数＋熔断通知演练（临时把 cap 调 0 触发一次真实 notify 后还原，或以 dev 库演练）。发布走 `/release`，api＋admin 双容器重建。

## 4. 批次二 P1：看板工作台化

### P1-1 今日小时桶实时趋势（CCR「今天·按小时分桶」）

- `llm_dash.py` 新 `_today_hourly(today)`：`SELECT substr(ts,12,2) h, COUNT(*) c, COALESCE(SUM(cost_usd),0) cost FROM llm_calls WHERE substr(ts,1,10)=? GROUP BY h`，补齐 0~当前 UTC 小时空桶；`overview()` 增 `hourly` 键（JSON 同步带上）。
- `admin.py /admin/llm` 渲染 `svg_bars`×2（时调用数、时费用，x 轴=UTC 小时）；模板在趋势区上方插「今日实时（UTC 小时桶）」节。**口径标注 UTC**（与全仓指标 UTC 日界一致，cron.md §3）。
- 只读 SQL 不加聚合任务，趋势 7/14/30 天仍走 daily_metrics（聚合压力留给 cron 的既定分工不变）。

### P1-2 明细筛选日志页（CCR 日志页的零 JS 子集）

- `/admin/llm` 加 GET 参数（服务端 WHERE，全部参数化＋白名单枚举防脏链接）：`f_status`(ok|error)、`f_ec`(error_class 五枚举)、`f_task`(next_question|finalize|cold_start|batch_copy)、`f_days`(1|7|30，默认 7)。
- `_detail_rows` 按参数动态拼 WHERE＋`substr(ts,1,10)>=` 日期下限；无参数=现行为（最近 50 条）。表格加 model 列（P1-4 后）。
- 模板加 `<form method="get">`（select＋提交按钮，纯导航零 JS）＋当前筛选态回显。

### P1-3 补齐已聚合未可视化指标

- `_trend` 扩读：`llm_error_dist`（value 为 JSON dict，展开为五枚举各一条序列）、`llm_retry_rate`、`llm_soft_timeout_rate`、`llm_tokens_in_sum`/`llm_tokens_out_sum`。
- 「结构与能力质量」区扩四图：error_class 堆叠柱（**启用死代码 `svg_stack`**，labels=五枚举）、重试率折线、软超时占比折线、tokens in/out 双柱。
- `cost_close.py` 补一个 metric：`quiz_finalize_reasons`（拒因分布 dict——现只在告警消息文本里，入库后可判读）。

### P1-4 迁移 0008＋贯通（拍板 #2：本轮走规程）

- **`migrations/0008_monitor_v2_columns.sql`**（expand-only，两列均可空、无表重建、不触任何 CHECK）：
  ```sql
  -- 监控 v2（monitoring-workbench-plan §4）：model＝实际模型名，与 vendor（接入方式）语义分离
  ALTER TABLE llm_calls ADD COLUMN model TEXT;
  -- 出题主链 L4 口径修复：next() 生成的题目（含 source）暂存，answer() 取用并入 question_log 后清空
  ALTER TABLE quiz_session ADD COLUMN pending_q TEXT;
  ```
- **规程步骤**（`.zcode/commands/db-migration.md`）：生产库 `sqlite3 .backup` 副本预演 → smoke_local 全量迁移绿 → 合入发布。
- **model 贯通**：`log_call` 签名加 `model=None`；调用点补传——`service.complete()` 成败两处（`model=model`，resolve 结果里现成）、`generate_recommendation()` 三处（`model=r["model"]`）、`cron/batch.py` 一处（`model=model`）。`vendor` 列**不动**（历史一致），明细页两列并显；分组判读/未来 vendor 对照用 model 维度。老行 NULL 显示 `—`，不回填（JSONL 有但收益低）。
- **L4 口径修复（P1-4b，配套 quiz.py 两处，冒烟全绿为门槛）**：
  - `_next_question` 生成题（LLM 路径与本地题路径）返回前，把 `{question, options, source}` 写入 `quiz_session.pending_q`（tx）；
  - `answer()` 落 question_log 时从 `pending_q` 取 `source` 并入条目、清空 `pending_q`；老会话 pending_q 为 NULL 时缺省 `llm`（老数据本就失真，判读从上线日起算）。
  - 效果：`quiz_question_llm_rate` 首次反映真实出题来源构成；9/16~上线日的该指标作废口径披露于迭代日志。
- **测试**：pytest 断言 log_call 落 model；quiz 链冒烟后 cost_close 的 `quiz_question_llm_rate` 可为 <1.0（造一道本地题即证）。

### P1-5 单会话链路面板（CCR Agent 观测极简版）

- 模板抽公共 `app/templates/admin/base.html`（head/样式/nav，Jinja2 原生 extends，无构建链）；`llm.html` 改继承，新增 `sessions.html`＋`trace.html` 同源样式。
- 路由（均 require_basic＋audit 留痕 `llm_trace_view`）：
  - `GET /admin/llm/sessions`：quiz_session 近 20 条（id/state/步数/结果菜名/result.source/local_reason/anon_id 前 12 字符截断显示）；
  - `GET /admin/llm/session/{sid}`：单会话 trace——question_log 逐题时间线表（step/问题/选项/来源徽章 llm|local/tags/dim）＋result 摘要（菜名/source/local_reason）。数据全在库（0005），纯渲染。
- 入口：sessions 列表页从看板明细区旁加链接；判读场景＝「为什么这题本地兜底」一眼定位（P1-4b 后 source 可信）。

**批次二验收**：pytest＋smoke 全绿（看板断言扩：小时桶 SVG 存在、`f_task=finalize` 筛选 200、sessions/trace 页 401/200、明细含 model 列头）；`recalc_metrics.py --check` 核对新 metric 键（disk_pct/db_size_mb/quiz_finalize_reasons 等是否需入其清单，实施时对齐）；生产 0008 预演记录归档 ops-private。

## 5. 批次三 P2：健康与自愈

### P2-1 LLM 供应商连通性检测（CCR「连通性检测」，拍板 #3：不计熔断）

- `service.py` 新 `ping()`：对 `primary/glm/qwen` 三路由各发一次最小 completion（prompt「回复 ok」，`agent='app.admin'`, `task='ping'`，走网关既有超时/重试/JSONL 留痕）。model 取值：primary=config `llm.model`；glm/qwen 读新 env `GLM_MODEL`/`QWEN_MODEL`（.env.example 补名；缺省值实施时对 ADR-004 附录备选模型名核定）。
- **落痕选型**：结果写 `audit_log`（action=`llm_ping`，detail=三路由 {ok,latency_ms,error_class} JSON）——**不落 llm_calls**：scene 列 CHECK(batch|cold_start) 不含诊断用途，expand-only 禁改 CHECK；且天然实现「不计熔断/不入月成本口径」（三路由×~$0.01/次手动触发，费用影响披露：月 $40 口径微幅低估，可忽略）。
- 端点两个：`POST /api/admin/llm/ping`（Bearer，返回 JSON）＋`POST /admin/llm/ping`（Basic，SSR 表单提交后 303 回看板——纯表单导航零 JS）；60 秒节流（查最近 audit 时间戳，防连点）。
- 看板概览卡加「路由健康」KPI：读最近一条 `llm_ping` audit 渲染三徽章（绿/红＋延迟，无记录显「未测」）＋「Ping」提交按钮。**只探测不切换**——路由决策与降级链零改动（AGENTS.md：主供切换拍板权归人）。
- 测试：smoke 断言 200＋JSON 键齐全（dev/冒烟环境 provider=stub 时各路由返回 route_unconfigured，无真实外呼——结构断言即够）。

### P2-2 应用侧错误出口

- **500**：`main.py` unhandled handler（L56-64）在 stderr 外写 audit（actor `system:api`、action `app_error`、target=path、detail 仅 `{exc: 类型名}`——不落 query string/异常消息原文，脱敏从紧）；单日上限 50 条（查当日计数，超限只 stderr——防异常风暴刷爆 audit）。
- **429**：限流中间件拒绝分支（L68-75）UPSERT `daily_metrics` metric=`app_429_count`（db.tx 内读旧值+1 写回，原子；这是 web 进程写 daily_metrics 的首个键，cost_close 不写此键无冲突）。
- **日结与告警**：cost_close 聚合 audit `app_error` 当日计数写 `app_500_count`；告警两条——500>10 → P2「应用 500 偏多」、429>500 → P2（被刷信号）。
- 看板概览卡加「应用错误」KPI（500/429 当日值）。

### P2-3 周判读模板

- 新 `docs/execution/weekly-review-template.md`（私有正本，与判读实例同处）：L1 可用性/L2 性能/L3 成本/L4 能力质量/L5 业务映射五节固定盘面＋取数指引（overview JSON 键名）＋在案观察项区（P95 软超时、慢路径占比、磁盘水位、收口拒因）——v1.1 §5.2 承诺收口。
- 外部拨测不列本轮实施：跟备案号下发后的恢复清单走（`docs/execution/icp-checklist-20260915.md`）。

**批次三验收**：pytest＋smoke 全绿（ping 结构断言、app_error 落痕断言）；生产手动触发一次 ping 看真实三路由结果归档截图/文本入迭代日志。

## 6. 实施顺序与验收总表

| 序 | 内容 | 估时 | 门槛 |
|---|---|---|---|
| 1 | **P0-1 probe 修复＋兜底告警翻转去重**（独立 commit，可单独先发） | 0.5h＋测试 1.5h | test_probe 四锚全绿＋生产直跑真实出数 |
| 2 | P0-2 notify 收口＋sys 修复＋熔断 P2 通知 | 1.5h | 熔断去重通知测试绿 |
| 3 | P0-3 OB-12 磁盘/库告警＋指标 | 1h | smoke §6.5 扩键绿（注：上线即 P2 属预期） |
| 4 | P0-4 wrapper 入私有正本＋.env.example＋cron.md | 1h | ops-private 入档＋env 名与代码读取一一对齐 |
| 5 | P1-4 迁移 0008（model＋pending_q）＋贯通＋L4 口径修复 | 0.5 天 | /db-migration 规程全项（副本预演/冒烟/recalc 对齐） |
| 6 | P1-1 小时桶＋P1-2 筛选＋P1-3 补图＋P1-5 trace（含 base 模板重构） | 1 天 | 看板断言扩项全绿＋公共面 diff 为零 |
| 7 | P2-1 ping＋P2-2 应用错误出口 | 0.5 天 | ping 结构断言＋app_error 留痕断言 |
| 8 | P2-3 周判读模板 | 0.5h | 模板五节与 overview 键对齐 |

- 发布节奏：序 1 可单独 hotfix；序 2-4 合为批次一发布；序 5-6 批次二；序 7-8 批次三。每批走 `/release` 规程，api＋admin 双容器重建（admin 面改动必同步重建 admin 容器——既有教训）；cron 入口 `python -m app.cron` 不变，宿主 crontab 零改动。
- 里程碑判读：批次二上线后看板即为「工作台形态」（实时概览＋当日趋势＋筛选日志＋会话 trace）；批次三补齐健康探测与自愈信号。

## 7. 风险与回滚

| 风险 | 评估 | 对策 |
|---|---|---|
| probe 修复后首次真实探活可能触发真 P1＋自动兜底 | 设计内（三试＋对照机制 9-13/9-15 已加固）；持续态经评审 A 翻转去重，仅首日一次 | runbook §5.2.6 人工复核；深链不可用本就该兜底；用户面影响为零（§0 发现 B） |
| 磁盘告警上线即持续 P2（当前 82~90%） | 预期，等于把人工盯盘自动化 | 「磁盘 90% 升级待办」完成后自止 |
| 0008 迁移 | expand-only 两可空列，SQLite 元数据级变更、旧镜像可跑新 schema | 规程副本预演＋smoke 全量迁移＋tar 镜像回滚兜底 |
| quiz.py next/answer 改动触出题主链 | 全链冒烟覆盖（quiz_flow）＋pending_q 为纯增量字段 | 老会话 NULL 缺省 llm 兼容；出问题回滚 commit 即可（schema 列残留无害） |
| web 进程发 notify（P0-2）/写 daily_metrics（P2-2） | 出网面与 LLM 调用同向无新增暴露；写路径全走 db.tx | notify 失败仅 stderr；429 键与 cron 写键不相交 |
| base 模板重构致看板回归 | 冒烟已有 401/200/SVG 断言＋本方案扩项 | 回滚模板 commit 独立于数据层 |
| ping 费用 | 手动触发×3 路由×~$0.01，60s 节流 | 不入熔断/月口径已披露；按钮仅 Admin 面 |

## 8. 红线对照（自查）

双面物理分离（全部新端点挂 admin 面；公共面仅 main.py 加观测留痕，行为零改动）✓；SQLite 写一律 db.tx（notify 在 tx 外、audit/daily_metrics 写在 tx 内）✓；cron 只 INSERT/UPSERT daily_metrics 不改业务表 ✓；降级链语义零改动（probe/notify/看板/ping 均只观测；ping 只探测不切换路由）✓；LLM 硬预算红线不动（cap/超时原值；ping 不计入已拍板披露）✓；无 SPA 构建链/无 Webfont/零 JS（Jinja2 extends＋服务端 SVG＋纯表单 GET/POST）✓；prompt 不落库（prompt_hash 机制不变；audit detail 脱敏从紧——只 exc 类型名＋path）✓；依赖钉版（零新依赖）✓；拍板权归人（§0 四点已拍；vendor 对照仍「备料不启动」；出题主链改动已显式标注可裁示）✓；留档数据不触（execution 只新增模板文件）✓；commit message 公开化（IP/主机名不入，运维细节指 ops-private 中性坐标）✓。
