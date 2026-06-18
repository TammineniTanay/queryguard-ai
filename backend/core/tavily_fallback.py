from tavily import TavilyClient
from dotenv import load_dotenv
import os

load_dotenv()

client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


def web_search(question):
    """
    Used when internal data can't answer the question.
    Returns the answer and sources from the web.
    """
    try:
        response = client.search(query=question, search_depth="basic", max_results=3)
        results = response.get("results", [])

        if not results:
            return {"found": False, "answer": None, "sources": []}

        answer = response.get("answer") or results[0].get("content", "")
        sources = [r.get("url") for r in results]

        return {"found": True, "answer": answer, "sources": sources}

    except Exception as e:
        return {"found": False, "answer": None, "error": str(e)}
