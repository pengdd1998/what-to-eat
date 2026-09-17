"""`python -m app.cron <task>` 的包执行入口（crontab 调度路径）。

阶段3②教训：CLI 写在 __init__ 的 __main__ 块对 `python -m 包名` 不生效——
包执行的是本文件。任务表与分发见 __init__.py。
"""
import json
import sys

from . import _TASKS

if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = _TASKS.get(task)
    if not fn:
        print("usage: python -m app.cron [aggregate|probe|cost_close|batch|backup]",
              file=sys.stderr)
        sys.exit(2)
    print(json.dumps(fn(), ensure_ascii=False, default=str))
