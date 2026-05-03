"""FastAPI application: health check, chat endpoint, and on-demand ingestion triggers."""

from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import agent.agent as agent_module
from ingestion import pipeline

_scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _scheduler.add_job(
        lambda: pipeline.run("whoop"),
        CronTrigger(hour=9, minute=0, timezone="Europe/Paris"),
        id="whoop_daily",
        replace_existing=True,
    )
    _scheduler.add_job(
        lambda: pipeline.run("strava"),
        CronTrigger(hour=20, minute=0, timezone="Europe/Paris"),
        id="strava_daily",
        replace_existing=True,
    )
    _scheduler.start()
    yield
    _scheduler.shutdown()


app = FastAPI(title="Running Coach AI", lifespan=lifespan)


# --- Request / response schemas -------------------------------------------


class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    response: str


class IngestResponse(BaseModel):
    status: str
    source: str
    records_inserted: int


# --- Routes ---------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe — returns 200 when the service is up."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Run the user query through the agent and return the response."""
    response = agent_module.run(request.query)
    return ChatResponse(response=response)


@app.post("/ingest/whoop", response_model=IngestResponse)
def ingest_whoop() -> IngestResponse:
    """Trigger an immediate Whoop ingestion run."""
    try:
        result = pipeline.run("whoop")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return IngestResponse(status="ok", source="whoop", records_inserted=result["records_inserted"])


@app.post("/ingest/strava", response_model=IngestResponse)
def ingest_strava() -> IngestResponse:
    """Trigger an immediate Strava ingestion run."""
    try:
        result = pipeline.run("strava")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return IngestResponse(status="ok", source="strava", records_inserted=result["records_inserted"])
