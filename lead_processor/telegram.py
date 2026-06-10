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
    """Build a clean, readable Telegram notification."""
    # Emoji header by classification
    header_emoji = {
        LeadScore.HOT: "🔥🔥🔥",
        LeadScore.WARM: "🟡",
        LeadScore.COLD: "❄️",
    }.get(lead.classification, "📋")

    lines = [
        f"{header_emoji} *New Lead — {lead.classification}*",
        f"🆔 `{lead.lead_id}` | {lead.received_at}",
        "",
        f"👤 *{_esc(lead.name)}*",
        f"📧 {_esc(lead.email)}",
    ]

    if lead.phone:
        lines.append(f"📞 {_esc(lead.phone)}")
    if lead.company:
        company_line = _esc(lead.company)
        if lead.employees:
            company_line += f" \\({_esc(lead.employees)} employees\\)"
        lines.append(f"🏢 {company_line}")
    if lead.budget:
        lines.append(f"💰 Budget: {_esc(lead.budget)}")
    if lead.service:
        lines.append(f"🛠 Service: {_esc(lead.service)}")
    if lead.source:
        lines.append(f"📡 Source: {_esc(lead.source)}")

    lines += [
        "",
        f"📝 *AI Summary:*",
        _esc(lead.ai_summary),
        "",
        f"🎯 *Reason:* _{_esc(lead.classification_reason)}_",
    ]

    if lead.message:
        trimmed = lead.message[:300] + ("…" if len(lead.message) > 300 else "")
        lines += ["", f"💬 *Message:*", _esc(trimmed)]

    return "\n".join(lines)


def _esc(text: str) -> str:
    """Escape special MarkdownV2 characters."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))


async def send_telegram_notification(lead: ProcessedLead) -> bool:
    """
    Sends a MarkdownV2 message to the configured Telegram chat.
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
                    "parse_mode": "MarkdownV2",
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
