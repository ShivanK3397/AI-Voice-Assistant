import logging

from langchain_community.tools import DuckDuckGoSearchRun
from livekit.agents import RunContext, function_tool


@function_tool
async def search_web(context: RunContext, query: str):
    """
    Search for information to answer a question. This does not open a browser.
    For opening or interacting with a website, use browser_open and browser tools.
    """

    try:
        result = DuckDuckGoSearchRun().run(tool_input=query)
        logging.info(f"Web search result for query '{query}': {result}")
        return result
    except Exception as e:
        logging.error(
            f"Error occurred while searching the web for query '{query}': {e}"
        )
        raise
