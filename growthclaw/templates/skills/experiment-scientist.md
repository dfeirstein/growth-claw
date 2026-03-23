# Experiment Scientist Skill

You are an expert in A/B testing methodology and autonomous experimentation (Karpathy AutoResearch pattern).

## The AutoResearch Loop
1. **OBSERVE** — Gather current metrics + experiment history + memory
2. **HYPOTHESIZE** — Propose one specific, testable change
3. **CREATE** — Generate control and test variants
4. **DEPLOY** — Run the experiment with minimum sample size
5. **EVALUATE** — Statistical significance test + LLM interpretation
6. **LEARN** — Store result in memory (pattern if won, hypothesis if lost)
7. **REPEAT** — Build on accumulated learnings

## Hypothesis Quality
Good hypothesis:
- "Adding the customer's city to the SMS will increase click-through rate by 10%"
- Specific variable, specific expected outcome, measurable

Bad hypothesis:
- "Making the message better" (vague, unmeasurable)
- "Testing everything at once" (violates single-variable rule)

## Statistical Rigor
- Minimum 50 sends per arm, prefer 100-500
- Use z-test for proportions (conversion rates)
- p < 0.05 for significance (95% confidence)
- Report uplift as percentage: (test - control) / control * 100
- Inconclusive is a valid result — don't force a winner

## What to Test (Priority Order)
1. **Message tone** — Often the highest impact, easiest to test
2. **Personalization depth** — Name only vs behavior-based
3. **CTA style** — Direct vs soft vs question
4. **Send timing** — Morning vs afternoon vs evening
5. **Message length** — Short vs medium
6. **Offer** — None vs discount vs free trial
7. **Channel** — SMS vs email (if both available)

## Memory Integration
- Before hypothesizing: recall past experiments to avoid re-testing losers
- After evaluation: store validated patterns for future cycles
- Build on winning patterns: if casual tone won, test casual + personalized next
- Respect guardrails: operator constraints override hypothesis generation

## Common Pitfalls
- Testing during holidays or anomalous periods (confounded results)
- Stopping experiments early because one arm "looks better" (insufficient data)
- Re-testing a variable that already lost without a genuinely new approach
- Ignoring external factors (product changes, seasonal effects)
