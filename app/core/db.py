"""SQLite 存取层（落地方案 §2：WAL、busy_timeout=5s、口径单一事实源）。

T0.2 最小实现：单连接＋线程锁（FastAPI sync 端点跑在线程池）。写入频率极低
（§2.3），该实现够用；T1.2 数据层全表时重访连接策略。
"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager

APP_VERSION = os.environ.get("APP_VERSION", "0.1.0-t0.2")
GIT_SHA = os.environ.get("GIT_SHA", "dev")

# 仓库根＝app/core/ 上两级（阶段3：db.py 自 app/ 迁入 core/，路径随之加深一层）
_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
DB_PATH = os.environ.get("WTE_DB_PATH", os.path.join(_REPO, "app.db"))
MIGRATIONS_DIR = os.path.join(_REPO, "migrations")

_lock = threading.Lock()
_conn: sqlite3.Connection = None


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=FULL")  # §2.2 持久性
        _conn.execute("PRAGMA busy_timeout=5000")
    return _conn


@contextmanager
def tx():
    """串行化写事务：锁＋BEGIN IMMEDIATE，避免线程池并发写冲突。"""
    conn = connect()
    with _lock:
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def init_schema() -> None:
    """按文件名顺序执行 migrations（expand-only，§3.3）。

    ALTER ADD COLUMN 类语句 SQLite 无 IF NOT EXISTS——重复启动时按
    "duplicate column" 识别为已应用并跳过；第 3 次 schema 变更触发 D-10
    换正式迁移框架后本特例消亡。
    """
    conn = connect()
    with _lock:
        for fname in sorted(os.listdir(MIGRATIONS_DIR)):
            if not fname.endswith(".sql"):
                continue
            with open(os.path.join(MIGRATIONS_DIR, fname), encoding="utf-8") as f:
                sql = f.read()
            try:
                conn.executescript(sql)
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e):
                    continue
                raise
        conn.commit()


def get_config(key: str, default=None):
    row = connect().execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_config(key: str, value) -> None:
    from datetime import datetime, timezone

    with tx() as conn:
        conn.execute(
            "INSERT INTO config(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False),
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )


def ensure_config(key: str, default) -> None:
    """仅缺省补齐（INSERT OR IGNORE）——不覆盖 Admin 通道的改动（§1.3）。"""
    from datetime import datetime, timezone

    with tx() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO config(key,value,updated_at) VALUES(?,?,?)",
            (key, json.dumps(default, ensure_ascii=False),
             datetime.now(timezone.utc).isoformat(timespec="seconds")))


def db_writable() -> bool:
    try:
        with tx() as conn:
            conn.execute("SELECT 1")
        return True
    except sqlite3.Error:
        return False
