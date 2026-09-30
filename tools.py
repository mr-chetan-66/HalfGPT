import math
import json
import os
from contextvars import ContextVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_tavily import TavilySearch
from database import save_memory, search_memory
from rag import retrieve_from_rag



load_dotenv()


CURRENT_THREAD_ID = ContextVar("current_thread_id", default="default")
CURRENT_PROFILE_ID = ContextVar("current_profile_id", default=None)


def set_tool_context(thread_id: str, profile_id: str | None = None):
    return (
        CURRENT_THREAD_ID.set(thread_id),
        CURRENT_PROFILE_ID.set(profile_id)
    )


def reset_tool_context(tokens):
    thread_token, profile_token = tokens
    CURRENT_PROFILE_ID.reset(profile_token)
    CURRENT_THREAD_ID.reset(thread_token)


def memory_scopes():
    scopes = [CURRENT_THREAD_ID.get()]
    profile_id = CURRENT_PROFILE_ID.get()

    if profile_id:
        scopes.insert(0, f"profile:{profile_id}")

    return list(dict.fromkeys(scopes))


@tool
def web_search(query: str) -> str:
    """Search the web for current information."""
    search = TavilySearch(
        max_results=3,
        topic="general",
        search_depth="basic"
    )
    response = search.invoke({"query": query})

    try:
        results = json.loads(response) if isinstance(response, str) else response
    except json.JSONDecodeError:
        return str(response)[:2000]

    concise_results = [
        {
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "content": (result.get("content") or result.get("snippet") or "")[:500]
        }
        for result in results.get("results", [])[:3]
        if isinstance(result, dict)
    ]

    return json.dumps(
        {
            "query": results.get("query", query),
            "answer": (results.get("answer") or "")[:500],
            "results": concise_results
        },
        ensure_ascii=False
    )


@tool
def google_search(query: str) -> str:
    """Search Google for current information, falling back to Tavily if Google Search is unavailable."""
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    search_engine_id = os.getenv("GOOGLE_CSE_ID")

    if api_key and search_engine_id:
        params = urlencode({
            "key": api_key,
            "cx": search_engine_id,
            "q": query,
            "num": 3,
            "safe": "active"
        })

        try:
            with urlopen(
                f"https://www.googleapis.com/customsearch/v1?{params}",
                timeout=10
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))

            results = [
                {
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "content": (item.get("snippet") or "")[:500]
                }
                for item in payload.get("items", [])[:3]
            ]

            if results:
                return json.dumps(
                    {"provider": "Google Search", "query": query, "results": results},
                    ensure_ascii=False
                )
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            pass

    return web_search.invoke({"query": query})


@tool
def calculator(expression: str) -> str:
    """
    Useful for simple math calculations.
    Input should be a valid math expression.
    Example: 2 + 2, math.sqrt(16), 10 * 5
    """

    try:
        allowed = {
            "math": math,
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum
        }

        result = eval(expression, {"__builtins__": {}}, allowed)
        return str(result)

    except Exception as e:
        return f"Calculation error: {str(e)}"
    


@tool
def search_uploaded_documents(query: str) -> str:
    """
    Search uploaded documents for relevant information.
    Use this when the user asks about uploaded PDFs, DOCX, TXT, notes, files, or documents.
    """

    return retrieve_from_rag(
        query=query,
        thread_id=CURRENT_THREAD_ID.get()
    )




@tool
def remember_this(memory: str) -> str:
    """
    Save an important user preference or fact into long-term memory.
    Use this when the user asks you to remember something.
    """

    scopes = memory_scopes()

    for scope in scopes:
        save_memory(thread_id=scope, memory=memory)

    if CURRENT_PROFILE_ID.get():
        return "Memory saved for this chat and future chats in this browser."

    return "Memory saved successfully."



@tool
def recall_memory(query: str) -> str:
    """
    Recall saved long-term memories about the user or this conversation.
    """

    memories = []
    seen = set()

    for scope in memory_scopes():
        result = search_memory(thread_id=scope, query=query)

        for line in result.splitlines():
            if not line.startswith("- "):
                continue

            memory = line[2:].strip()
            key = memory.casefold()

            if memory and key not in seen:
                memories.append(memory)
                seen.add(key)

    if not memories:
        return "No saved memory found."

    return "\n".join(f"- {memory}" for memory in memories[:10])





tools = [
    calculator,
    search_uploaded_documents,
    remember_this,
    recall_memory,
    web_search,
    google_search,
]