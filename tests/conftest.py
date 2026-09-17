"""pytest 公共夹具：独立临时库＋中文断言输出。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
_TMP = os.environ.get("WTE_TEST_DB", "/tmp/wte_pytest.db")
os.environ["WTE_DB_PATH"] = _TMP
os.environ.setdefault("WTE_ENV", "dev")


@pytest.fixture(scope="session", autouse=True)
def _db():
    from app.core import db
    if os.path.exists(_TMP):
        os.remove(_TMP)
    db.init_schema()
    yield db
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(_TMP + suffix)
        except FileNotFoundError:
            pass
