"""cron 任务入口（§1.1；容器内 `python -m app.cron <task>`，宿主 crontab 调度）。

- aggregate   02:00 日表聚合（FR-19）——闸门指标口径单一事实源，周报只读日表
- probe       15:30 深链探活（FR-14；全红且对照绿 → 自动全局兜底＋P1；全绿自动恢复）
- cost_close  23:59 LLM 成本/用量日结＋Umami 游标对账（SUP-03/04）
- batch       每周一 04:00 批产管道（T1.5）
- backup      03:00 备份＋完整性校验＋轮转（keep 14）

判读纪律（§4）：任何闸门判定必须同报 n——所有指标写 daily_metrics(n)。
北极星口径（§5/HC-10）：accept＋jump 双事件 server_ts 差 ≤60s。
"""
from .aggregate import aggregate
from .backup import backup
from .batch import batch
from .common import notify  # noqa: F401（外部复用：cron-run.sh 失败告警路径）
from .cost_close import cost_close
from .probe import probe

_TASKS = {"aggregate": aggregate, "probe": probe, "cost_close": cost_close,
          "batch": batch, "backup": backup}
