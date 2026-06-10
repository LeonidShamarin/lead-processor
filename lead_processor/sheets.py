"""
Google Sheets integration.

Uses the Sheets REST API v4 with a Service Account JSON key.
On first run it ensures the header row exists; subsequent calls append rows.

Required env vars:
    GOOGLE_SERVICE_ACCOUNT_JSON  — full JSON key as a single-line string
    GOOGLE_SHEET_ID              — the spreadsheet ID from its URL
    GOOGLE_SHEET_NAME            — tab name, default "Leads"
"""

import json
import logging
import os
import time
from typing import Optional

import httpx
from google.oauth2.service_account import Credentials  # type: ignore
from googleapiclient.discovery import build  # type: ignore
from googleapiclient.errors import HttpError  # type: ignore

from models import ProcessedLead

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_service():
    """Build an authorized Sheets API service object."""
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not raw:
        raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON is not set")

    info = json.loads(raw)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _ensure_headers(service, sheet_id: str, sheet_name: str) -> None:
    """Write header row if the sheet is empty."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"{sheet_name}!A1:A1")
        .execute()
    )
    if not result.get("values"):
        headers = [ProcessedLead.sheet_headers()]
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="RAW",
            body={"values": headers},
        ).execute()
        logger.info("Header row written to sheet '%s'", sheet_name)


async def append_lead_to_sheet(lead: ProcessedLead) -> Optional[str]:
    """
    Appends one row to the Google Sheet.
    Returns the updated range string on success, None on failure.
    """
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Leads")

    if not sheet_id:
        logger.warning("GOOGLE_SHEET_ID not set — skipping Sheets write")
        return None

    try:
        service = _get_service()
        _ensure_headers(service, sheet_id, sheet_name)

        row = lead.to_sheet_row()
        body = {"values": [row]}

        result = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=sheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )

        updated_range = result.get("updates", {}).get("updatedRange", "unknown")
        logger.info("Lead %s written to Sheets: %s", lead.lead_id, updated_range)
        return updated_range

    except HttpError as exc:
        logger.error("Google Sheets API error: %s", exc)
        return None
    except Exception as exc:
        logger.error("Unexpected Sheets error: %s", exc)
        return None
