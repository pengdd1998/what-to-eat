-- 0008：监控 v2（monitoring-workbench-plan §4 P1-4）
-- expand-only：两列均可空、无表重建、不触任何 CHECK。

-- model＝实际模型名，与 vendor（接入方式）语义分离——vendor 对照备料的真实维度
ALTER TABLE llm_calls ADD COLUMN model TEXT;

-- 出题主链 L4 口径修复：next() 生成的题目（含 source）暂存，
-- answer() 取用并入 question_log 后清空（question_log 由 answer 落库但 source 在 next 生成）
ALTER TABLE quiz_session ADD COLUMN pending_q TEXT;
