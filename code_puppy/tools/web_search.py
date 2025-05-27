from code_puppy.agent import code_generation_agent
from typing import List, Dict
import requests
from bs4 import BeautifulSoup
from pydantic_ai import RunContext


@code_generation_agent.tool
def web_search(
    context: RunContext, query: str, num_results: int = 5
) -> List[Dict[str, str]]:
    """Perform a web search and return a list of results with titles and URLs.

    Args:
        query: The search query.
        num_results: Number of results to return. Defaults to 5.

    Returns:
        A list of dictionaries, each containing 'title' and 'url' for a search result.
    """
    search_url = "https://www.google.com/search"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }
    params = {"q": query}

    response = requests.get(search_url, headers=headers, params=params)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    for g in soup.find_all("div", class_="tF2Cxc")[:num_results]:
        title_element = g.find("h3")
        link_element = g.find("a")
        if title_element and link_element:
            title = title_element.get_text()
            url = link_element["href"]
            results.append({"title": title, "url": url})

    return results
