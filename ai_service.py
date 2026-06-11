"""
AI service — uses Groq (FREE tier: 14,400 req/day) to:
1. Generate a concise human-readable summary of the lead.
2. Classify the lead as HOT / WARM / COLD with reasoning.

Model: llama-3.3-70b-versatile — fast, accurate, free.
Get a free API key at: https://console.groq.com/keys
No credit card required.

Groq uses OpenAI-compatible API → simple REST call.
Structured output via JSON-only prompt → deterministic json.loads() parsing.
"""

import json
import logging
import os
from typing import Tuple

import httpx

from models import LeadRequest, LeadScore

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are a CRM analyst assistant. You receive lead form submissions
and return structured JSON with exactly three fields:
- "summary": a 2-3 sentence plain-language summary of this lead (who they are,
  what they want, key signals). Write in the same language the lead used.
- "classification": one of "HOT", "WARM", or "COLD"
- "reason": one sentence explaining the classification

HOT criteria: large budget, enterprise company, clear urgent need, specific service request.
WARM criteria: some budget signal, real company, vague or mid-size need.
COLD criteria: no budget, unclear intent, very generic inquiry, likely student/researcher.

Respond ONLY with valid JSON. No markdown fences, no explanation outside the JSON object."""


def _build_lead_text(lead: LeadRequest) -> str:
    parts = [f"Name: {lead.name}", f"Email: {lead.email}"]
    if lead.phone:
        parts.append(f"Phone: {lead.phone}")
    if lead.company:
        parts.append(f"Company: {lead.company}")
    if lead.employees:
        parts.append(f"Company size: {lead.employees} employees")
    if lead.budget:
        parts.append(f"Budget: {lead.budget}")
    if lead.service:
        parts.append(f"Interested in: {lead.service}")
    if lead.source:
        parts.append(f"Source: {lead.source}")
    if lead.message:
        parts.append(f"Message: {lead.message}")
    return "\n".join(parts)


async def analyze_lead(lead: LeadRequest) -> Tuple[str, LeadScore, str]:
    """
    Returns (summary, classification, reason).
    Falls back to rule-based analysis if the API call fails.
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        logger.warning("GROQ_API_KEY not set — using fallback classification")
        return _fallback_analysis(lead)

    lead_text = _build_lead_text(lead)

    # Groq uses OpenAI-compatible chat completions format
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze this lead:\n\n{lead_text}"},
        ],
        "max_tokens": 512,
        "temperature": 0.2,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        # OpenAI-compatible response structure
        raw_text = data["choices"][0]["message"]["content"].strip()
        # Strip accidental markdown fences
        raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        parsed = json.loads(raw_text)

        summary = parsed.get("summary", "No summary generated.")
        raw_class = parsed.get("classification", "WARM").upper()
        reason = parsed.get("reason", "")

        classification = {
            "HOT": LeadScore.HOT,
            "WARM": LeadScore.WARM,
            "COLD": LeadScore.COLD,
        }.get(raw_class, LeadScore.WARM)

        logger.info("Groq analysis complete: %s", raw_class)
        return summary, classification, reason

    except Exception as exc:
        logger.error("Groq AI analysis failed: %s", exc)
        return _fallback_analysis(lead)


def _fallback_analysis(lead: LeadRequest) -> Tuple[str, LeadScore, str]:
    """
    Rule-based fallback when the API is unavailable.
    Simple heuristic: score by budget presence + company presence.
    """
    score = 0
    if lead.budget and lead.budget.isdigit() and int(lead.budget) >= 5000:
        score += 2
    elif lead.budget:
        score += 1
    if lead.company:
        score += 1
    if lead.phone:
        score += 1
    if lead.message and len(lead.message) > 50:
        score += 1

    if score >= 4:
        classification = LeadScore.HOT
        reason = "High score: budget + company + phone present (rule-based fallback)."
    elif score >= 2:
        classification = LeadScore.WARM
        reason = "Moderate score: some qualifying signals (rule-based fallback)."
    else:
        classification = LeadScore.COLD
        reason = "Low score: missing key qualification data (rule-based fallback)."

    summary = (
        f"{lead.name} submitted a lead inquiry"
        f"{f' from {lead.company}' if lead.company else ''}. "
        f"Budget: {lead.budget or 'not specified'}. "
        f"Message: {(lead.message or 'none')[:120]}."
    )
    return summary, classification, reason
    