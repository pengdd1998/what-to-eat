"""身份锚（FR-11；T1.8）——anon_id 常设可见＋口令恢复常设能力。

口令策略（§4.1 评审 7）：≥6 位、拒绝纯数字、拒绝弱口令（Top-1000 精简占位版，
D-19）；加盐 PBKDF2 单向哈希；recover 连续 5 次失败锁 24h（identity.locked_until，
0004 迁移）；端点独立限流 ≤5 次/分/IP（app/ratelimit.py）。
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

# 精简弱口令表（占位 ~120 条常见模式；D-19：上线放行前换全量 Top-1000）
WEAK_PREFIXES = ("123", "111", "000", "666", "888", "abc", "aaa", "qqq",
                 "asd", "qwe", "zxc", "pass", "admin", "ilove", "wang", "zhang",
                 "chen", "liu", "yang", "huang", "wu", "520", "1314", "100", "1qaz",
                 "a123", "aa11", "p@ss", "letme", "welc", "monkey", "dragon")
WEAK_EXACT = {"password", "passwd", "123123", "123321", "12341234", "121212",
              "112233", "654321", "698544", "775852", "88775852", "a123456",
              "123456", "1234567", "12345678", "123456789", "1234567890",
              "000000", "111111", "666666", "888888", "666888", "888666",
              "abc123", "abc123456", "qwerty", "qazwsx", "asdasd", "qq123456",
              "taobao", "alibaba", "google", "iphone", "android", "weixin",
              "woaini", "woaini520", "520520", "111222", "333666", "987654321"}
COMMON_YEARS = tuple(str(y) for y in range(1960, 2027))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def passcode_ok(passcode: str) -> tuple:
    """返回 (合格?, 原因)。规则：≥6 位、非纯数字、非弱模式。"""
    if len(passcode) < 6:
        return False, "too_short"
    if passcode.isdigit():
        return False, "pure_digits"
    low = passcode.lower()
    if low in WEAK_EXACT:
        return False, "weak_list"
    if len(set(passcode)) <= 2:
        return False, "low_entropy"
    for y in COMMON_YEARS:
        if y in passcode:
            return False, "contains_year"
    for p in WEAK_PREFIXES:
        if low.startswith(p):
            return False, "weak_prefix"
    return True, ""


def hash_passcode(passcode: str, salt: str = None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", passcode.encode(),
                                 salt.encode(), 120_000).hex()
    return salt, digest


def verify(passcode: str, salt: str, expected_hash: str) -> bool:
    import hmac as hmac_mod
    _, digest = hash_passcode(passcode, salt)
    return hmac_mod.compare_digest(digest, expected_hash)


def lock_state(locked_until: str):
    """返回是否处于锁定期。"""
    if not locked_until:
        return False
    return _now() < datetime.fromisoformat(locked_until)


def new_lock_deadline() -> str:
    return (_now() + timedelta(hours=24)).isoformat(timespec="seconds")

# ---------- service 层（阶段4：passphrase/passcode 双轨合并，端点契约不变） ----------

def set_passcode(anon_id: str, passcode: str):
    """设置/更换口令：校验→加盐哈希→upsert＋审计。返回 (ok, reason)。"""
    ok, reason = passcode_ok(passcode)
    if not ok:
        return False, reason
    from datetime import datetime, timezone as _tz
    from ..core import db as _db
    from ..core.audit import audit
    salt, digest = hash_passcode(passcode)
    today = datetime.now(_tz.utc).isoformat(timespec="seconds")[:10]
    with _db.tx() as t:
        t.execute(
            "INSERT INTO identity(anon_id,passcode_salt,passcode_hash,"
            "created_at,recovery_count,locked_until) VALUES(?,?,?,?,0,NULL) "
            "ON CONFLICT(anon_id) DO UPDATE SET passcode_salt=excluded."
            "passcode_salt, passcode_hash=excluded.passcode_hash, "
            "recovery_count=0, locked_until=NULL",
            (anon_id, salt, digest, today))
        audit(t, f"anon:{anon_id[:6]}", "passcode_set", anon_id, {})
    return True, ""


def try_recover(anon_id: str, passcode: str):
    """凭 口令 找回：成功→("ok", None)；失败→("mismatch"|"locked"|"not_found", 剩余信息)。
    行级锁定（5 错锁 24h）与锁定审计在事务内。"""
    from ..core import db as _db
    from ..core.audit import audit
    r = _db.connect().execute(
        "SELECT passcode_salt, passcode_hash, recovery_count, locked_until "
        "FROM identity WHERE anon_id=?", (anon_id,)).fetchone()
    if not r or not r["passcode_hash"]:
        return "not_found", None
    if lock_state(r["locked_until"]):
        return "locked", None
    if verify(passcode, r["passcode_salt"], r["passcode_hash"]):
        with _db.tx() as t:
            t.execute("UPDATE identity SET recovery_count=0, locked_until=NULL "
                      "WHERE anon_id=?", (anon_id,))
        return "ok", None
    with _db.tx() as t:
        new_count = r["recovery_count"] + 1
        lock = new_lock_deadline() if new_count >= 5 else None
        t.execute("UPDATE identity SET recovery_count=?, locked_until=? "
                  "WHERE anon_id=?", (new_count, lock, anon_id))
        if lock:
            audit(t, f"anon:{anon_id[:6]}", "passcode_locked", anon_id, {})
    return "mismatch", None
