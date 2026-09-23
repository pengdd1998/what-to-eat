# 吃什么 · what-to-eat

> 30 秒收口的晚餐决策工具——几道轻松的选择题，给一个能点的菜。
> 🌐 [chishenma.top](https://chishenma.top)

## 这是什么

晚饭不知道吃什么？刷外卖平台半小时还是选不出来。「吃什么」用 **5~8 道单选卡牌**（品类大类→细分→口味，逐层收敛）把决策压到 **30 秒内**，最终给出一道具体菜＋一句口语推荐语，点了「就吃这个」就完事。

核心特性：

- **维度树导航式收敛**——LLM（qwen3.8-flash）从引擎计算的可用维度集中选维度出题，品类大类→小类→主菜逐层收窄；引擎持有约束状态机（选项 tags 累积＋同支相容守卫＋根维度覆盖校验），结构上杜绝「选了带汤主食又推荐盖饭」式上下文漂移
- **味觉记忆**——每次答题路径与收口结果沉淀为个人口味画像（显式反馈 ±3 分／隐式选择 +1 分加权），用得越多收敛越快（画像充分后 3~4 问收口）
- **环境感知**——时段场景（早/午/下午茶/晚/宵夜）＋实时天气（IP→城市→Open-Meteo，档位化注入：天热引导清爽、下雨引导热汤）
- **降级链是产品原则**——LLM 不可用/超预算/池未命中 → 本地菜库兜底＝功能降级可用（source 单列观测），不算故障
- **合规内建**——匿名代号＋口令恢复（无注册无手机号）、禁健康/减脂表述双层拦截、prompt 脱敏（prompt_hash）

## 技术栈

FastAPI + SQLite(WAL) + Jinja2 SSR 单体——无 SPA 构建链、无 Webfont、动效 CSS-only；Docker Compose 双面部署（公共面 api + 回环 Admin 面）；零 JS 前端（原生 fetch + CSS 卡牌动效）。

```
app/
├── core/       基础设施：db/ratelimit/events/umami/util/audit/notify/config
├── llm/        模型域：gateway（唯一 HTTP 出口＋厂商方言分派）＋service（双熔断）
├── providers/  环境上下文：env_ctx（场景/天气）＋ipsearch（IP 归属，vendored）
├── domain/     业务引擎：dimensions（维度树）/quiz（收敛）/strategy/memory/identity/jump
├── web/        路由层：pages/quiz_api/identity_api/go/misc_api/llm_dash（看板）
├── cron/       定时任务：aggregate/probe/cost_close/batch/backup
└── templates + static   零 JS SSR 前端（昼/夜主题）
```

**测试**：pytest 60 项（含维度树 golden set 30 用例——树改动即回归）＋冒烟 45 断言全链路（CI 六 job 常驻）。

## 快速开始

```bash
# 本地跑（自动建 venv + 临时库，起公共面 8100 + Admin 面 8103 全链路断言）
./scripts/smoke_local.sh

# 或直接起服务
docker compose up -d --build api
```

环境变量见 `.env.example`（LLM_BASE_URL/LLM_API_KEY 等；密钥只进 `.env`，禁入 git）。

## CI/CD

GitHub Actions 双 workflow：

- **CI**（push/PR）：gitleaks 全历史／树卫生门禁（基础设施字面量正则＋白名单）／pytest／冒烟／迁移两遍幂等／compose 校验
- **CD**（手动 dispatch）：CI 绿门禁 → tar→scp→VPS 本地 build（防墙设计）→ marker 重建面判定 → health 分层断言（回环双面恒跑＋公网层可开关）→ 失败回滚

## 文档地图

| 线 | 内容 |
|---|---|
| `docs/product/` | 产品规划 v4.1、路线图、立项提案、**美食分类图谱**（维度树领域蓝本） |
| `docs/tech/` | 实施方案 v3.1、CI/CD 方案、LLM 监控方案×2（基础＋工作台化） |
| `docs/adr/` | ADR-001~005（技术栈/载体/形态终裁/LLM 供应商/载体重评） |
| `docs/design/` | 设计系统「街角灯箱」＋ hifi 原型 |
| `docs/eval/` | LLM golden set（30 出题用例） |

细节：`docs/README.md`（知识索引）。

## License

个人项目，未设开源协议。
