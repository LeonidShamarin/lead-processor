"""
Telegram notification service.

Sends a formatted message to a Telegram chat when a new lead is processed.

Required env vars:
    TELEGRAM_BOT_TOKEN  — bot token from @BotFather
    TELEGRAM_CHAT_ID    — chat / channel ID to send notifications to
"""

import logging
import os

import httpx

from models import LeadScore, ProcessedLead

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _format_message(lead: ProcessedLead) -> str:
    """Build a clean HTML-formatted Telegram notification."""
    header_emoji = {
        LeadScore.HOT: "🔥🔥🔥",
        LeadScore.WARM: "🟡",
        LeadScore.COLD: "❄️",
    }.get(lead.classification, "📋")

    lines = [
        f"{header_emoji} <b>New Lead — {h(lead.classification.value if hasattr(lead.classification, 'value') else lead.classification)}</b>",
        f"🆔 <code>{h(lead.lead_id)}</code> | {h(lead.received_at)}",
        "",
        f"👤 <b>{h(lead.name)}</b>",
        f"📧 {h(lead.email)}",
    ]

    if lead.phone:
        lines.append(f"📞 {h(lead.phone)}")
    if lead.company:
        company_line = h(lead.company)
        if lead.employees:
            company_line += f" ({h(lead.employees)} employees)"
        lines.append(f"🏢 {company_line}")
    if lead.budget:
        lines.append(f"💰 Budget: {h(lead.budget)}")
    if lead.service:
        lines.append(f"🛠 Service: {h(lead.service)}")
    if lead.source:
        lines.append(f"📡 Source: {h(lead.source)}")

    lines += [
        "",
        f"📝 <b>AI Summary:</b>",
        h(lead.ai_summary),
        "",
        f"🎯 <i>Reason: {h(lead.classification_reason)}</i>",
    ]

    if lead.message:
        trimmed = lead.message[:300] + ("…" if len(lead.message) > 300 else "")
        lines += ["", f"💬 <b>Message:</b>", h(trimmed)]

    return "\n".join(lines)


def h(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


async def send_telegram_notification(lead: ProcessedLead) -> bool:
    """
    Sends an HTML-formatted message to the configured Telegram chat.
    Returns True on success, False on any error.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning("Telegram credentials not set — skipping notification")
        return False

    text = _format_message(lead)
    url = TELEGRAM_API.format(token=token)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            data = response.json()

        if data.get("ok"):
            logger.info("Telegram notification sent for lead %s", lead.lead_id)
            return True
        else:
            logger.error("Telegram API error: %s", data)
            return False

    except Exception as exc:
        logger.error("Failed to send Telegram notification: %s", exc)
        return False