# Security & Data Handling

## Database Access
- Customer database: READ ONLY. Never write, update, or delete customer data.
- The only writes to the customer DB are NOTIFY trigger functions (fire-and-forget).
- All GrowthClaw state is stored in the `growthclaw` schema on the internal DB.

## PII Handling
- Customer names, emails, and phone numbers are used for outreach only.
- Never log full PII in tool call logs or notifications.
- Mask user IDs in dashboard displays (show first/last 2 chars only).
- Never include PII in AutoResearch hypotheses or memory entries.

## Consent & Compliance
- SMS: Only send to users with verified SMS consent (sms_consent_check from concepts).
- Email: Check suppression list before every send. Respect unsubscribes immediately.
- Quiet hours: Never send SMS between 9 PM and 8 AM in the customer's timezone.
- Frequency caps: Respect global daily and weekly limits across all triggers.

## Credentials
- API keys are stored in ~/.growthclaw/.env (never committed to git).
- Database connection strings contain passwords — never log or display them.
- Twilio/Resend credentials are used at send time only, never cached.

## Dry Run Mode
- GROWTHCLAW_DRY_RUN=true is the default. All messages are logged but never sent.
- Only change to false after reviewing proposed triggers and testing with real data.
- The dashboard shows composed journeys even in dry run mode.

## Audit Trail
- Every LLM call is logged with provider, tokens, estimated cost.
- Every trigger fire, journey, and experiment is persisted with full provenance.
- MCP tool calls are logged to data/logs/tool_calls.jsonl.
