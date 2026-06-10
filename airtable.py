"""
Airtable integration — replaces Google Sheets.

Appends one record per processed lead using the Airtable REST API v0.
No SDK needed — plain httpx calls.

Required env vars:
    AIRTABLE_API_TOKEN  — Personal Access Token from airtable.com/create/tokens
    AIRTABLE_BASE_ID    — e.g. appIT1G1JliKqzpla
    AIRTABLE_TABLE_ID   — e.g. tblIKm0m0CwRkFVhZ (or table name "Leads")
"""

import logging
import os
from typing import Optional

import httpx

from models import ProcessedLead

logger = logging.getLogger(__name__)

AIRTABLE_API_URL = "https://api.airtable.com/v0/{base_id}/{table_id}"


async def append_lead_to_airtable(lead: ProcessedLead) -> Optional[str]:
    """
    Creates a new record in Airtable.
    Returns the created record ID on success, None on failure.
    """
    token = os.getenv("AIRTABLE_API_TOKEN", "")
    base_id = os.getenv("AIRTABLE_BASE_ID", "")
    table_id = os.getenv("AIRTABLE_TABLE_ID", "")

    if not all([token, base_id, table_id]):
        logger.warning("Airtable credentials not set — skipping write")
        return None

    url = AIRTABLE_API_URL.format(base_id=base_id, table_id=table_id)

    # Map ProcessedLead fields → Airtable column names
    fields = {
        "Lead ID":                lead.lead_id,
        "Received At":            lead.received_at,
        "Name":                   lead.name,
        "Email":                  lead.email,
        "Phone":                  lead.phone or "",
        "Company":                lead.company or "",
        "Employees":              lead.employees or "",
        "Budget":                 lead.budget or "",
        "Service":                lead.service or "",
        "Source":                 lead.source or "",
        "Message":                lead.message or "",
        "Classification":         lead.classification,
        "Classification Reason":  lead.classification_reason,
        "AI Summary":             lead.ai_summary,
    }

    # Airtable ignores empty strings for some field types — remove them
    fields = {k: v for k, v in fields.items() if v != ""}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"fields": fields},
            )
            response.raise_for_status()
            data = response.json()

        record_id = data.get("id", "unknown")
        logger.info("Lead %s written to Airtable: %s", lead.lead_id, record_id)
        return record_id

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Airtable API error %s: %s",
            exc.response.status_code,
            exc.response.text,
        )
        return None
    except Exception as exc:
        logger.error("Unexpected Airtable error: %s", exc)
        return None
