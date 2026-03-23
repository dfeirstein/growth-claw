# GrowthClaw Heartbeat Tasks

## Every 5 minutes
- Check for conversion outcomes on pending journeys

## Every 6 hours
- Run AutoResearch cycle for each active trigger
- Recall memory for past patterns before generating hypotheses

## Daily (3 AM)
- Consolidate memory: decay old confidence scores, archive stale memories
- Clean up frequency tracking records older than 30 days

## Weekly
- Generate performance summary for operator
- Compare this week vs last week: sends, conversions, conversion rate
- Highlight top-performing trigger and AutoResearch discoveries
