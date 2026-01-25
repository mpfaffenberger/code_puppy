"""Agent Marketplace tools for searching, downloading, and uploading agents.

These tools provide programmatic access to the Agent Marketplace for use by
agents (including agent-creator). All tools use synchronous wrappers around
the async API client.
"""

import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

# =============================================================================
# Output Models
# =============================================================================


class MarketplaceSearchOutput(BaseModel):
    """Output from marketplace search."""

    agents: List[dict] = Field(
        default_factory=list, description="List of matching agents"
    )
    total: int = Field(default=0, description="Total number of results")
    has_more: bool = Field(default=False, description="Whether more results exist")
    error: Optional[str] = Field(
        default=None, description="Error message if search failed"
    )


class MarketplaceDownloadOutput(BaseModel):
    """Output from marketplace download."""

    success: bool
    agent_name: Optional[str] = None
    version: Optional[int] = None
    content_hash: Optional[str] = None
    saved_path: Optional[str] = None
    error: Optional[str] = None


class MarketplaceUploadOutput(BaseModel):
    """Output from marketplace upload."""

    success: bool
    agent_name: Optional[str] = None
    version: Optional[int] = None
    content_hash: Optional[str] = None
    access_level: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class MarketplaceCheckUpdateOutput(BaseModel):
    """Output from checking for agent updates."""

    success: bool
    has_update: bool = False
    local_version: Optional[int] = None
    latest_version: Optional[int] = None
    local_hash: Optional[str] = None
    latest_hash: Optional[str] = None
    error: Optional[str] = None


class MarketplaceAuthOutput(BaseModel):
    """Output from marketplace authentication."""

    success: bool
    message: str
    user_email: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# Constants
# =============================================================================

AGENTS_DIR = Path.home() / ".code_puppy" / "agents"
MARKETPLACE_BASE_URL = "https://puppy.walmart.com/marketplace"

VALID_CATEGORIES = ["automation", "data", "review", "security", "custom"]
VALID_SORT_OPTIONS = ["downloads", "rating", "recent", "name"]
VALID_ACCESS_LEVELS = ["public", "private", "ad_group"]


# =============================================================================
# Tool Functions
# =============================================================================


def marketplace_search_agents(
    query: str = "",
    category: Optional[str] = None,
    tags: Optional[List[str]] = None,
    sort: str = "downloads",
    limit: int = 10,
) -> MarketplaceSearchOutput:
    """
    Search the Agent Marketplace for community-created agents.

    Args:
        query: Text search query (searches name and description)
        category: Filter by category (automation, data, review, security, custom)
        tags: Filter by tags (e.g., ["sql", "python"])
        sort: Sort order (downloads, rating, recent, name)
        limit: Maximum results to return (default 10, max 50)

    Returns:
        MarketplaceSearchOutput with list of matching agents
    """
    # Import here to avoid circular imports and handle missing dependencies
    try:
        from code_puppy.plugins.agent_marketplace import run_async, search_agents
    except ImportError:
        return MarketplaceSearchOutput(
            error="Marketplace API client not available. Is code-puppy installed correctly?"
        )

    # Validate inputs
    if category and category not in VALID_CATEGORIES:
        return MarketplaceSearchOutput(
            error=f"Invalid category '{category}'. Must be one of: {', '.join(VALID_CATEGORIES)}"
        )

    if sort not in VALID_SORT_OPTIONS:
        return MarketplaceSearchOutput(
            error=f"Invalid sort option '{sort}'. Must be one of: {', '.join(VALID_SORT_OPTIONS)}"
        )

    # Clamp limit to valid range
    limit = max(1, min(50, limit))

    try:
        response = run_async(
            search_agents(
                query=query if query else None,
                category=category,
                tags=tags,
                sort=sort,
                limit=limit,
            )
        )

        if not response.get("success"):
            return MarketplaceSearchOutput(error=response.get("error", "Search failed"))

        # API returns: {data: [...agents], pagination: {total, has_more, ...}}
        # Or older format: {data: {agents: [...], total: ...}}
        raw_data = response.get("data", {})

        # Handle both formats
        if isinstance(raw_data, list):
            # New format: data is the agents array directly
            agents = raw_data
            pagination = response.get("pagination", {})
            total = pagination.get("total", len(agents))
            has_more = pagination.get("has_more", False)
        else:
            # Old format: data.agents and data.total
            agents = raw_data.get("agents", [])
            total = raw_data.get("total", len(agents))
            has_more = total > limit

        # Filter to only show the latest version of each agent
        agents = _filter_latest_versions(agents)

        return MarketplaceSearchOutput(
            agents=agents,
            total=len(agents),  # Update total to reflect filtered count
            has_more=has_more,
        )

    except Exception as e:
        return MarketplaceSearchOutput(error=f"Search error: {e}")


def marketplace_download_agent(
    name: str,
    force: bool = False,
) -> MarketplaceDownloadOutput:
    """
    Download an agent from the marketplace to local storage.

    Args:
        name: Name of the agent to download (e.g., "data-analyzer")
        force: If True, download even if local version exists

    Returns:
        MarketplaceDownloadOutput with download result

    Note: Downloaded agents are saved to ~/.code_puppy/agents/<name>.json
    """
    try:
        from code_puppy.plugins.agent_marketplace import download_agent, run_async
    except ImportError:
        return MarketplaceDownloadOutput(
            success=False,
            error="Marketplace API client not available. Is code-puppy installed correctly?",
        )

    if not name or not name.strip():
        return MarketplaceDownloadOutput(
            success=False,
            error="Agent name is required",
        )

    name = name.strip().lower()
    local_path = AGENTS_DIR / f"{name}.json"

    # Check if already exists
    if local_path.exists() and not force:
        return MarketplaceDownloadOutput(
            success=False,
            agent_name=name,
            saved_path=str(local_path),
            error=f"Agent '{name}' already exists locally. Use force=True to overwrite.",
        )

    try:
        response = run_async(download_agent(name))

        if not response.get("success"):
            return MarketplaceDownloadOutput(
                success=False,
                agent_name=name,
                error=response.get("error", "Download failed"),
            )

        data = response.get("data", {})
        agent_data = data.get("agent")
        version = data.get("version", 1)
        content_hash = data.get("content_hash") or data.get("hash")

        if not agent_data:
            return MarketplaceDownloadOutput(
                success=False,
                agent_name=name,
                error="Invalid response: missing agent data",
            )

        # Ensure directory exists
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)

        # Save agent to local file
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(agent_data, f, indent=2)

        # Save hash for update checking
        _save_download_hash(name, content_hash, version)

        return MarketplaceDownloadOutput(
            success=True,
            agent_name=name,
            version=version,
            content_hash=content_hash,
            saved_path=str(local_path),
        )

    except Exception as e:
        return MarketplaceDownloadOutput(
            success=False,
            agent_name=name,
            error=f"Download error: {e}",
        )


def marketplace_upload_agent(
    file_path: str,
    category: str = "custom",
    tags: Optional[List[str]] = None,
    access_level: str = "public",
    ad_group: Optional[str] = None,
) -> MarketplaceUploadOutput:
    """
    Upload a JSON agent file to the marketplace.

    Args:
        file_path: Path to the agent JSON file
        category: Agent category (automation, data, review, security, custom)
        tags: List of tags for discoverability
        access_level: Access control (public, private, ad_group)
        ad_group: Required if access_level is "ad_group"

    Returns:
        MarketplaceUploadOutput with upload result
    """
    try:
        from code_puppy.plugins.agent_marketplace import run_async, upload_agent
        from code_puppy.plugins.agent_marketplace.upload import (
            generate_agent_hash,
            load_agent_file,
            save_local_hash,
            validate_agent_data,
        )
    except ImportError:
        return MarketplaceUploadOutput(
            success=False,
            error="Marketplace API client not available. Is code-puppy installed correctly?",
        )

    # Validate category
    if category not in VALID_CATEGORIES:
        return MarketplaceUploadOutput(
            success=False,
            error=f"Invalid category '{category}'. Must be one of: {', '.join(VALID_CATEGORIES)}",
        )

    # Validate access level
    if access_level not in VALID_ACCESS_LEVELS:
        return MarketplaceUploadOutput(
            success=False,
            error=f"Invalid access_level '{access_level}'. Must be one of: {', '.join(VALID_ACCESS_LEVELS)}",
        )

    # AD group required for ad_group access
    if access_level == "ad_group" and not ad_group:
        return MarketplaceUploadOutput(
            success=False,
            error="ad_group parameter is required when access_level is 'ad_group'",
        )

    # Load the agent file
    agent_data, error = load_agent_file(file_path)
    if error:
        return MarketplaceUploadOutput(
            success=False,
            error=error,
        )

    # Validate agent data
    is_valid, errors = validate_agent_data(agent_data)
    if not is_valid:
        return MarketplaceUploadOutput(
            success=False,
            error=f"Validation failed: {'; '.join(errors)}",
        )

    # Generate content hash
    content_hash = generate_agent_hash(agent_data)
    agent_name = agent_data["name"]

    # Clean tags
    clean_tags = []
    if tags:
        clean_tags = [t.strip().lower() for t in tags if t.strip()]
        clean_tags = list(dict.fromkeys(clean_tags))  # Dedupe preserving order

    # Build payload - flatten agent_data into the payload
    # API expects: {name, display_name, description, system_prompt, tools, ...}
    payload = {
        **agent_data,  # Spread the agent fields at top level
        "tags": clean_tags,
        "category": category,
        "access_level": access_level,
    }
    if ad_group:
        payload["ad_group"] = ad_group

    try:
        response = run_async(upload_agent(payload))

        if not response.get("success"):
            error_msg = response.get("error", "Upload failed")
            status_code = response.get("status_code", 0)

            # Handle "no changes" as a soft success
            if status_code == 409:
                return MarketplaceUploadOutput(
                    success=True,
                    agent_name=agent_name,
                    content_hash=content_hash,
                    error="No changes detected - agent is identical to marketplace version",
                )

            return MarketplaceUploadOutput(
                success=False,
                agent_name=agent_name,
                error=error_msg,
            )

        data = response.get("data", {})
        version = data.get("version", 1)
        server_hash = data.get("hash", content_hash)
        url = data.get("url", f"{MARKETPLACE_BASE_URL}/{agent_name}")

        # Save hash locally for future comparisons
        save_local_hash(agent_name, content_hash, version)

        return MarketplaceUploadOutput(
            success=True,
            agent_name=agent_name,
            version=version,
            content_hash=server_hash,
            access_level=access_level,
            url=url,
        )

    except Exception as e:
        return MarketplaceUploadOutput(
            success=False,
            agent_name=agent_data.get("name"),
            error=f"Upload error: {e}",
        )


def marketplace_check_update(
    name: str,
) -> MarketplaceCheckUpdateOutput:
    """
    Check if a local agent has an update available in the marketplace.

    Args:
        name: Name of the agent to check

    Returns:
        MarketplaceCheckUpdateOutput with update info
    """
    try:
        from code_puppy.plugins.agent_marketplace import check_update, run_async
        from code_puppy.plugins.agent_marketplace.upload import get_local_hash
    except ImportError:
        return MarketplaceCheckUpdateOutput(
            success=False,
            error="Marketplace API client not available. Is code-puppy installed correctly?",
        )

    if not name or not name.strip():
        return MarketplaceCheckUpdateOutput(
            success=False,
            error="Agent name is required",
        )

    name = name.strip().lower()

    # Get local hash info
    local_info = get_local_hash(name)
    if not local_info:
        # Check if we have the agent file at least
        local_path = AGENTS_DIR / f"{name}.json"
        if not local_path.exists():
            return MarketplaceCheckUpdateOutput(
                success=False,
                error=f"Agent '{name}' not found locally. Download it first.",
            )
        # File exists but no hash - compute it
        try:
            from code_puppy.plugins.agent_marketplace.upload import generate_agent_hash

            with open(local_path, "r", encoding="utf-8") as f:
                agent_data = json.load(f)
            local_hash = generate_agent_hash(agent_data)
            local_version = None
        except Exception as e:
            return MarketplaceCheckUpdateOutput(
                success=False,
                error=f"Could not read local agent file: {e}",
            )
    else:
        local_hash = local_info.get("hash")
        local_version = local_info.get("version")

    try:
        response = run_async(check_update(name, local_hash))

        if not response.get("success"):
            return MarketplaceCheckUpdateOutput(
                success=False,
                error=response.get("error", "Check update failed"),
            )

        data = response.get("data", {})
        has_update = data.get("has_update", False)
        latest_version = data.get("latest_version") or data.get("version")
        latest_hash = data.get("latest_hash") or data.get("hash")

        return MarketplaceCheckUpdateOutput(
            success=True,
            has_update=has_update,
            local_version=local_version,
            latest_version=latest_version,
            local_hash=local_hash,
            latest_hash=latest_hash,
        )

    except Exception as e:
        return MarketplaceCheckUpdateOutput(
            success=False,
            error=f"Check update error: {e}",
        )


# =============================================================================
# Helper Functions
# =============================================================================


def _filter_latest_versions(agents: List[dict]) -> List[dict]:
    """Filter agents to only show the most recent version of each agent.

    Args:
        agents: List of agent dictionaries from marketplace API

    Returns:
        List of agents with only the latest version of each agent name
    """
    if not agents:
        return agents

    # Group agents by name and track the latest version
    latest_by_name = {}

    for agent in agents:
        name = agent.get("name")
        if not name:
            continue

        version = agent.get("version", 1)

        # If we haven't seen this agent, or this is a newer version, keep it
        if name not in latest_by_name or version > latest_by_name[name].get(
            "version", 1
        ):
            latest_by_name[name] = agent

    # Return the filtered list, preserving the original order where possible
    # by keeping the first occurrence of each agent name
    seen_names = set()
    result = []

    for agent in agents:
        name = agent.get("name")
        if name and name not in seen_names:
            seen_names.add(name)
            result.append(latest_by_name[name])

    return result


def _save_download_hash(name: str, content_hash: str, version: int) -> None:
    """Save downloaded agent hash to local registry."""
    try:
        from code_puppy.plugins.agent_marketplace.upload import save_local_hash

        if content_hash:
            save_local_hash(name, content_hash, version)
    except ImportError:
        pass  # Hash tracking not available, but download still succeeded


# =============================================================================
# Register Functions (for agent-based registration)
# =============================================================================


def register_marketplace_search_agents(agent):
    """Register the marketplace_search_agents tool."""
    from pydantic_ai import RunContext

    @agent.tool
    def marketplace_search_agents_tool(
        context: RunContext,
        query: str = "",
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        sort: str = "downloads",
        limit: int = 10,
    ) -> MarketplaceSearchOutput:
        """Search the Agent Marketplace for community-created agents.

        Args:
            context: The run context (injected automatically)
            query: Text search query (searches name and description)
            category: Filter by category (automation, data, review, security, custom)
            tags: Filter by tags (e.g., ["sql", "python"])
            sort: Sort order (downloads, rating, recent, name)
            limit: Maximum results to return (default 10, max 50)

        Returns:
            MarketplaceSearchOutput with matching agents or error
        """
        return marketplace_search_agents(query, category, tags, sort, limit)


def register_marketplace_download_agent(agent):
    """Register the marketplace_download_agent tool."""
    from pydantic_ai import RunContext

    @agent.tool
    def marketplace_download_agent_tool(
        context: RunContext,
        name: str,
        version: Optional[int] = None,
    ) -> MarketplaceDownloadOutput:
        """Download an agent from the marketplace to your local agents directory.

        Args:
            context: The run context (injected automatically)
            name: Name of the agent to download
            version: Specific version to download (default: latest)

        Returns:
            MarketplaceDownloadOutput with download result or error
        """
        return marketplace_download_agent(name, version)


def register_marketplace_upload_agent(agent):
    """Register the marketplace_upload_agent tool."""
    from pydantic_ai import RunContext

    @agent.tool
    def marketplace_upload_agent_tool(
        context: RunContext,
        file_path: str,
        category: str = "custom",
        tags: Optional[List[str]] = None,
        access_level: str = "public",
        ad_group: Optional[str] = None,
    ) -> MarketplaceUploadOutput:
        """Upload/publish an agent to the Agent Marketplace.

        Args:
            context: The run context (injected automatically)
            file_path: Path to the agent JSON file to upload
            category: Category for the agent (automation, data, review, security, custom)
            tags: Tags to help with discovery (e.g., ["python", "testing"])
            access_level: Who can download (public, private, ad_group)
            ad_group: Required AD group name if access_level is 'ad_group'

        Returns:
            MarketplaceUploadOutput with upload result or error
        """
        return marketplace_upload_agent(
            file_path, category, tags, access_level, ad_group
        )


def register_marketplace_check_update(agent):
    """Register the marketplace_check_update tool."""
    from pydantic_ai import RunContext

    @agent.tool
    def marketplace_check_update_tool(
        context: RunContext,
        name: str,
    ) -> MarketplaceCheckUpdateOutput:
        """Check if a locally installed agent has updates available.

        Args:
            context: The run context (injected automatically)
            name: Name of the agent to check

        Returns:
            MarketplaceCheckUpdateOutput with update status or error
        """
        return marketplace_check_update(name)


def register_marketplace_authenticate(agent):
    """Register the marketplace_authenticate tool."""
    from pydantic_ai import RunContext

    @agent.tool
    def marketplace_authenticate_tool(
        context: RunContext,
    ) -> MarketplaceAuthOutput:
        """Trigger authentication flow for the Agent Marketplace.

        Opens a browser window for the user to authenticate via PingFed SSO.
        After successful authentication, the token is saved for marketplace API calls.

        Use this when marketplace operations fail due to authentication errors,
        or when the user needs to log in for the first time.

        Args:
            context: The run context (injected automatically)

        Returns:
            MarketplaceAuthOutput with authentication result
        """
        return marketplace_authenticate()


def marketplace_authenticate() -> MarketplaceAuthOutput:
    """
    Trigger the Puppy site authentication flow.

    Opens a browser for the user to authenticate via PingFed SSO,
    then saves the token for marketplace API calls.

    Returns:
        MarketplaceAuthOutput with authentication result
    """
    try:
        from code_puppy.plugins.walmart_specific.pingfed_auth import (
            handle_puppy_auth_command,
        )
    except ImportError:
        return MarketplaceAuthOutput(
            success=False,
            message="Authentication module not available",
            error="walmart_specific plugin not installed",
        )

    try:
        # Trigger the /puppy_auth command handler
        result = handle_puppy_auth_command("/puppy_auth", "puppy_auth")

        if result:
            # Check if token was saved
            try:
                from code_puppy.config import get_value

                token = get_value("marketplace_token")

                if token:
                    # Try to get user email from saved token data
                    user_email = None
                    try:
                        import json
                        from pathlib import Path

                        token_file = (
                            Path.home() / ".code_puppy" / "marketplace_token.json"
                        )
                        if token_file.exists():
                            with open(token_file) as f:
                                token_data = json.load(f)
                                user_email = token_data.get("user", {}).get("email")
                    except Exception:
                        pass

                    return MarketplaceAuthOutput(
                        success=True,
                        message="Authentication successful! You can now use marketplace features.",
                        user_email=user_email,
                    )
                else:
                    return MarketplaceAuthOutput(
                        success=False,
                        message="Authentication completed but no token was saved",
                        error="Token not found after authentication",
                    )
            except ImportError:
                return MarketplaceAuthOutput(
                    success=False,
                    message="Could not verify authentication",
                    error="Config module not available",
                )
        else:
            return MarketplaceAuthOutput(
                success=False,
                message="Authentication was not completed",
                error="User may have cancelled or browser automation failed",
            )

    except Exception as e:
        return MarketplaceAuthOutput(
            success=False,
            message="Authentication failed",
            error=str(e),
        )


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "MarketplaceSearchOutput",
    "MarketplaceDownloadOutput",
    "MarketplaceUploadOutput",
    "MarketplaceCheckUpdateOutput",
    "MarketplaceAuthOutput",
    "marketplace_search_agents",
    "marketplace_download_agent",
    "marketplace_upload_agent",
    "marketplace_check_update",
    "marketplace_authenticate",
    # Register functions
    "register_marketplace_search_agents",
    "register_marketplace_download_agent",
    "register_marketplace_upload_agent",
    "register_marketplace_check_update",
    "register_marketplace_authenticate",
]
