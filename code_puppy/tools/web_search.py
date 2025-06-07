from typing import Dict

import requests
from pydantic_ai import RunContext


def register_web_search_tools(agent):
    @agent.tool
    def grab_json_from_url(context: RunContext, url: str) -> Dict:
        from code_puppy.tools.common import console

        try:
            response = requests.get(url)
            response.raise_for_status()
            ct = response.headers.get("Content-Type")
            if "json" not in str(ct):
                console.print(
                    f"[bold red]Error:[/bold red] Response from {url} is not JSON (got {ct})"
                )
                return {"error": f"Response from {url} is not of type application/json"}
            json_data = response.json()
            if isinstance(json_data, list) and len(json_data) > 1000:
                console.print("[yellow]Result list truncated to 1000 items[/yellow]")
                return json_data[:1000]
            if not json_data:
                console.print("[yellow]No data found for URL:[/yellow]", url)
            else:
                console.print(f"[green]Successfully fetched JSON from:[/green] {url}")
            return json_data
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            return {"error": str(exc)}
