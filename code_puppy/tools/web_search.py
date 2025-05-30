from code_puppy.agent import code_generation_agent
from typing import Dict
import requests
from pydantic_ai import RunContext


@code_generation_agent.tool
def grab_json_from_url(context: RunContext, url: str) -> Dict:
    """Grab JSON from a URL if the response is of type application/json.

    Args:
        url: The URL to grab the JSON from.

    Returns:
        Parsed JSON data if successful.

    Raises:
        ValueError: If response content type is not application/json.
    """
    response = requests.get(url)
    response.raise_for_status()

    if response.headers.get('Content-Type') != 'application/json':
        raise ValueError(f"Response from {{url}} is not of type application/json")

    json_data = response.json()

    # Limit to 1000 lines if the response is large
    if isinstance(json_data, list) and len(json_data) > 1000:
        return json_data[:1000]

    return json_data
