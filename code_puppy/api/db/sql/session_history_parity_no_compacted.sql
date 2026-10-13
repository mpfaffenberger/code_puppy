SELECT
    'message' AS row_type,
    CAST(m.id AS TEXT) AS row_id,
    m.seq,
    m.role,
    m.content,
    m.type,
    m.agent_name,
    m.model_name,
    m.timestamp,
    m.thinking,
    m.attachments_json,
    m.clean_content,
    m.system_message_type,
    m.system_message_path,
    m.token_count,
    m.compacted,
    m.compaction_log_id,
    NULL AS tool_name,
    NULL AS args_json,
    NULL AS result_json,
    NULL AS status,
    NULL AS duration_ms,
    NULL AS error_text,
    NULL AS parent_message_seq
FROM messages m
WHERE m.session_id = ? AND m.compacted = 0

UNION ALL

SELECT
    'tool_call' AS row_type,
    tc.id AS row_id,
    tc.seq,
    'tool' AS role,
    NULL AS content,
    NULL AS type,
    tc.agent_name,
    tc.model_name,
    CAST(tc.timestamp AS TEXT) AS timestamp,
    NULL AS thinking,
    NULL AS attachments_json,
    NULL AS clean_content,
    NULL AS system_message_type,
    NULL AS system_message_path,
    0 AS token_count,
    0 AS compacted,
    NULL AS compaction_log_id,
    tc.tool_name,
    tc.args_json,
    tc.result_json,
    tc.status,
    tc.duration_ms,
    tc.error_text,
    tc.parent_message_seq
FROM tool_calls tc
WHERE tc.session_id = ?

ORDER BY seq;
