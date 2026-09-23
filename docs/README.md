# docs/ 知识索引（L5 · Agent 自取）

> 基座 v1.0 · 2026-09-04。规则本体在根级 `AGENTS.md`＋`app/AGENTS.md`＋`.zcode/commands/`；本页只做地图，不含规则。

## 阅读顺序（新会话建议）
1. 根级 `AGENTS.md`（常驻须知）→ 2. 本页挑所需 → 3. 改代码前 `app/AGENTS.md` → 4. 领域操作走 `/release`、`/db-migration`、`/incident`。

## 目录结构

```
docs/
├── README.md    # 本地图
├── adr/         # ADR-001~005 架构决策记录
├── product/     # 产品线：立项提案、规划、路线图、访谈素材、美食分类图谱（维度树蓝本）
├── tech/        # 技术线：实施方案、CI/CD、LLM 接入研讨、LLM 监控×2（基础＋工作台化）
├── design/      # 设计线：语境卡→方向→规格→红队评审＋hifi 高保真原型
├── eval/        # 评测：LLM golden set（30 出题用例）
└── archive/     # 历史版本（v1~v4 旧文档）
```

> 执行归档（迭代日志/事故取证/判读）与私有运维注记在嵌套私有仓跟踪（`docs/execution/` 等三棵子树），不在公开树——双正本机制见 `docs/tech/ci-cd-plan.md` §2.3。

## ADR（方案级决策，改对应区域前必读；文件在 `adr/`）
| ADR | 主题 | 一句话结论 |
|---|---|---|
| adr-001 | 技术栈深度评估 | 1 人＋AI 产能定栈；统计结论是唯一交付物 |
| adr-002 | 载体与组装 | 裁 E：H5＋自部署组件＋无推送 |
| adr-003 | 形态×栈终评 | A/C 差 0.8%＜15%，W1 D6 终裁，C 兼任法定兜底；两结局均 Python |
| adr-004 | LLM 供应商 | 初裁 MiMo；**2026-09-04 修订：qwen3.8-flash 主供**（owner 拍板「文本模型选用qwen」，晚高峰复测＋收敛性基准＋PoC-2 质量三组数据支撑）；MiMo 降第二 |
| adr-005 | 载体重评＋M3 重定义 | 全程 P-c（微信外浏览器）＋PWA；M3＝M2 队列深化，公测放量裁撤 |

## 文档地图
- **技术**（`tech/`）：`tech/implementation-plan.md`（v3.1）、`tech/technical-requirements.md`（TRD v2，FR/HC/SC/SUP/RSK 编号源）、`tech/llm-integration-discussion.md`、`tech/llm-monitoring-plan.md`（v1.1 已完成——五层指标＋Admin 看板＋告警）、`tech/monitoring-workbench-plan.md`（监控 v2 工作台化 v1.1，2026-09-20 评估通过已冻结待实施——probe 实伤修复＋告警翻转去重/告警闭环/看板工作台化/LLM ping）、`tech/ci-cd-plan.md`（GitHub CI/CD 方案 v1.5，2026-09-17 定稿未实施——公开仓脱敏/嵌套仓双正本（白名单 ignore＋切换原子序＋本地滞留物 ignore 补齐＋clean -x 禁令）/备案期断言分层/两期上线/待拍板项在内）
- **设计**（`design/`）：`../DESIGN.md`（tokens 权威）＋ 四段流 `design/design-brief.md` → `design/design-directions.md` → `design/design-system.md` → `design/design-review.md` ＋ `design/hifi/index.html`（高保真原型；本地预览 `design/serve.py`）
- **归档旧版**：`archive/`（v1~v4 历史版本文档）

## 高频查询
- 定时任务与排程 → `scripts/cron.md`
- 备份/恢复演练 → `scripts/backup.sh`、`scripts/restore-drill.sh`
- 指标口径与独立复算 → `app/cron.py` 头注、`scripts/recalc_metrics.py`
- 事件枚举（FR-15）→ `app/events.py`＋规划 §3 In-6
