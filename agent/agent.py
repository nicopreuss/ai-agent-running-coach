"""Core agent module: initializes the LangChain ReAct agent and exposes a run() entrypoint."""

import logging
import os

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from agent.prompts import SYSTEM_PROMPT
from agent.tools import get_tools

load_dotenv()

logger = logging.getLogger(__name__)

# create_react_agent requires {tools}, {tool_names}, {input}, and {agent_scratchpad}.
# SYSTEM_PROMPT is pre-filled via .partial() so it isn't exposed as a runtime variable.
_REACT_TEMPLATE = (
    "{system_prompt}\n\n"
    "You have access to the following tools:\n\n{tools}\n\n"
    "Use the following format:\n\n"
    "Question: the input question you must answer\n"
    "Thought: you should always think about what to do\n"
    "Action: the action to take, should be one of [{tool_names}]\n"
    "Action Input: the input to the action\n"
    "Observation: the result of the action\n"
    "... (this Thought/Action/Action Input/Observation can repeat N times)\n"
    "Thought: I now know the final answer\n"
    "Final Answer: the final answer to the original input question\n\n"
    "Begin!\n\n"
    "Question: {input}\n"
    "Thought:{agent_scratchpad}"
)


def build_agent() -> AgentExecutor:
    """Instantiate and return the ReAct AgentExecutor."""
    llm = ChatOpenAI(
        model=os.environ["OPENAI_MODEL"],  # REPLACE: e.g. "gpt-4o"
        temperature=0,
    )

    # REGISTER YOUR TOOLS HERE — import from agent/tools.py and add to this list
    tools = get_tools()

    prompt = PromptTemplate.from_template(_REACT_TEMPLATE).partial(
        system_prompt=SYSTEM_PROMPT
    )

    agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)


_agent: AgentExecutor | None = None


def run(query: str) -> str:
    """Invoke the agent with *query* and return the text response."""
    global _agent
    if _agent is None:
        _agent = build_agent()

    try:
        result = _agent.invoke({"input": query})
        return result["output"]
    except Exception:
        logger.exception("Agent invocation failed for query: %s", query)
        raise
