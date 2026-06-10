"""
Lead Processing API — main entry point.

Endpoints:
    POST /webhook/lead   — accept a lead form submission
    GET  /health         — liveness check
    GET  /               — basic info page
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, HTMLResponse

from ai_service import analyze_lead
from models import LeadRequest, ProcessedLead
from sheets import append_lead_to_sheet
from telegram import send_telegram_notification

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Lead Processor starting up")
    yield
    logger.info("👋 Lead Processor shutting down")


app = FastAPI(
    title="Lead Processor API",
    description="MVP pipeline: receive → normalize → AI summary → classify → Sheets → Telegram",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    return """
    <html><body style="font-family:sans-serif;padding:2rem">
    <h2>🎯 Lead Processor API</h2>
    <p>Send a <code>POST /webhook/lead</code> with a JSON body to process a lead.</p>
    <p><a href="/docs">📖 Interactive docs (Swagger UI)</a></p>
    </body></html>
    """


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post(
    "/webhook/lead",
    status_code=status.HTTP_200_OK,
    summary="Process an incoming lead form submission",
    response_description="Processing result with lead ID and classification",
)
async def process_lead(payload: LeadRequest):
    """
    Full pipeline:
    1. Validate & normalize the incoming JSON (handled by Pydantic).
    2. Send to Claude for AI summary + classification.
    3. Persist to Google Sheets.
    4. Send Telegram notification.
    5. Return a summary response.

    All downstream failures (Sheets / Telegram) are non-fatal — the endpoint
    always returns 200 if the lead was received and processed by AI.
    """
    logger.info("New lead received: %s <%s>", payload.name, payload.email)

    # Step 1: AI analysis
    summary, classification, reason = await analyze_lead(payload)
    logger.info("Lead classified as %s", classification)

    # Step 2: Build enriched lead object
    lead = ProcessedLead(
        **payload.model_dump(),
        ai_summary=summary,
        classification=classification,
        classification_reason=reason,
    )

    # Step 3 & 4: Sheets + Telegram run concurrently to save time
    sheet_task = asyncio.create_task(append_lead_to_sheet(lead))
    telegram_task = asyncio.create_task(send_telegram_notification(lead))

    sheet_result, telegram_result = await asyncio.gather(
        sheet_task, telegram_task, return_exceptions=True
    )

    # Log but don't fail on downstream errors
    if isinstance(sheet_result, Exception):
        logger.error("Sheets task raised: %s", sheet_result)
    if isinstance(telegram_result, Exception):
        logger.error("Telegram task raised: %s", telegram_result)

    return {
        "success": True,
        "lead_id": lead.lead_id,
        "received_at": lead.received_at,
        "classification": lead.classification,
        "ai_summary": lead.ai_summary,
        "destinations": {
            "google_sheets": bool(sheet_result and not isinstance(sheet_result, Exception)),
            "telegram": bool(telegram_result and not isinstance(telegram_result, Exception)),
        },
    }


# ---------------------------------------------------------------------------
# Global error handler — always return JSON, never expose stack traces
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"},
    )


# ---------------------------------------------------------------------------
# Dev runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
    )
