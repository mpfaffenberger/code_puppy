# Parallel Search MCP

Use Code Puppy's HTTP MCP transport to search the web and fetch page excerpts
with [Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp).
The anonymous endpoint requires no API key or OAuth. Free access is intended
for exploration and light use and has rate limits.

## Setup

From a checkout of Code Puppy, install its declared dependencies:

```sh
uv sync
```

In the project where you want to use web search, create
`.code_puppy/mcp_servers.json` using the adjacent [configuration](mcp_servers.json).
If the file already exists, merge the `parallel-search` entry into its
`mcp_servers` mapping instead of replacing your existing servers.
The example is opt-in and does not change your model or existing MCP bindings.

Start Code Puppy from that project's root (`uv run code-puppy` from this
checkout, or `code-puppy` with an installed copy). Review and accept the
project configuration:

```text
/mcp trust
/mcp trust accept
```

Exit and relaunch Code Puppy from the same project root after accepting trust
so the new server is initialized, then run:

```text
/mcp start parallel-search
/mcp status
```

Project MCP configuration is ignored until trusted. Editing it requires trusting
it again. Starting the server binds it to the current agent for this session.
For a persistent binding, use the agent's MCP binding menu under `/agents`.

## Use

Ask the current agent to use `parallel-search_web_search` to find Python's
asyncio documentation, then `parallel-search_web_fetch` to read the relevant
page. Search results include source URLs and excerpts; fetch returns page
excerpts. Your configured model must support tool calls.

The underlying tools accept these arguments:

```json
{
  "objective": "Find the official Python asyncio documentation",
  "search_queries": ["Python asyncio official documentation"]
}
```

```json
{
  "urls": ["https://docs.python.org/3/library/asyncio.html"],
  "objective": "Explain what asyncio is used for"
}
```

Queries and fetched URLs are sent to Parallel. The configuration uses only
Streamable HTTP, with a 30-second tool timeout and a Code Puppy User-Agent.
It intentionally omits authentication headers. If the free endpoint reports a
rate limit, wait for the indicated retry time before trying again.

To stop using it in the current session, run `/mcp stop parallel-search`.
To revoke project configuration trust, run `/mcp trust revoke`.
