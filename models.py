"""
Lead data models with normalization logic.
Handles messy real-world form submissions gracefully.
"""

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


class LeadScore(str, Enum):
    HOT = "🔥 HOT"
    WARM = "🟡 WARM"
    COLD = "❄️ COLD"


class LeadSource(str, Enum):
    WEBSITE = "website"
    REFERRAL = "referral"
    SOCIAL = "social"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Raw incoming payload (permissive — accepts whatever the form sends)
# ---------------------------------------------------------------------------

class LeadRequest(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    company: Optional[str] = None
    budget: Optional[str] = None          # "5000", "$5,000", "5k", "до 10 000 грн"
    message: Optional[str] = None
    service: Optional[str] = None         # which service they're interested in
    source: Optional[str] = None          # utm_source / how they found us
    employees: Optional[str] = None       # company size: "10", "50-100", "500+"

    @field_validator("name")
    @classmethod
    def normalize_name(cls, v: str) -> str:
        """Trim whitespace, title-case the name."""
        return " ".join(v.strip().split()).title()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: Optional[str]) -> Optional[str]:
        """Strip formatting, keep digits and leading +."""
        if not v:
            return None
        digits = re.sub(r"[^\d+]", "", v.strip())
        # Ukrainian numbers: 0XXXXXXXXX → +380XXXXXXXXX
        if digits.startswith("0") and len(digits) == 10:
            digits = "+380" + digits[1:]
        return digits or None

    @field_validator("budget")
    @classmethod
    def normalize_budget(cls, v: Optional[str]) -> Optional[str]:
        """Try to extract a numeric USD/UAH value; keep original if ambiguous."""
        if not v:
            return None
        clean = v.strip()
        # Remove currency symbols and spaces
        numeric = re.sub(r"[^\d.,k]", "", clean.lower())
        # Handle shorthand like "5k" → "5000"
        if numeric.endswith("k"):
            try:
                return str(int(float(numeric[:-1]) * 1000))
            except ValueError:
                pass
        # Remove separators and return
        numeric = numeric.replace(",", "").replace(".", "")
        return numeric if numeric.isdigit() else clean

    @field_validator("company")
    @classmethod
    def normalize_company(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        return " ".join(v.strip().split())

    @field_validator("source")
    @classmethod
    def normalize_source(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        low = v.strip().lower()
        mapping = {
            "facebook": LeadSource.SOCIAL,
            "instagram": LeadSource.SOCIAL,
            "linkedin": LeadSource.SOCIAL,
            "google": LeadSource.WEBSITE,
            "organic": LeadSource.WEBSITE,
            "referral": LeadSource.REFERRAL,
            "friend": LeadSource.REFERRAL,
        }
        for key, mapped in mapping.items():
            if key in low:
                return mapped.value
        return LeadSource.OTHER.value


# ---------------------------------------------------------------------------
# Enriched / processed lead — written to Sheets & sent to Telegram
# ---------------------------------------------------------------------------

class ProcessedLead(BaseModel):
    # Original normalized fields
    name: str
    email: str
    phone: Optional[str]
    company: Optional[str]
    budget: Optional[str]
    message: Optional[str]
    service: Optional[str]
    source: Optional[str]
    employees: Optional[str]

    # AI-generated enrichment
    ai_summary: str
    classification: LeadScore
    classification_reason: str

    # Metadata
    received_at: str = ""
    lead_id: str = ""

    @model_validator(mode="before")
    @classmethod
    def set_metadata(cls, values):
        if not values.get("received_at"):
            values["received_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        if not values.get("lead_id"):
            import uuid
            values["lead_id"] = str(uuid.uuid4())[:8].upper()
        return values

    def to_sheet_row(self) -> list:
        """Flat list for Google Sheets append."""
        return [
            self.lead_id,
            self.received_at,
            self.name,
            self.email,
            self.phone or "",
            self.company or "",
            self.employees or "",
            self.budget or "",
            self.service or "",
            self.source or "",
            self.message or "",
            self.classification,
            self.classification_reason,
            self.ai_summary,
        ]

    @staticmethod
    def sheet_headers() -> list:
        return [
            "ID", "Received At", "Name", "Email", "Phone",
            "Company", "Employees", "Budget", "Service",
            "Source", "Message", "Classification",
            "Classification Reason", "AI Summary",
        ]
