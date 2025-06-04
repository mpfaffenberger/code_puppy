from typing import Dict
import requests
from pydantic_ai import RunContext

def register_web_search_tools(agent):
    @agent.tool
    def grab_json_from_url(context: RunContext, url: str) -> Dict:
        response = requests.get(url)
        response.raise_for_status()
        if response.headers.get('Content-Type') != 'application/json':
            raise ValueError(f"Response from {url} is not of type application/json")
        json_data = response.json()
        if isinstance(json_data, list) and len(json_data) > 1000:
            return json_data[:1000]
        return json_data
