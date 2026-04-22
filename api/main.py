"""FastAPI application: exposes a health check and a /chat endpoint backed by the agent."""

from fastapi import FastAPI
from pydantic import BaseModel

import agent.agent as agent_module

app = FastAPI(title="REPLACE WITH YOUR PROJECT NAME")


# --- Request / response schemas -------------------------------------------

class ChatRequest(BaseModel):
    query: str


class ChatResponse(BaseModel):
    response: str


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
