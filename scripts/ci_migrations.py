#!/usr/bin/env python3
"""CI 迁移完整性（ci-cd-plan §3）：空 SQLite 按序跑全部迁移两遍，验 expand-only 幂等。"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("WTE_ENV", "dev")
db_path = "/tmp/ci-mig.db"
for suf in ("", "-wal", "-shm"):
    try: os.remove(db_path + suf)
    except FileNotFoundError: pass
os.environ["WTE_DB_PATH"] = db_path   # 必须在 import db 前（模块级固化路径）
from app.core import db

db.init_schema()
db.init_schema()  # 两遍：幂等性
conn = sqlite3.connect(db_path)
tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
print("tables:", tables)
need = {"sessions", "events", "config", "dish_library", "dish_pool", "memory_events",
        "identity", "llm_calls", "audit_log", "daily_metrics", "probe_results",
        "batch_runs", "quiz_session", "recommendation"}
missing = need - set(tables)
if missing:
    print(f"FAIL 缺表: {missing}")
    sys.exit(1)
print("migrations idempotent: OK")
