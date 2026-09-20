> 发布/回滚机制落地（T1.10 演练修正，2026-09-06）：build 必须 `GIT_SHA=$(git rev-parse --short HEAD) docker compose build api`（镜像 tag=git sha，§3.4 原设计）；回滚＝`GIT_SHA=<上一稳定sha> docker compose up -d api`（演练实测 11s）。切勿自造 tag 名——compose image 字段按 GIT_SHA 解析，未传时全为 dev 且无回滚能力。

> 口径声明（工程审查 W-16，2026-09-04）：全部指标日界＝UTC 日（代码 substr(ts,1,10)）；与宿主机排程时区的差异已被知晓——晚高峰（UTC+8）跨 UTC 日界对周级北极星影响可忽略，如需本地日界须连带改聚合器与熔断计数。

# cron 调度（落地方案 §1.1；宿主 crontab 或 cron 容器执行）

任务以 `python -m app.cron <task>` 运行（容器内 `uvicorn` 同镜像；本地用
`.venv/bin/python`，须带 `WTE_DB_PATH` 环境变量指向生产库卷）。

| 时刻（宿主机本地时区） | 任务 | 说明 |
|---|---|---|
| 02:00 | `aggregate` | 日表聚合（FR-19，闸门指标口径单一事实源） |
| 03:00 | `./scripts/backup.sh` | 备份（03:30 未绿→告警，§5.1；宿主 crontab 须设 `WTE_DB_PATH`/`BACKUP_DIR`/`AGE_RECIPIENT`） |
| 15:30 | `probe` | 深链探活（核心时段 17:30–21:30 前完成；全红且对照绿→自动全局兜底＋P1 占位） |
| 23:59 | `cost_close` | LLM 成本/用量日结＋Umami 游标对账（umami_lag） |
| 周一 04:00 | `batch` | 批产管道（U2 未定稿＝合成占位批，staged；人工抽检后经 Admin `/api/admin/batch/{id}/activate` 激活） |

crontab 示例（VPS 部署后启用；当前 X5 阻塞＝占位）：

```
0  2 * * * cd /srv/app && WTE_DB_PATH=/data/app.db .venv/bin/python -m app.cron aggregate >> /data/logs/cron.log 2>&1
0  3 * * * cd /srv/app && WTE_DB_PATH=/data/app.db BACKUP_DIR=/data/backups ./scripts/backup.sh >> /data/logs/cron.log 2>&1
30 15 * * * cd /srv/app && WTE_DB_PATH=/data/app.db .venv/bin/python -m app.cron probe >> /data/logs/cron.log 2>&1
59 23 * * * cd /srv/app && WTE_DB_PATH=/data/app.db .venv/bin/python -m app.cron cost_close >> /data/logs/cron.log 2>&1
0  4 * * 1 cd /srv/app && WTE_DB_PATH=/data/app.db .venv/bin/python -m app.cron batch >> /data/logs/cron.log 2>&1
```

| 03:45 | 宿主 crontab | JSONL 14 天清理（docker exec 容器内 `/srv/app/app/logs/`，文件操作非表写不触 cron 只 INSERT 红线） |

| wrapper 正本 | 私有 | `docs/ops-private/bin/cron-run.sh`（宿主实装版入档；告警 env＝SERVERCHAN_SENDKEY/NTFY_TOPIC 任配其一） |
