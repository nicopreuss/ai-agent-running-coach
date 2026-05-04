# LangGraph Migration Design

## Goal

Migrate the running coach agent from the old LangChain `AgentExecutor` + text-based ReAct framework to `langgraph.prebuilt.create_react_agent`, fixing iteration limit failures, correcting the proxy session header, and adding conversational memory.

## Architecture

Two files change: `agent/agent.py` (full rewrite of `build_agent()` and `run()`) and `tests/test_agent.py` (updated mocks). All other files — `agent/tools.py`, `agent/prompts.py`, `api/main.py`, `ui/app.py`, `tests/test_chat_endpoint.py` — are untouched. The public `run()` interface stays identical: accepts a `str`, returns `{"response": str, "tools_used": list[str]}`.

## Tech Stack

- `langgraph.prebuilt.create_react_agent` — replaces `langchain.agents.create_react_agent` + `AgentExecutor`
- `langgraph.checkpoint.memory.MemorySaver` — in-memory conversation checkpointer
- `langchain_core.messages.SystemMessage`, `HumanMessage` — LangGraph's message format
- `langchain_openai.ChatOpenAI` — unchanged, but `user=` replaced with `default_headers={"X-Session-ID": ...}`

## Components

### `_SESSION_ID` (module-level constant)

A UUID generated once when `agent.agent` is first imported. Used as both the `X-Session-ID` request header and the LangGraph `thread_id`. Fixed for the lifetime of the server process — memory clears on restart.

### `build_agent()`

Constructs the LangGraph agent:

```python
def build_agent():
    llm = ChatOpenAI(
        model=os.environ["OPENAI_MODEL"],
        temperature=0,
        default_headers={"X-Session-ID": _SESSION_ID},
    )
    checkpointer = MemorySaver()
    return create_react_agent(
        llm,
        tools=get_tools(),
        prompt=SystemMessage(content=SYSTEM_PROMPT),
        checkpointer=checkpointer,
    )
```

Removes: `AgentExecutor`, `PromptTemplate`, `_REACT_TEMPLATE`, `handle_parsing_errors`, `user=` field.

### `run(query: str) -> dict[str, Any]`

Invokes the agent with LangGraph's message format, parses the response:

```python
_THREAD = {"configurable": {"thread_id": _SESSION_ID}}

def run(query: str) -> dict[str, Any]:
    global _agent
    if _agent is None:
        _agent = build_agent()
    result = _agent.invoke({"messages": [HumanMessage(content=query)]}, config=_THREAD)
    tools_used = [
        tc["name"]
        for msg in result["messages"]
        if hasattr(msg, "tool_calls")
        for tc in (msg.tool_calls or [])
    ]
    final = next(
        (msg.content for msg in reversed(result["messages"])
         if msg.type == "ai" and not msg.tool_calls),
        "",
    )
    return {"response": final, "tools_used": tools_used}
```

## Data Flow

```
ui/app.py
  → POST /chat  (query: str)
  → api/main.py  (unchanged)
  → agent.run(query)
      → LangGraph agent.invoke({"messages": [HumanMessage]}, config=_THREAD)
          → ChatOpenAI  (X-Session-ID header → bootcamp proxy)
          → tool calls if needed  (refresh_data)
      → parse result["messages"] → response str + tools_used list
  → ChatResponse(response, tools_used)
  → rendered in Streamlit chat panel
```

## Memory Behaviour

`MemorySaver` stores the full message history keyed by `thread_id` in memory. Every `run()` call appends to the same thread, so the agent sees all prior turns in the conversation. Memory is lost when the API server restarts. This is acceptable for a single-user personal project with no cross-session memory requirement.

## Error Handling

- `run()` lets exceptions propagate — `api/main.py` catches them and returns HTTP 500 (unchanged behaviour).
- If `result["messages"]` contains no final AI message, `run()` returns `""` as the response rather than raising.

## Testing

`tests/test_agent.py` is rewritten to mock the LangGraph agent's `.invoke()` return value — a dict with a `"messages"` key containing mock message objects. Three test cases:

1. `run()` returns correct `response` and empty `tools_used` when no tools called.
2. `run()` extracts tool names from `msg.tool_calls` on AI messages.
3. `run()` re-raises exceptions from the agent.

`tests/test_chat_endpoint.py` is unchanged — it patches `agent_module.run()` directly and is unaffected by the internal implementation change.

## Out of Scope

- Data tools (`get_recent_stats`, `analyze_performance_vs_recovery`, `get_upcoming_sessions`) — Phase 3.
- Streaming (`astream_events`, SSE) — future phase.
- Persistent cross-session memory (database-backed checkpointer) — not needed for single-user project.
- Per-request `thread_id` — single global thread is correct for this use case.
