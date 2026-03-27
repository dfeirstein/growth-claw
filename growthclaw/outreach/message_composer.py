"""Message composer — uses LLM to generate personalized outreach messages."""

from __future__ import annotations

import logging

from growthclaw.llm.client import LLMClient, render_template
from growthclaw.models.profile import IntelligenceBrief
from growthclaw.models.schema_map import BusinessConcepts
from growthclaw.models.trigger import TriggerRule

logger = logging.getLogger("growthclaw.outreach.message_composer")

SMS_MAX_LENGTH = 160
MAX_SMS_RETRIES = 2


async def compose(
    trigger: TriggerRule,
    profile_data: dict,
    intelligence_brief: IntelligenceBrief,
    concepts: BusinessConcepts,
    llm_client: LLMClient,
    cta_link: str = "",
    business_name: str = "",
    dag: object | None = None,
) -> str:
    """Generate a personalized message using LLM based on trigger context and customer profile."""
    # Enrich with DAG context (recent performance patterns for this trigger)
    dag_insights: list[str] = []
    if dag:
        try:
            dag_nodes = await dag.get_composition_context(trigger.name, trigger.channel)
            dag_insights = [n.summary_text for n in dag_nodes]
        except Exception as e:
            logger.warning("DAG context fetch failed: %s", e)

    prompt = render_template(
        "compose_message.j2",
        channel=trigger.channel,
        business_name=business_name or concepts.business_description,
        business_type=concepts.business_type,
        business_description=concepts.business_description,
        trigger_context=trigger.message_context,
        trigger_description=trigger.description,
        profile_data=profile_data,
        intelligence_brief=intelligence_brief.model_dump(mode="json"),
        cta_link=cta_link,
        dag_insights=dag_insights,
    )

    message = await llm_client.call(prompt, temperature=0.7, max_tokens=500, purpose="compose_sms")
    message = message.strip().strip('"').strip("'")

    # For SMS, enforce 160 char limit
    if trigger.channel == "sms" and len(message) > SMS_MAX_LENGTH:
        for _ in range(MAX_SMS_RETRIES):
            logger.warning("SMS message too long (%d chars), re-prompting LLM", len(message))
            retry_prompt = (
                f"This SMS message is {len(message)} characters but must be under {SMS_MAX_LENGTH}. "
                f"Shorten it while keeping the CTA link and key message:\n\n{message}"
            )
            message = await llm_client.call(retry_prompt, temperature=0.5, max_tokens=200, purpose="compose_sms_retry")
            message = message.strip().strip('"').strip("'")
            if len(message) <= SMS_MAX_LENGTH:
                break

        if len(message) > SMS_MAX_LENGTH:
            logger.warning("SMS still too long after retries (%d chars), truncating", len(message))
            message = message[: SMS_MAX_LENGTH - 3] + "..."

    logger.info("Composed %s message (%d chars) for trigger %s", trigger.channel, len(message), trigger.name)
    return message


async def compose_email(
    trigger: TriggerRule,
    profile_data: dict,
    intelligence_brief: IntelligenceBrief,
    concepts: BusinessConcepts,
    llm_client: LLMClient,
    cta_link: str = "",
    business_name: str = "",
) -> dict:
    """Compose a personalized email. Returns {"subject": str, "html_body": str, "plain_text": str}."""
    prompt = render_template(
        "compose_email.j2",
        trigger_context=trigger.message_context,
        profile_data=profile_data,
        intelligence_brief=intelligence_brief.model_dump(mode="json"),
        business_type=concepts.business_type or "business",
        business_description=concepts.business_description or "",
        cta_link=cta_link,
        business_name=business_name or concepts.business_description,
    )

    result = await llm_client.call_json(prompt, temperature=0.7, purpose="compose_email")

    subject = result.get("subject", "")
    html_body = result.get("html_body", "")
    plain_text = result.get("plain_text", "")

    logger.info("Composed email for trigger %s: subject='%s' (%d chars body)", trigger.name, subject, len(html_body))
    return {"subject": subject, "html_body": html_body, "plain_text": plain_text}
