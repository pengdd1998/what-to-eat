-- 0001_init.sql —— 首部署初始化（落地方案 §3.3：绿地＋expand-only）
-- T0.2 骨架冒烟子集：sessions / events / dish_library / config。
-- T1.2 数据层全表在此之上 expand（identity / preference_profile / memory_events /
-- dish_pool / template_copy / batch_runs / llm_calls / probe_results / audit_log /
-- daily_metrics），禁 rename/drop/改型。
-- 标注：form 列在终裁（ADR-003，W1 D6）前取 'undecided' 占位。

CREATE TABLE IF NOT EXISTS sessions (
  id            TEXT PRIMARY KEY,              -- 服务端生成的会话 id
  anon_id       TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'started',
                -- started→answering→presented→accepted/swapped_out/abandoned/timeout
  is_cold_start INTEGER NOT NULL DEFAULT 1,
  swap_count    INTEGER NOT NULL DEFAULT 0,
  swap_limit    INTEGER NOT NULL DEFAULT 2,    -- 稳态 2 / 冷启动 3（FR-04）
  form          TEXT NOT NULL DEFAULT 'undecided',
  started_at    TEXT NOT NULL,                 -- server_ts（ISO8601，权威时钟 SUP-06）
  ended_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_anon ON sessions(anon_id, started_at);

CREATE TABLE IF NOT EXISTS events (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  client_event_id  TEXT NOT NULL UNIQUE,       -- 幂等键（§2.2）
  session_id       TEXT NOT NULL,
  anon_id          TEXT NOT NULL,
  type             TEXT NOT NULL,              -- FR-15 子集，白名单见 app/events.py
  step             INTEGER,
  payload          TEXT NOT NULL DEFAULT '{}', -- JSON
  client_ts        TEXT,                       -- 仅存档，不作判读依据
  server_ts        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, id);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(type, server_ts);

-- dish_library：两形态共有（C 主数据 / A 兜底），≥50 道（SC-4 下限）。
-- dish_slug＝跨形态全局键（v3.1 评审 2）。本表种子数据为 [假设] 占位，
-- T1.5（菜库首批人工＋LLM 辅助初建）替换。
CREATE TABLE IF NOT EXISTS dish_library (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  dish_slug  TEXT NOT NULL UNIQUE,
  dish_name  TEXT NOT NULL,
  category   TEXT NOT NULL DEFAULT '',
  tags       TEXT NOT NULL DEFAULT '[]',       -- JSON 数组，词表＝10 固定标签（FR-02）
  base_score REAL NOT NULL DEFAULT 0.5,
  active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS config (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,                    -- JSON（SUP-08；生效语义 §1.3）
  updated_at TEXT NOT NULL
);
