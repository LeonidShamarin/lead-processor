"""
AI service — uses Groq (FREE tier: 14,400 req/day) to:
1. Generate a concise human-readable summary of the lead.
2. Classify the lead as HOT / WARM / COLD with reasoning.

Model: openai/gpt-oss-120b (Groq retired llama-3.3-70b-versatile in Nov 2026).
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

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-120b"

# Extra request fields per base URL. gpt-oss reasons before answering and those
# tokens count against max_tokens; "low" keeps a lead analysis at ~80-150 tokens.
# Other providers reject the field, so it is sent to Groq only.
_EXTRA_BODY = {GROQ_BASE_URL: {"reasoning_effort": "low"}}

# Provider fallback chain. Groq, OpenAI and xAI are OpenAI-compatible; Gemini has
# an OpenAI-compatible endpoint. Order: the current provider (Groq) first, then the
# four shared keys, then the last-priority keys. Any provider that fails hands off
# to the next; if every one fails, analyze_lead still returns via _fallback_analysis.
PROVIDERS = {
    # provider -> (base_url, model)
    "groq": (GROQ_BASE_URL, GROQ_MODEL),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash-lite"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "xai": ("https://api.x.ai/v1", "grok-4.20-0309-non-reasoning"),
}
# (provider, env var) in chain order; duplicates by (provider, key value) collapse.
_CHAIN = [
    ("groq", "GROQ_API_KEY"),          # current provider
    ("gemini", "GEMINI_API_KEY"),      # ai-keys.env, file order
    ("groq", "GROQ_API_KEY"),
    ("openai", "OPENAI_API_KEY"),
    ("xai", "XAI_API_KEY"),
    ("gemini", "GEMINI_API_KEY_2"),    # ключі2.txt, last
    ("gemini", "GEMINI_API_KEY_3"),
    ("groq", "GROQ_API_KEY_2"),
]


def _build_chain(env) -> list:
    """Resolve the chain to a list of (label, base_url, model, api_key) from env,
    skipping unset keys and collapsing duplicate (provider, key) pairs."""
    out = []
    seen = set()
    for provider, var in _CHAIN:
        key = (env.get(var) or "").strip()
        if not key or (provider, key) in seen:
            continue
        seen.add((provider, key))
        base_url, model = PROVIDERS[provider]
        out.append((f"{provider}:{var}", base_url, model, key))
    return out

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


async def _call_provider(client: httpx.AsyncClient, base_url: str, model: str,
                         api_key: str, messages: list) -> str:
    """One OpenAI-compatible chat completion. Raises on any transport/HTTP error."""
    response = await client.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "max_tokens": 512, "temperature": 0.2,
              **_EXTRA_BODY.get(base_url, {})},
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def _parse_analysis(raw_text: str) -> Tuple[str, LeadScore, str]:
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
    return summary, classification, reason


async def analyze_lead(lead: LeadRequest) -> Tuple[str, LeadScore, str]:
    """
    Returns (summary, classification, reason).

    Tries each configured provider in the fallback chain in turn; if every one
    fails (or none is configured), falls back to rule-based analysis so a lead is
    never lost.
    """
    chain = _build_chain(os.environ)
    if not chain:
        logger.warning("no provider key set — using fallback classification")
        return _fallback_analysis(lead)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Analyze this lead:\n\n{_build_lead_text(lead)}"},
    ]

    errors = []
    async with httpx.AsyncClient(timeout=30) as client:
        for label, base_url, model, api_key in chain:
            try:
                raw_text = await _call_provider(client, base_url, model, api_key, messages)
                result = _parse_analysis(raw_text)
                logger.info("AI analysis complete via %s: %s", label, result[1])
                return result
            except Exception as exc:
                errors.append(f"{label}: {str(exc)[:120]}")
                continue

    logger.error("all providers failed (%s) — using fallback", " | ".join(errors))
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
    