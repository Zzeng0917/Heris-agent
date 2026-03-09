"""Prompt for Web Search Tool.

This module defines the prompt and description for the web_search tool,
which is used to inform the LLM about the tool's functionality.
"""

TOOL_NAME = "web_search"

DESCRIPTION = """Search the web for real-time information and news.

This tool performs web searches to fetch the latest information that may not be
in the LLM's training data. Use it when:
- The user asks about recent events, news, or developments
- You need up-to-date information beyond your knowledge cutoff
- Real-time data like stock prices, weather, or current events is needed
- Verifying facts about recent happenings
"""

USAGE_EXAMPLE = """
# Search for latest news
web_search(query="Anthropic latest news 2026")

# Search for specific topic
web_search(query="OpenAI GPT-5 release date")

# Search with result limit
web_search(query="Apple stock price today", max_results=5)

# Get recent tech news
web_search(query="latest technology news March 2026")
"""

PROMPT = """When the user asks about recent events, news, or real-time information:

1. Recognize that your knowledge has a cutoff date and you cannot provide real-time info directly
2. Use `web_search` to fetch the latest information from the web
3. Formulate a clear, specific search query
4. Review the search results and extract relevant information
5. Present the findings to the user with proper attribution
6. If needed, perform additional searches to get more details

Best practices:
- Use specific keywords for better search results
- Include dates (year, month) for time-sensitive queries
- Combine multiple searches if the topic is complex
- Always inform the user that information comes from web search
- Cite the sources when providing information
"""

PARAMETERS = {
    "QUERY": {
        "type": "string",
        "description": "The search query string. Be specific and include relevant keywords for better results.",
        "required": True,
    },
    "MAX_RESULTS": {
        "type": "integer",
        "description": "Maximum number of search results to return (default: 10, max: 20).",
        "required": False,
    },
    "TIME_RANGE": {
        "type": "string",
        "description": "Time filter for results: 'day', 'week', 'month', 'year', or None for all time.",
        "required": False,
    },
}

RESPONSE_FORMAT = """The tool returns search results in the following format:

Search Results for "Anthropic latest news":

1. Title: Anthropic Announces New AI Model
   URL: https://example.com/news/anthropic-model
   Snippet: Anthropic has announced a breakthrough in AI safety research...
   Date: 2026-03-08

2. Title: Claude 4 Released with New Features
   URL: https://tech-news.example.com/claude-4
   Snippet: The latest version of Claude brings significant improvements...
   Date: 2026-03-05

Total results: 2
"""
