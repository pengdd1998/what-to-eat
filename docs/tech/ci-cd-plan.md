# GitHub CI/CD 落地方案 v1.5

> 2026-09-17 立项 · 源＝owner 需求（推送 GitHub 远程仓库＋GitHub Actions CI/CD，只出方案不操作）
> 状态：**P0-P2（阶段 1-5）已实施完成**（2026-09-17，owner 指令「实施最新方案」＝按方案推荐值执行：备案时序选 B/双正本按 §2.3/排除清单按 §2.2/alert 二期不做）；CD v2 待平台时序
> v1.5 变更（2026-09-17 四轮评审 D4 采纳）：`mv .git .git-archive-bak` 后巨型档案目录未入外层 ignore——滞留 git status 之外，本地误 `git add -A` 会把全量历史对象（含敏感叙事）staged 进公开仓；修复＝切换原子序第 4 步外层 .gitignore **一次补齐全部本地滞留路径**（bak／poc／.impeccable／.video_agent），bak 亦可直接移出工作区（§2.3）
> v1.4 变更（2026-09-17 三轮评审 D1–D3 采纳）：①D1 内层仓白名单 ignore 定稿——`/*` 锚定根层式三行（**评审原建议的无斜杠 `*` 写法不工作**：它按 basename 匹配所有深度，`!` 规则救不回子文件），防 `git add -A` 误卷公开子树（§2.3）；②D2 阶段 2 切换原子序——「先验证推送成功→再动本地 .git→移走不删除→双远程全绿才清理」，任一步失败即停在可用形态（§2.3）；③D3 `git clean -x` 全层级禁令——根目录执行＝三棵敏感子树＋内层仓一次清空，`docs/` 内执行＝清掉外层跟踪子树；入 AGENTS.md 纪律＋`.zcode` 守卫 hook 候选拦截（§2.3/§2.4）
> v1.3 变更（2026-09-17 二轮评审 N1–N4 采纳）：①**N1 单工作区双正本落地机制**——嵌套仓设计定稿（§2.3：工作区＝公开仓 checkout，`docs/` 内嵌运维正本仓跟踪 execution/reverse/ops-private 三棵子树；私有侧双远程＝冻结全量档案仓＋滚动运维正本仓；路径零迁移，机制上杜绝漂移）；②N2 公开仓引用私有档用中性措辞（§2.4）；③N3 备案降级期版本区间记私有注记（§4/§8）；④N4 `CRON_WINDOWS` 以私有注记为源、GitHub Var 为投影（§6）
> v1.2 变更（2026-09-17 一轮评审采纳，五条全收）：R1 备案拦截期公网断言必红——health 拆基线/公网两层＋`skip_public_checks` 降级开关＋回环 admin 断言补位；R2 私有备份仓「强烈建议」→必做前置；R3 双正本分工（v1.3 补落地机制）；R4 四细节——ci-gate 超时预算／树卫生白名单集中配置／sudoers `visudo -c` 先行／cron 窗口撞车告警
> v1.1 变更（2026-09-17 owner 拍板「仓库性质＝公开」）：新增 §2 公开仓脱敏（历史策略／排除清单／脱敏改写／树卫生门禁）；本文档自身同步脱敏——基础设施字面量改由 Secrets/Vars 注入，具体值记于不入公开树的私有运维注记
> v1.0 背景：蓝本＝read-pal 仓库 `.github/`（五 workflow）＋ `ops/edge/README.md`（平台边缘手册）＋ `ops/edge/PLAN.md`（平台迁移计划，定稿未实施）；关联 ADR-002/005、`implementation-plan.md`（SUP-02）、AGENTS.md 架构红线

## 0. 一页总览

- **目标**：代码入 **GitHub 公开仓**（2026-09-17 owner 拍板）；CI 全自动验证，CD 手动触发、延续「tar→scp→VPS 本地 build」路径——VPS 在国内区拉不到 GitHub/GHCR，服务器本地 build 是防墙设计，保留；不用「Actions 推镜像＋VPS pull」路线。
- **发布节奏**：CI 绿 → 真机 e2e（人肉，Mac＋USB＋CDP，`scripts/e2e_mobile.py`）→ 手动 dispatch 部署。不做 every-push 自动部署（真机验收环节在中间）。
- **公开仓三支柱**：净化快照起点（全量历史不外推，§2）；公开树零基础设施字面量（值走 Secrets/Vars＋私有注记）；CI 常设树卫生门禁防再引入（§3）。
- **双正本**：代码正本＝公开仓、运维正本＝私有仓，单工作区嵌套仓机制落地（§2.3）。
- **两期上线**：CD v1 不依赖平台迁移、随时可上；CD v2（边缘片段收敛）绑定平台 edge-caddy 迁移的阶段 D-1。
- **一句话红线**：部署只碰 `api`/`admin` 两个具名服务；永不裸 `up`、永不 `--remove-orphans`、永不触碰平台层 compose、永不 `system prune -af`。

**现状基座**（2026-09-17 取证；字面量值见私有运维注记，不入公开树）：

| 事实 | 内容 |
|---|---|
| 版本管理 | 无 git remote，从未推送；部署一直走 tar＋scp 不走 git |
| 生产 | 国内区 VPS，docker compose：api（回环）＋admin（回环），SQLite（`api-data` 卷） |
| 公网状态 | **备案审核中——腾讯云拦截期（302 阻断页，窗口期波动）**，公网断言当前不可作为部署判据（§4 基线/公网分层由此） |
| 混部 | 同机 read-pal（蓝本仓，自带全套 GH Actions）＋anynote；平台层（PG/Redis/MinIO＋edge-caddy）**定稿未实施** |
| 生产边缘 | 仍是本项目 compose 的 `edge` 容器（占 0.0.0.0:80/443）；服务器侧 Caddyfile 已被手改为三站点（含本项目公网 403 策略） |
| 域名 | 生产实际域名与仓库 `deploy/Caddyfile` 存在漂移（仓库值为已弃旧域）；CD v2 片段以割接时现网值为准，经 Var 注入 |
| 平台契约 | 别名 `wt-api` 已登记；片段落点 `sites/wte.caddy`；validate＋reload、禁 restart、禁对平台层任何 compose 操作 |

## 1. 路线图（六步，两处与平台交接）

| # | 阶段 | 内容 | 依赖 |
|---|---|---|---|
| 1 | 公开化清障 | ①gitleaks 全历史扫描（防历史夹带密钥）；②敏感内容分置（§2 排除清单＋脱敏改写＋私有运维注记落位）；③owner 确认排除清单与脱敏度 | — |
| 2 | 双仓推送 | **必做前置**：先推私有侧（§2.3 双远程＝冻结全量档案仓＋运维正本仓 fresh init）；再推公开净化快照；**嵌套仓机制随本步生效，按 §2.3 切换原子序实施**，本步完成即正本切换点 | 1 |
| 3 | CI 上线 | 纯只读验证＋树卫生门禁，零风险 | 2 |
| 4 | 部署通道 | VPS 建部署账号＋sudoers 白名单（`visudo -c` 先行）＋专用 SSH key；GitHub 配 Secrets/Vars | 2，与 3 并行 |
| 5 | CD v1 | 先 `dry_run` 干跑核对重建判定，再实跑（备案期按 §4 开关降级公网断言）；compose 携带 edge-net 改动（＝平台阶段 A0） | 3＋4＋R1 时序拍板（§8） |
| 6 | CD v2 | 平台迁移 A＋B 完成后：清理旧边缘定义、接管路由片段＋收敛钩子（＝平台阶段 D-1） | 5＋平台时序 |

## 2. 公开仓脱敏（仓库性质＝公开，2026-09-17 拍板）

### 2.1 敏感分级与取证结论（2026-09-17 全仓扫描）

| 级 | 定义 | 取证结论 |
|---|---|---|
| A 硬密钥 | 密钥/凭据字面量 | **树内零命中**（全部 env 注入，`.env` 已 gitignore）；gitleaks 全历史扫描仍必跑（历史 commit 保险） |
| B 基础设施拓扑 | VPS IP、ssh 别名、部署路径、端口暴露细节、平台层弱点 | IP 在 `docs/execution/`（56 个跟踪文件）与 `docs/reverse/evidence-pack.md` 反复出现；`scripts/llm-dashboard.sh` 含 ssh 隧道逻辑 |
| C 运维内档 | 迭代日志、PoC 报告、留档数据、事故记录、ICP 清单、agent 命令 | `docs/execution/`（含 `data/` 留档 JSONL/CSV/截图）、`docs/reverse/`、`.zcode/`（5 个文件在 gitignore 生效前已被跟踪）、`.zcode/commands/release.md` 含公网验证清单 |
| D 产品自身域名 | 对外服务域名 | 产品门面，DNS 本就公开——**可公开**；历史换域叙事保留（ADR-005） |
| E 用户素材 | 访谈/调研 | `user-interview-material.md` 已自证「假设级素材、无真实用户数据」——**可公开** |
| F 工具产物 | agent/设计工具缓存 | `.impeccable/`（31 个文件）、`.video_agent`——无公开价值 |

### 2.2 处置清单

| 对象 | 级 | 处置 |
|---|---|---|
| `docs/execution/` 全部（含 `data/`） | B＋C | **不入公开树**；随运维正本仓持续跟踪（§2.3，只增不改纪律不变） |
| `docs/reverse/` 全部 | B＋C | **不入公开树**；随运维正本仓持续跟踪 |
| `.zcode/` 全部 | C | **不入公开树**（`git rm --cached` 收尾，gitignore 已有条目）；本地保留（工作区工具配置，不入任何远程） |
| `.impeccable/`、`.video_agent` | F | **不入公开树**＋补 gitignore |
| `scripts/llm-dashboard.sh` | B | **不入公开树**；迁入 `docs/ops-private/bin/` 随运维正本仓跟踪（更新引用处） |
| `poc/` | C 低危 | 不入公开树（owner 可改判保留；保留本地则随 §2.3 切换原子序第 4 步补 gitignore） |
| `AGENTS.md` | B | **脱敏改写留公开树**：架构原则/红线保留；部署路径、隧道细节、cron 具体等运维细节瘦身，移入私有运维注记（走纠偏 mini 流程） |
| `docs/tech/` 各方案文档 | B | **脱敏改写留公开树**：机制可公开，主机/路径/端口字面量以 `<VAR>` 占位（本文档即此形态） |
| `deploy/Caddyfile`、`docs/README.md` 地图 | B 轻 | CD v2 时 Caddyfile 归档删除；地图在净化快照中裁掉指向被排除目录的行 |
| `PRODUCT.md`、`docs/adr/`、`docs/design/`、`docs/eval/`、`app/`、`tests/` 等 | D/E/无 | 保留（域名属产品门面） |

**私有运维注记**（新设，不入公开树，路径 `docs/ops-private/`）：承接被抽出公开树的具体值——主机/端口/部署路径/平台片段目录/备份与 crontab 细则/看板访问流程/备案状态与断言开关现值＋降级期版本区间。它随运维正本仓跟踪（§2.3），与公开树互为表里（公开树＝机制，注记＝值）。

### 2.3 历史策略、双正本分工与嵌套仓落地机制

**历史策略**

- **公开仓以净化快照为起点**：现有全量历史不外推——commit message 即含运维叙事（IP/路径/排查细节曾直接写入），逐条重写不可行也不值得。快照形态：单 initial commit（首选，简单）或里程碑化数 commit（owner 定）。

**私有侧双远程（必做前置，评审 R2）**

| 仓 | 语义 | 生命周期 |
|---|---|---|
| **冻结全量档案仓** | 现全量历史一次性推送（含敏感 commit message 叙事的完整备份） | 切换后**只读封存**，永不再提交 |
| **运维正本仓** | 承接 `docs/execution/`、`docs/reverse/`、`docs/ops-private/` 的持续滚动更新 | fresh init，历史自切换点起算（切换前历史在冻结档案仓；subtree split 连续史属可选增强，刻意取简） |

**单工作区双正本＝嵌套仓机制（二轮评审 N1 落地设计，阶段 2 实施时一次成型）**

```
工作区（＝公开仓 checkout，代码正本）
├── app/ migrations/ …            → 外层跟踪（公开仓）
├── docs/
│   ├── .git/                     → 内层运维正本仓（remote＝私有运维仓）
│   ├── product/ tech/ …          → 外层跟踪（公开仓）
│   ├── execution/ reverse/       → 内层跟踪（私有）
│   └── ops-private/（含 bin/）    → 内层跟踪（私有）
└── .gitignore                    → 外层新增：docs/execution/、docs/reverse/、docs/ops-private/、docs/.git/
```

- **机制**：工作区根＝公开仓；`docs/` 内嵌独立 git 仓，跟踪且仅跟踪三棵敏感子树。外层 gitignore 四行与排除清单天然咬合——两仓跟踪集互斥，同一工作区各司其职，**机制上杜绝双正本漂移**（二轮评审 N1 的核心诉求）。
- **内层白名单 ignore（三轮 D1）**：`docs/.gitignore`（内层仓跟踪）＝
  ```
  /*
  !/execution/
  !/reverse/
  !/ops-private/
  ```
  锚定根层的白名单式——`/*` 只匹配 docs/ 根层条目，三行 `!` 重含三棵子树（其内容不再被任何规则命中）。**不可用无斜杠 `*`**：它按 basename 匹配所有深度，`!/execution/` 只救回目录本身，目录内文件仍被 `*` 吞掉。白名单式＝防呆：即使 `cd docs && git add -A` 误操作，也只会碰三棵子树，product/tech 永不入私有仓。
- **切换原子序（三轮 D2＋四轮 D4）**：阶段 2 的本地重构按「**先验证、后动 .git、移走不删除**」固化，任一步失败即停在该步、本地形态始终可用：
  1. 推全量历史→冻结档案仓（不动本地任何东西）；
  2. `git ls-remote` 核验远端 refs 与本地一致；
  3. `mv .git .git-archive-bak`（移走而非删除，本地保留全量副本；**备选＝直接移出工作区**至盘内同级路径，则第 4 步免 ignore 该项）；
  4. 根目录 `git init` 净化快照，**外层 .gitignore 一次补齐全部「留在本地但不入公开树」的滞留路径**——`.git-archive-bak/`（四轮 D4：巨型档案目录若不被 ignore，除 git status 永久噪音外，本地误 `git add -A` 会把全量历史对象——含敏感叙事——整个 staged 进公开仓）＋`poc/`＋`.impeccable/`＋`.video_agent`＋三棵敏感子树＋`docs/.git/` 四行→推公开仓→核验；
  5. `docs/` `git init` 内层仓＋落白名单 ignore＋add 三棵子树→首推运维正本仓→核验；
  6. 双远程核验全绿后才可清理 `.git-archive-bak`（**建议永久保留＝第三重保险**；第 3 步选移出工作区则本步免）。
- **路径零迁移**：迭代日志/留档/注记仍写在原路径；`app/` 代码改动提交外层（公开仓），运维档更新在 `docs/` 内提交推送内层（私有仓）。既有工具（`.zcode` 路径守卫 hook 等引用留档路径）因路径不变全部继续有效。
- **提交纪律**：运维档更新随写随提交（至少日终推送）。
- **破坏性操作禁令（三轮 D3）**：任何目录层级**禁 `git clean` 带 `-x`**——根目录执行会连 ignore 内容一起删（三棵敏感子树＋`docs/.git` 内层仓**一次清空**，且这些内容不在公开仓、无远程以外的其他副本）；`docs/` 内执行则会清掉外层跟踪的 product/tech。配套陷阱：`cd docs` 后执行 git 命令命中的是内层仓（`git status` 只见三棵子树）。两条均入 AGENTS.md 纪律，并列 `.zcode` 路径守卫 hook 候选拦截规则（Bash matcher 扩展）。公开仓 CI/树卫生跑在公开 checkout 上，不含 `docs/.git`，无影响。

**双正本分工（切换点＝阶段 2 完成）**：此后**代码正本＝公开仓**（日常开发、CI/CD、GIT_SHA 基准），**运维正本＝私有仓**（`docs/execution/`、`docs/reverse/`、`docs/ops-private/` 持续滚动——迭代日志本就含运维叙事，永不在公开仓写）。之后的开发 commit message 遵守公开化纪律（§2.4）。

### 2.4 持续纪律

- **commit message 公开化**：结论/出处/任务号惯例保留；基础设施字面量（IP/路径/主机名）与运维敏感细节不入 message（公开仓里 message 永久可见）。此条入 AGENTS.md（纠偏 mini 流程）。
- **公开仓引用私有档用中性措辞**（二轮评审 N2）：「出处：iteration-log W3 D4」类坐标保留（本就是 owner/agent 内部索引），但不展开引用其敏感内容；公开文档不出现「见私有注记」之外的内部值。随上一条一并入 AGENTS.md。
- **嵌套仓操作纪律（三轮评审 D1/D3，细则见 §2.3）**：内层仓白名单 ignore 随机制落位（`/*` 锚定式）；任何层级禁 `git clean -x`；`cd docs` 后 git 命令命中内层仓。与上面两条一并入 AGENTS.md。
- **CI 树卫生门禁**（§3）：每次 PR/push 扫公开树，正则拦 B 级模式（IPv4 字面量、已知 ssh 别名、内网路径前缀等），白名单豁免（如 `app/providers/ipsearch.py` 的测试 IP、`127.0.0.1`）。模式与白名单集中在单一配置文件维护，新豁免＝一行 PR；**误红优于漏放**。
- **GitHub 加固**：main 分支保护＋必过 CI；`workflow_dispatch` 仅协作者可触发（fork PR 天然无 secrets 权限）；各 workflow `permissions:` 最小化（CI 只读、deploy 仅部署所需）；Actions 对公开仓免费额度（顺带利好）。

## 3. CI 设计

**触发**：PR→main、push→main；`concurrency` 允许取消。Python 版本钉与 Dockerfile 基镜像一致（依赖钉版红线，防本地/容器/CI 三方漂移）。

| Job | 内容 | 备注 |
|---|---|---|
| secret-scan | gitleaks，`fetch-depth: 0` 全历史，命中即红 | 独立 workflow、零 secrets 依赖 |
| **树卫生** | 正则扫公开树 B 级模式（IP/别名/路径前缀），白名单豁免 | §2.4 纪律的执行器；白名单集中配置文件维护 |
| pytest | 53 项（requirements＋requirements-dev；golden 用例读仓内 jsonl） | 测试资产随仓 |
| 冒烟 | `./scripts/smoke_local.sh`（双面断言） | 与 runner Python 版本有摩擦时降级为 pytest＋smoke.py 断言段 |
| 迁移完整性 | 空 SQLite 按文件名序跑完全部 `migrations/*.sql` 两遍 | 验 expand-only 链幂等 |
| compose 校验 | `docker compose config -q` | external 网络 edge-net 不存在时容忍该子项 |
| 片段语法 | `caddy:2` 容器内 `caddy validate docker/edge.caddy` | CD v2 阶段文件存在后启用 |
| 容器内验证（可选） | requirements.txt 变更时构建镜像、容器内跑 pytest | `paths` 过滤，作依赖升级门禁 |

## 4. CD v1（部署主体）

**触发**：仅 `workflow_dispatch`，inputs：`dry_run`（默认 false）＋**`skip_public_checks`（默认 false；备案拦截期临时 true，§health 分层）**。`concurrency` **不允许取消**——半途中止的部署会留下混合版本容器。

**前置 `ci-gate` job**：`gh run watch` 等**同一 commit** 的 CI 跑绿；**带超时预算**（watch 15 分钟＋job `timeout-minutes` 兜底，超时＝gate 失败、可重新 dispatch）——防止挂起占用 concurrency 组阻塞后续部署（评审 R4）。

**零字面量原则**：deploy 脚本（入公开仓的 workflow 文件）不出现任何主机/路径/端口/域名值，全部经 `secrets.*`/`vars.*` 注入。

**SSH 脚本序**（VPS 侧执行；runner 打包排除 `.git`/`.venv`/`tests`，清 `._*`；tar 清单含 `docker/edge.caddy`）：

1. **preflight 守卫**：可用内存、磁盘检查（阈值按同机混部实测量定，计入平台层常驻基线；实机核定量记私有注记）；磁盘低先 `docker builder prune --filter until=24h` 再复查，仍低中止；**cron 窗口撞车告警**（命中 `CRON_WINDOWS` Var 配置的聚合/批产窗口仅告警不阻断——cron 自带失败告警，二期可升级文件锁互斥；评审 R4）。守卫兼作双项目部署的天然互斥。
2. **留旧包**：上一版 tgz 存为回滚兜底。
3. **解包**：`sudo tar xzf --overwrite` 到部署根（`<DEPLOY_PATH>`，Var 注入；属主非 root 必须 sudo），再清一次 `._*`。
4. **重建面判定**：与 `DEPLOY_MARKER`（上次**成功**部署的 SHA）diff，而非 HEAD~1——被取消的部署不推进 marker，整段区间不漏。`app/**`→重建 api；admin 模板/路由→重建 admin；compose/Dockerfile/requirements→双面。此项治「只建 api 致 admin 看板 404」旧伤。
5. **构建切换**：`GIT_SHA=$SHA docker compose build <服务>`＋`GIT_SHA=$SHA docker compose up -d <服务>`——**build 与 up 都必须带 GIT_SHA**（只传 build 会用旧镜像假成功）。只操作具名服务，绝不带 `--remove-orphans`。
6. **health 分层断言**（各 6 次×10s 重试；评审 R1 改造）：
   - **基线层（恒跑，备案期即部署判据）**：部署机回环 api health（version 含新 SHA）＋**回环 admin health**——双面面级覆盖，与重建面判定互为印证；
   - **公网层（`skip_public_checks=false` 时跑）**：`https://<域名 Var>/api/health` 200＋`/api/admin/x` 403（第三层防线在线）。**备案拦截期（302 阻断页、窗口波动）公网两项必红**——备案期 dispatch 显式带 `skip_public_checks=true` 降级；备案恢复后默认回全量，**首次全量跑即恢复验证**。降级期部署的版本未经公网验证，**降级版本区间随开关现值记私有注记**（§8 核实项 7，二轮评审 N3）——恢复首跑为最终态验证语义。
7. **失败回滚**：解回旧包、旧 SHA 重建、复验；仍失败输出人工介入指引并红。
8. **成功收尾**：写 marker（断言全过后才写）、`docker image prune -f`（仅 dangling，绝不 `-a`——不误伤同机邻项目留存镜像）、报磁盘占用。

**dry_run**：只做到解包＋打印「会重建 api：是/否、admin：是/否」即停，不碰容器。

**回滚主路径**＝重打旧 SHA 的 tar 包重建（git 历史在远程，永远可重打），不依赖旧镜像留存——与同机邻项目 deploy preflight 的 `system prune -af` 解耦；镜像 tag 回退仅作可选加速。另需与平台组明确：任何 prune 不得带 `--volumes`（会清生产 SQLite 所在卷）。

**CD v1 期 compose 收敛只做一半**：**加** `edge-net: { external: true }`＋api 服务 `aliases: [wt-api]`（＝平台阶段 A0 派给本项目的改动，容器重建闪断一次，是阶段 A 硬前置）；**不删** `edge` 服务定义——平台阶段 A 割接要靠它停旧边缘，删除必须排在割接＋48h 观察后。admin 面永不加入 edge-net（隔离＝回环＋token，公网可达性为零）；api 回环端口保留（SSH 隧道备用入口，平台手册明示回环绑定合法）。

## 5. CD v2（边缘片段收敛，＝平台阶段 D-1）

前置：平台 edge-caddy 迁移阶段 A（边缘割接进平台层）＋B（骨架/片段拆分，过渡片段由平台代管）完成。

- **清理 commit**（平台 A 后 48h 观察＋平台停旧边缘之后）：删 compose 的 `edge` 服务定义与两个 caddy 卷声明（证书数据平台已迁走，回退窗口由平台控制）；归档 `deploy/Caddyfile*`。
- **新增 `docker/edge.caddy`**（承接平台代管的过渡片段，语义＝现网平移，文件名 `wte.caddy` 为平台计划钉死）：

```caddyfile
# what-to-eat edge fragment — 只写 site 块, 全局选项归骨架（平台 ops/edge/README.md）
<域名（Var 注入，随备案结果可换）> {
	encode gzip
	# 第三层防线：公网 /api/admin 一律 403（admin 真身仅宿主回环）
	handle /api/admin/* {
		respond 403
	}
	reverse_proxy wt-api:8000
}
```

  - 片段无需 `header_up X-Real-IP`：应用读 X-Forwarded-For（`app/web/support.py` `_client_ip`→uvicorn `--proxy-headers` 解析），Caddy 反代默认自动设置 XFF。蓝本仓需要显式回传是因其应用读 X-Real-IP——两者不同，换框架前需复核此条。
  - 无流式接口（SSR＋JSON），不需 `flush_interval -1`。
- **收敛钩子**（diff 命中 `^docker/edge\.caddy$` 时；片段目录 `<EDGE_SITES_DIR>` 经 Var 注入）：

```bash
cp docker/edge.caddy <EDGE_SITES_DIR>/wte.caddy
docker exec edge-caddy caddy validate --config /etc/caddy/Caddyfile \
  && docker exec edge-caddy caddy reload --config /etc/caddy/Caddyfile
```

  - validate 失败必须让部署红（别吞）——旧配置仍在服务，最坏＝「没生效」而非下线；首次执行人工做一次。
  - api/admin 容器重建**不触发任何边缘动作**（别名按连接拨号解析、重建自愈），两条线正交。
  - 回滚时在 `up -d` **之后**回收敛片段并 `|| true`（回滚期片段失败不阻断回滚、仅告警——与主流程「validate 失败必红」不对称是刻意的）。

## 6. Secrets 与服务器权限

**Secrets/Vars**（值记私有运维注记；GitHub Variables/Secrets 均不对公众可见，读取需协作者权限）：

| 项 | 类型 | 用途 |
|---|---|---|
| `VPS_HOST`/`VPS_PORT`/`VPS_USER`/`VPS_SSH_KEY` | Secret | 部署连接（专用 key，独立于邻项目，可单独吊销） |
| `DEPLOY_PATH` | Var | 部署根路径 |
| `WTE_DOMAIN` | Var | 公网验证域名（备案换域只改 Var） |
| `EDGE_SITES_DIR` | Var | 平台片段目录（CD v2 起） |
| `CRON_WINDOWS` | Var | VPS cron 窗口表（preflight 撞车告警用）——**私有注记为源、本 Var 为投影**，改 cron 时同步（二轮评审 N4；影响面仅告警精度） |

**`GO_SECRET`/`ADMIN_TOKEN`/`LLM_API_KEY` 永不入 GitHub**——只活在 VPS `.env`，部署流程不触碰（tar 亦不含 `.env`）。

**sudoers 白名单**（精确到命令，路径值见私有注记）：tar 解包部署根；本项目 compose 的 build/up；`cp` 片段到平台片段目录；`docker exec edge-caddy caddy validate/reload`。**编辑必须 `visudo`（或 `visudo -c` 校验先行）**——语法错误会锁死 sudo（评审 R4）。

**禁区**（写入 deploy 脚本注释与评审清单）：

- 不带服务名的 `compose up`、`--remove-orphans`（漂移的 edge 服务会撞平台边缘 80/443，全机站一起挂）
- 对平台层 compose 的任何操作、`restart edge-caddy`（平台组专属）
- `docker system prune -af` 及任何 `--volumes`（同机邻项目资产）
- 给被反代服务发布 0.0.0.0 端口（绕过边缘＝绕过 TLS/header/审计；回环绑定合法）
- 手改平台 `sites/` 下任何文件（下次部署静默覆盖）

## 7. 平台协调项

- **知会平台组 CD 已存在**：其风险登记表按「本项目无自动 CD、窗口好约」设计协调窗口，该假设在 CD 上线后失效（deploy 仅手动 dispatch，窗口天然可控）。
- 平台阶段 A 秒级割接窗口内，我方公网 health 检查会误红——约窗口或临时降噪（备案期本就走降级开关，两层窗口风险同机制处置）。
- A0 验收抄平台现成命令：`docker network inspect edge-net` 三组别名齐全。
- 平台层存量风险已知悉、由平台组处置中（细节不入公开仓，记私有注记）；本项目不消费平台数据面服务（SQLite），部署账号落同一台机器，时间线跟随平台。

## 8. 待办清单

**owner 拍板项**：

1. **备案期时序（评审 R1，实施前置）**：A＝等备案恢复再实跑 CD v1；B＝按 §4 开关备案期即上（推荐——断言默认全量、备案期显式降级为回环双面、恢复后首跑即全量验证，CD 上线不被备案窗口绑架）
2. **双正本与嵌套仓机制确认（评审 R3＋N1，机制已定稿于 §2.3）**：代码正本＝公开仓、运维正本＝私有仓，切换点＝阶段 2 完成
3. 净化快照的排除清单与脱敏度确认（§2.2 全表；含 `poc/` 去留、AGENTS.md/tech 文档瘦身幅度）
4. VPS 部署账号＋sudoers 白名单（改生产服务器状态；`visudo -c` 先行）
5. alert workflow（health 巡检＋digest＋部署失败即时告警）是否要——可选二期；边缘容器健康已由平台监控覆盖

**实机核实项**（CD 落地前一次性盘点，结果记私有注记）：

1. 80/443 现由谁持有（判断平台迁移实际进度，CD v2 时序随实况）
2. `edge-net`/`wt-api` 别名状态（平台 A0 是否已做）
3. 平台片段目录下 `wte.caddy` 是否已存在（判断平台 B 进度）
4. 数据层确认仍 SQLite（同机有现成 PostgreSQL，须排除历史手改——若已换库即架构红线变更，另走 ADR）
5. 备份保留代数（纳入磁盘守卫核算）
6. 平台层常驻后的内存/磁盘基线（守卫阈值定标）
7. 备案状态与公网断言开关现值＋**降级期版本区间**（私有注记滚动记录，恢复后回默认并清区间）

**实施前置与工作量**（两轮开发评审口径，2026-09-17）：二轮结论＝v1.2 已解决全部结构性问题、N1 机制已随本版定稿；实施前置＝拍板项 1–4 清零。工作量维持：阶段 1–4 约 0.5–1 天，CD v1 含 dry_run 演练＋首次人工核验约 0.5 天；CD v2 随平台时序不占当前。
