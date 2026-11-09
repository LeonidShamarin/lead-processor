"""Провайдерський фолбек: порядок ланцюжка, дедуп, парсинг. Без мережі."""

import ai_service as a
from models import LeadScore


def test_chain_order_and_dedup():
    env = {"GROQ_API_KEY": "gsk_p", "GEMINI_API_KEY": "AIza_a", "OPENAI_API_KEY": "sk-a",
           "XAI_API_KEY": "xai-a", "GEMINI_API_KEY_2": "AQ.1", "GEMINI_API_KEY_3": "AQ.2",
           "GROQ_API_KEY_2": "gsk_2"}
    labels = [c[0] for c in a._build_chain(env)]
    assert labels == ["groq:GROQ_API_KEY", "gemini:GEMINI_API_KEY", "openai:OPENAI_API_KEY",
                      "xai:XAI_API_KEY", "gemini:GEMINI_API_KEY_2", "gemini:GEMINI_API_KEY_3",
                      "groq:GROQ_API_KEY_2"]


def test_chain_skips_unset_and_dedups_same_value():
    assert a._build_chain({}) == []
    # same key under primary and ai-keys.env slot -> one entry
    chain = a._build_chain({"GROQ_API_KEY": "same"})
    assert len(chain) == 1 and chain[0][0] == "groq:GROQ_API_KEY"


def test_each_provider_base_and_model():
    env = {"GROQ_API_KEY": "g", "GEMINI_API_KEY": "ge", "OPENAI_API_KEY": "o", "XAI_API_KEY": "x"}
    by = {c[0].split(":")[0]: (c[1], c[2]) for c in a._build_chain(env)}
    assert by["groq"] == ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b")
    assert by["gemini"] == ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.5-flash-lite")
    assert by["openai"] == ("https://api.openai.com/v1", "gpt-4o-mini")
    assert by["xai"] == ("https://api.x.ai/v1", "grok-2-latest")


def test_reasoning_effort_sent_to_groq_only():
    import asyncio
    import json

    import httpx

    sent = {}

    def handler(request):
        sent[str(request.url)] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            for provider in ("groq", "gemini"):
                base, model = a.PROVIDERS[provider]
                await a._call_provider(client, base, model, "k", [{"role": "user", "content": "x"}])

    asyncio.run(run())
    groq = sent["https://api.groq.com/openai/v1/chat/completions"]
    gemini = sent["https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"]
    assert groq["reasoning_effort"] == "low"
    assert "reasoning_effort" not in gemini


def test_parse_analysis_strips_fences_and_maps_class():
    summary, classification, reason = a._parse_analysis('```json\n{"summary":"s","classification":"hot","reason":"r"}\n```')
    assert summary == "s" and classification == LeadScore.HOT and reason == "r"


def test_parse_analysis_defaults_unknown_class_to_warm():
    _, classification, _ = a._parse_analysis('{"summary":"s","classification":"maybe","reason":""}')
    assert classification == LeadScore.WARM
