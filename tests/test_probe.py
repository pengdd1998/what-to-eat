"""probe 四锚回归（monitoring-workbench-plan §3 P0-1）：
NameError 修复锚／对照语义锚／兜底链路锚／持续态去重锚（评审 A）。
"""
import json
import urllib.request
from importlib import import_module
from unittest import mock

import pytest

# app.cron.__init__ 的 from .probe import probe 遮蔽模块名——import_module 取真模块
probe_mod = import_module("app.cron.probe")
from app.core import db


def _set_links(status):
    db.set_config("links", {"status": status, "default_platform": "meituan",
                            "templates": {"meituan": "https://x/?keyword={kw}"}})


class _Resp:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_probe_nameerror_fix():
    """锚1：urlopen 真实被调用（NameError 修复回归锚）→ 全 ok、无兜底。"""
    _set_links("ok")
    with mock.patch.object(urllib.request, "urlopen",
                           return_value=_Resp(200)) as m, \
         mock.patch.object(probe_mod, "notify") as n:
        r = probe_mod.probe()
    assert m.call_count > 0                      # NameError 修复：urlopen 真实调用
    assert all(v == "ok" for v in r["results"].values())
    assert r["auto_fallback"] is False
    assert n.call_count == 0
    assert db.get_config("links")["status"] == "ok"


def test_probe_ctrl_same_red_no_fallback():
    """锚2：全红＋对照同红 → 不置 dead、无 P1（对照语义锚）。"""
    _set_links("ok")
    with mock.patch.object(urllib.request, "urlopen",
                           side_effect=OSError("down")), \
         mock.patch.object(probe_mod, "notify") as n:
        r = probe_mod.probe()
    assert db.get_config("links")["status"] == "ok"   # 未被置 dead
    assert n.call_count == 0


def test_probe_fallback_flip():
    """锚3：链路全红＋对照绿 → 置 dead＋audit＋P1（兜底链路锚）。"""
    _set_links("ok")

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "baidu" in url:
            return _Resp(200)
        raise OSError("link dead")

    with mock.patch.object(urllib.request, "urlopen", fake_urlopen), \
         mock.patch.object(probe_mod, "notify") as n:
        r = probe_mod.probe()
    assert r["auto_fallback"] is True
    assert db.get_config("links")["status"] == "dead"
    assert n.call_count == 1 and n.call_args[0][2] == "P1"
    c = db.connect()
    assert c.execute("SELECT COUNT(*) FROM audit_log WHERE "
                     "action='probe_auto_fallback'").fetchone()[0] == 1


def test_probe_persistent_dead_dedup():
    """锚4（评审 A）：已 dead 再全红 → 无新 P1、无新 audit 行。"""
    _set_links("dead")                            # 已处于兜底态

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "baidu" in url:
            return _Resp(200)
        raise OSError("still dead")

    c = db.connect()
    before = c.execute("SELECT COUNT(*) FROM audit_log WHERE "
                       "action='probe_auto_fallback'").fetchone()[0]
    with mock.patch.object(urllib.request, "urlopen", fake_urlopen), \
         mock.patch.object(probe_mod, "notify") as n:
        r = probe_mod.probe()
    assert n.call_count == 0                      # 持续态静默
    after = c.execute("SELECT COUNT(*) FROM audit_log WHERE "
                      "action='probe_auto_fallback'").fetchone()[0]
    assert after == before                        # 无新 audit 行
    assert db.get_config("links")["status"] == "dead"   # config 幂等保持
