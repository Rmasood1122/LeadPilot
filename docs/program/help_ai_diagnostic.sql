-- Help AI production diagnostic (Phase 0, step 6).
--
-- READ-ONLY. Run on Neon by a founder; not run by Claude Code.
-- Schema source: app/db/models.py ChatSession / ChatMessage (migration
-- 0017_ai_support_chat). Reason codes source: app/services/support_chat.py.
--
-- Window note: support chats are purged after SUPPORT_CHAT_RETENTION_DAYS
-- (render.yaml sets 30), keyed on the session's last_message_at, so 30 days is
-- the most this table can show.
--
-- Reason codes and what they mean:
--   answered            live mode: the model answered above the confidence floor
--   mock_faq_match      mock/console mode: a curated FAQ was returned verbatim
--   mock_no_match       mock/console mode: no FAQ cleared MIN_MOCK_MATCH_SCORE -> ticket
--   low_confidence      live mode: model confidence below the floor -> ticket
--   model_error         live mode: the model call failed -> ticket
--   malformed_response  live mode: reply was not the JSON contract -> ticket
--   empty_answer        live mode: JSON parsed but no answer text -> ticket
--   empty_question      nothing to answer -> ticket
--   off_topic           refused, no ticket offered

BEGIN TRANSACTION READ ONLY;

-- 1. Distribution by reason, with the mode each reason proves was running.
SELECT
    reason,
    CASE
        WHEN reason IN ('mock_faq_match', 'mock_no_match') THEN 'mock'
        WHEN reason IN ('answered', 'low_confidence', 'model_error',
                        'malformed_response', 'empty_answer') THEN 'live'
        ELSE 'either'
    END                                              AS mode_proven,
    suggest_ticket,
    count(*)                                         AS messages,
    round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct,
    round(avg(confidence)::numeric, 3)               AS avg_confidence,
    min(created_at)                                  AS first_seen,
    max(created_at)                                  AS last_seen
FROM chat_messages
WHERE role = 'assistant'
  AND created_at >= now() - interval '30 days'
GROUP BY reason, suggest_ticket
ORDER BY messages DESC;

-- 2. Answered vs. ticket vs. refused.
SELECT
    CASE
        WHEN reason IN ('answered', 'mock_faq_match') THEN 'answered'
        WHEN reason = 'off_topic'                     THEN 'refused_off_topic'
        WHEN suggest_ticket                           THEN 'ticket'
        ELSE 'other'
    END                                              AS outcome,
    count(*)                                         AS messages,
    round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
FROM chat_messages
WHERE role = 'assistant'
  AND created_at >= now() - interval '30 days'
GROUP BY 1
ORDER BY messages DESC;

-- 3. Which FAQ entries are actually cited (shows how narrow the 9-entry KB is).
SELECT
    faq_id,
    count(*) AS citations
FROM chat_messages m
CROSS JOIN LATERAL json_array_elements_text(m.faq_ids) AS faq_id
WHERE m.role = 'assistant'
  AND m.created_at >= now() - interval '30 days'
  AND m.faq_ids IS NOT NULL
  AND json_typeof(m.faq_ids) = 'array'
GROUP BY faq_id
ORDER BY citations DESC;

-- 4. Volume: how many people used it at all.
SELECT
    count(DISTINCT s.user_id)                          AS users,
    count(DISTINCT s.id)                               AS sessions,
    count(*) FILTER (WHERE m.role = 'user')            AS questions,
    count(*) FILTER (WHERE m.role = 'assistant')       AS replies
FROM chat_messages m
JOIN chat_sessions s ON s.id = m.session_id
WHERE m.created_at >= now() - interval '30 days';

ROLLBACK;

-- If query 3 errors with "function json_array_elements_text(jsonb) does not
-- exist", the column is jsonb on this database: replace json_array_elements_text
-- with jsonb_array_elements_text and json_typeof with jsonb_typeof.
