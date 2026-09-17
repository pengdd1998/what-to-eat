-- 0004_identity_locked_until.sql —— expand-only：identity 加可空列 locked_until
-- （口令恢复连续 5 次失败锁 24h 的锁定期存储，§4.1 评审 7）
ALTER TABLE identity ADD COLUMN locked_until TEXT;
