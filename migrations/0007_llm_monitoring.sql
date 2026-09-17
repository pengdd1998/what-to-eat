-- 0007：LLM 监控数据补强（llm-monitoring-plan v1.1 §3 P0）
-- 纯 expand：三列可空，不触 scene CHECK、不重建表；老行为 NULL＝判读 COALESCE 旧口径。
-- task：应用层枚举 next_question|finalize|cold_start|batch_copy（网关 task 语义对齐）；
-- error_class：网关五枚举（超时/限流/内容过滤/解析失败/未知），成功为 NULL；
-- attempts：1=首过 2+=重试过（重试率可算）。

ALTER TABLE llm_calls ADD COLUMN task TEXT;
ALTER TABLE llm_calls ADD COLUMN error_class TEXT;
ALTER TABLE llm_calls ADD COLUMN attempts INTEGER;
