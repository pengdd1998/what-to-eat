-- 0009：换一（swap）状态机（设计评审 P0-1，灯箱换片形态 2026-09-23 owner 拍板）
-- expand-only：可空列，老会话 NULL＝0（换一功能上线前的会话无换一语义）
ALTER TABLE quiz_session ADD COLUMN swap_count INTEGER NOT NULL DEFAULT 0;
