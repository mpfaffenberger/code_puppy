"""DX Documentation plugin for Code Puppy.

Encapsulates all DX Developer Portal documentation functionality:
- Agent: DXDocsAgent for searching and reading DX docs
- Tools: dx_search, dx_semantic_search, dx_get_page_content, dx_get_tags, dx_authenticate
- Auth: mcp-cli token management for PingFed SSO
- Clients: DX MCP client and Tech Assistant semantic search client

All registration happens via the callback system in register_callbacks.py.
"""
