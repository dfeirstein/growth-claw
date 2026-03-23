"""SQL queries used by the GrowthClaw dashboard."""

# Latest schema map — returns the full discovery record with funnel as JSONB
FUNNEL_QUERY = """
SELECT business_name, business_type, funnel, concepts, discovered_at
FROM growthclaw.schema_map
ORDER BY discovered_at DESC LIMIT 1
"""

# Daily sends over last 30 days, broken out by channel
DAILY_SENDS = """
SELECT
    DATE(sent_at) AS send_date,
    channel,
    COUNT(*) AS send_count,
    COUNT(*) FILTER (WHERE outcome = 'converted') AS conversions
FROM growthclaw.journeys
WHERE sent_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE(sent_at), channel
ORDER BY send_date
"""

# Performance summary per trigger
TRIGGER_PERFORMANCE = """
SELECT
    t.name,
    t.status,
    t.channel,
    t.delay_minutes,
    t.max_fires,
    t.cooldown_hours,
    COUNT(j.id) AS total_fires,
    COUNT(j.id) FILTER (WHERE j.outcome = 'converted') AS conversions,
    CASE WHEN COUNT(j.id) > 0
         THEN ROUND(COUNT(j.id) FILTER (WHERE j.outcome = 'converted')::numeric / COUNT(j.id) * 100, 1)
         ELSE 0 END AS conversion_rate_pct
FROM growthclaw.triggers t
LEFT JOIN growthclaw.journeys j ON j.trigger_id = t.id AND j.status = 'sent'
GROUP BY t.id, t.name, t.status, t.channel, t.delay_minutes, t.max_fires, t.cooldown_hours
ORDER BY total_fires DESC
"""

# Recent journeys with trigger name
RECENT_JOURNEYS = """
SELECT
    j.created_at,
    j.user_id,
    t.name AS trigger_name,
    j.channel,
    LEFT(j.message_body, 80) AS message_preview,
    j.status,
    j.outcome,
    j.sent_at
FROM growthclaw.journeys j
JOIN growthclaw.triggers t ON t.id = j.trigger_id
ORDER BY j.created_at DESC
LIMIT 200
"""

# AutoResearch cycle history
AUTORESEARCH_HISTORY = """
SELECT
    ac.cycle_number,
    t.name AS trigger_name,
    ac.hypothesis,
    ac.variable,
    ac.control_desc,
    ac.test_desc,
    ac.control_sends,
    ac.control_conversions,
    ac.test_sends,
    ac.test_conversions,
    ac.status,
    ac.decision,
    ac.uplift_pct,
    ac.confidence,
    ac.reasoning,
    ac.started_at,
    ac.completed_at
FROM growthclaw.autoresearch_cycles ac
JOIN growthclaw.triggers t ON t.id = ac.trigger_id
ORDER BY ac.started_at DESC
"""
