from typing import Dict

import requests
from pydantic_ai import RunContext

from code_puppy.messaging import (
    emit_error,
    emit_warning,
    emit_success,
    emit_info,
    emit_system_message,
)


def register_web_search_tools(agent):
    @agent.tool
    def grab_json_from_url(context: RunContext, url: str) -> Dict:
        # Import common functions

        try:
            response = requests.get(url)
            response.raise_for_status()
            ct = response.headers.get("Content-Type")
            if "json" not in str(ct):
                emit_error(
                    f"Response from {url} is not JSON (got {ct})"
                )
                return {"error": f"Response from {url} is not of type application/json"}
            json_data = response.json()
            if isinstance(json_data, list) and len(json_data) > 1000:
                emit_warning("Result list truncated to 1000 items")
                return json_data[:1000]
            if not json_data:
                emit_warning(f"No data found for URL: {url}")
            else:
                emit_success(f"Successfully fetched JSON from: {url}")
            return json_data
        except Exception as exc:
            emit_error(f"{exc}")
            return {"error": str(exc)}
