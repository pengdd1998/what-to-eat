"""cron/backup（阶段3拆分自 app/cron.py）。"""
import os
from datetime import datetime, timezone

from ..core import db
from .common import notify


def backup() -> dict:
    """03:00 每日备份（SUP-01）：.backup 在线一致性快照＋integrity_check＋轮转。

    容器内执行（/data 卷内落盘）；AGE_RECIPIENT 设置时叠加 age 加密输出
    （私钥仅存本人本地设备，禁入 VPS/git/备份介质，评审 9）。
    """
    import os
    import sqlite3
    src_path = os.environ.get("WTE_DB_PATH", "/data/app.db")
    bdir = os.environ.get("BACKUP_DIR", "/data/backups")
    keep = int(os.environ.get("BACKUP_KEEP", "14"))
    recipient = os.environ.get("AGE_RECIPIENT", "")
    os.makedirs(bdir, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    plain = os.path.join(bdir, f"app-{day}.db")
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(plain)
    with dst:
        src.backup(dst)
    dst.close()
    chk = sqlite3.connect(plain)
    ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
    chk.execute("PRAGMA journal_mode=delete")   # 收尾校验连接产生的 -wal/-shm 残留
    chk.close()
    for ext in ("-wal", "-shm"):
        if os.path.exists(plain + ext):
            os.remove(plain + ext)
    if ok != "ok":
        notify("P2: 备份库校验失败", f"integrity={ok}", "P2")
        os.remove(plain)
        raise RuntimeError(f"backup integrity_check failed: {ok}")
    final = plain
    if recipient:
        enc = f"{plain}.age"
        rc = os.system(f"age -r '{recipient}' '{plain}' > '{enc}' 2>/dev/null")
        if rc == 0 and os.path.getsize(enc) > 0:
            os.remove(plain)
            final = enc
    files = sorted(f for f in os.listdir(bdir)
                   if f.startswith("app-") and (f.endswith(".db") or f.endswith(".age")))
    for f in files[:-keep]:
        os.remove(os.path.join(bdir, f))
    return {"date": day, "file": os.path.basename(final), "integrity": ok,
            "kept": len(files[-keep:])}
