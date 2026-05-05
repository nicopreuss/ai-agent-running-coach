"""Core agent module: initializes the LangGraph ReAct agent and exposes a run() entrypoint."""

import logging
import os
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from agent.memory import load_athlete_context
from agent.prompts import SYSTEM_PROMPT
from agent.tools import get_tools

load_dotenv()

logger = logging.getLogger(__name__)

_SESSION_ID = str(uuid4())
_THREAD = {"configurable": {"thread_id": _SESSION_ID}}


def build_agent():
    """Instantiate and return the LangGraph ReAct agent with memory."""
    athlete_context = load_athlete_context()
    full_prompt = f"{SYSTEM_PROMPT}\n\n---\n\n{athlete_context}"

    llm = ChatOpenAI(
        model=os.environ["OPENAI_MODEL"],
        temperature=0,
        default_headers={"X-Session-ID": _SESSION_ID},
    )
    checkpointer = MemorySaver()
    return create_react_agent(
        llm,
        tools=get_tools(),
        prompt=SystemMessage(content=full_prompt),
        checkpointer=checkpointer,
    )


_agent = None


def run(query: str) -> dict[str, Any]:
    """Invoke the agent with *query* and return response text plus tool names used."""
    global _agent
    if _agent is None:
        # Context is frozen at first call; restart the process to pick up profile changes.
        _agent = build_agent()
    try:
        result = _agent.invoke(
            {"messages": [HumanMessage(content=query)]},
            config=_THREAD,
        )
        tools_used = [
            tc["name"]
            for msg in result["messages"]
            if msg.type == "ai"
            for tc in (msg.tool_calls or [])
        ]
        final = next(
            (
                msg.content
                for msg in reversed(result["messages"])
                if msg.type == "ai" and not msg.tool_calls
            ),
            "",
        )
        return {"response": final, "tools_used": tools_used}
    except Exception:
        logger.exception("Agent invocation failed for query: %s", query)
        raise
