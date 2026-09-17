-- 0005_quiz_recommendation.sql —— 多步自适应收口引擎（A 形态，源自复刻工程移植 2026-09-07）
-- quiz_session：5~8 步问答会话（question_log 完整答题路径，供味觉记忆回放）
-- recommendation：推荐记录（含反馈三值与路径，味觉记忆页数据源）
-- identity 表沿用 0001/0004 生产 schema（复刻版 identity 列结构不迁，端点做适配层）

CREATE TABLE IF NOT EXISTS quiz_session (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  anon_id         TEXT NOT NULL,
  round_no        INTEGER NOT NULL DEFAULT 1,
  state           TEXT NOT NULL DEFAULT 'active',   -- active / done / abandoned
  step_index      INTEGER NOT NULL DEFAULT 0,
  question_log    TEXT NOT NULL DEFAULT '[]',       -- JSON [{step,question,option_id,option_text,options[],tags[]}]
  recommend_seed  TEXT NOT NULL,
  meal_scenario   TEXT,                             -- 早餐/午餐/下午茶/晚餐/宵夜
  result          TEXT,                             -- 收口结果 JSON（固化，刷新不重摇）
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_qsession_anon ON quiz_session(anon_id, id DESC);

CREATE TABLE IF NOT EXISTS recommendation (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  anon_id         TEXT NOT NULL,
  session_id      INTEGER,
  name            TEXT NOT NULL,
  tags            TEXT NOT NULL DEFAULT '[]',
  reason          TEXT,
  feedback        INTEGER,                          -- NULL 未评 / 1 对味 / 0 一般 / -1 不推荐
  meal_scenario   TEXT,
  question_log    TEXT,
  created_at      TEXT NOT NULL,
  feedback_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_rec_anon ON recommendation(anon_id, created_at DESC);
