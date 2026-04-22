"""Tool definitions for the LangChain agent.

Add one function per tool, decorated with @tool. The docstring is what the LLM
reads to decide when and how to use the tool — make it precise and specific.
"""

from langchain_core.tools import tool


@tool
def example_tool(query: str) -> str:
    """Use this tool to REPLACE WITH WHAT THIS TOOL DOES.

    The docstring is the tool description seen by the LLM. Include:
    - When to use this tool (trigger condition)
    - What input it expects (format, constraints)
    - What it returns (shape of the output)

    Args:
        query: REPLACE WITH A DESCRIPTION OF THE INPUT PARAMETER.

    Returns:
        A string result that the agent will use to formulate its answer.
    """
    # REPLACE: add your DB query, external API call, or computation here
    return f"Placeholder result for query: {query}"


def get_tools() -> list:
    """Return the list of tools registered with the agent."""
    # ADD YOUR TOOLS TO THIS LIST as you define them above
    return [example_tool]
