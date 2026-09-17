-- 0003_full_tables.sql —— T1.2 数据层全表（落地方案 §2.1；expand-only：仅加表）
-- 已有表（0001/0002）：sessions / events / dish_library / config。
-- dish_slug＝dish_pool 与 dish_library 共同携带的跨形态全局键（v3.1 评审 2）：
-- memory_events.dish_ref 引用 slug，形态切换后记忆可无损迁移（T1.8 验收项）。

CREATE TABLE IF NOT EXISTS identity (
  anon_id         TEXT PRIMARY KEY,
  passcode_salt   TEXT,
  passcode_hash   TEXT,             -- 盐＋单向哈希；未设置口令的用户为 NULL
  created_at      TEXT NOT NULL,
  recovery_count  INTEGER NOT NULL DEFAULT 0   -- 连续 5 次失败锁 24h（§4.1 评审 7）
);

CREATE TABLE IF NOT EXISTS preference_profile (
  anon_id    TEXT NOT NULL,
  answers    TEXT NOT NULL,         -- JSON：3 题冷启动画像（FR-08）
  created_at TEXT NOT NULL,
  PRIMARY KEY (anon_id, created_at) -- 画像可追加版本，读取侧取最新
);

CREATE TABLE IF NOT EXISTS memory_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  anon_id    TEXT NOT NULL,
  dish_ref   TEXT NOT NULL,         -- ＝ dish_slug（跨形态稳定键）
  signal     TEXT NOT NULL CHECK (signal IN ('accept','swap','negative','visit_bad')),
  weight     REAL NOT NULL,         -- SC-3 可调权重：+1/-0.5/-1/0/-1
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_anon ON memory_events(anon_id, id);

CREATE TABLE IF NOT EXISTS dish_pool (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  dish_slug TEXT NOT NULL,
  dish_name TEXT NOT NULL,
  city      TEXT NOT NULL DEFAULT 'sz',
  time_slot TEXT NOT NULL,          -- 午/晚/夜（U6 未定稿前按 3 时段假设）
  tag_combo TEXT NOT NULL,          -- JSON 数组；UNIQUE 与 slug 的组合约束见下
  copy      TEXT NOT NULL,          -- 按组合预生成的推荐语
  batch_id  TEXT NOT NULL,
  active    INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pool_slot_combo_slug
  ON dish_pool(time_slot, tag_combo, dish_slug);

CREATE TABLE IF NOT EXISTS template_copy (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  scene    TEXT NOT NULL,           -- 场景或 tag_combo 键
  text     TEXT NOT NULL,
  batch_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_template_scene ON template_copy(scene);

CREATE TABLE IF NOT EXISTS batch_runs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  form         TEXT NOT NULL,
  started_at   TEXT NOT NULL,
  finished_at  TEXT,
  items_in     INTEGER,
  items_out    INTEGER,
  cost_usd     REAL,
  status       TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS llm_calls (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         TEXT NOT NULL,
  vendor     TEXT NOT NULL,
  scene      TEXT NOT NULL CHECK (scene IN ('batch','cold_start')),
  latency_ms INTEGER,
  tokens_in  INTEGER,
  tokens_out INTEGER,
  cost_usd   REAL,
  status     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_ts ON llm_calls(ts);

CREATE TABLE IF NOT EXISTS probe_results (
  check_date TEXT NOT NULL,
  link_key   TEXT NOT NULL,         -- 菜品词搜索深链样本键（§2.4；含对照 URL）
  platform   TEXT NOT NULL,
  status     TEXT NOT NULL,         -- ok/fail/slow/counter_ok（对照判定探活器自身）
  detail     TEXT,
  PRIMARY KEY (check_date, link_key)
);

CREATE TABLE IF NOT EXISTS audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         TEXT NOT NULL,
  actor      TEXT NOT NULL,         -- owner / system:cron（§4.3）
  action     TEXT NOT NULL,         -- 批产激活/config 变更/口令重置/清除/发布/回滚…
  target     TEXT,
  detail     TEXT,                  -- JSON（config 变更含 before/after）
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_metrics (
  metric_date TEXT NOT NULL,
  metric      TEXT NOT NULL,        -- 口径单一事实源：全部闸门指标收敛于日表生成器（§2.2）
  value       TEXT NOT NULL,        -- JSON（兼容分布与标量）
  n           INTEGER,              -- 支持判读的样本量（判读纪律：任何判定必附 n）
  PRIMARY KEY (metric_date, metric)
);
