"""Walmart MCP Marketplace plugin.

Pulls the live MCP application registry from
https://dx.walmart.com/proxy/metaregistry/mcp-applications?environment=prod
and injects every entry as a catalog template so they appear in the
existing `/mcp install` TUI.

No new TUI needed — we just feed the existing browser. DRY for the win.
"""
