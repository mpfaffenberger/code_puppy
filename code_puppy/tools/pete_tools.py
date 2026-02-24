"""Pete CMS integration tools for Code Puppy.

Provides tools for interacting with Walmart's Pete enterprise database
web service: dynamic SQL execution, BigQuery querying, configuration,
and Instant API service invocation.
"""

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.walmart_specific.pete_client import (
    DEFAULT_PETE_CLUSTER,
    STAGE_PETE_CLUSTER,
    PeteAPIError,
    PeteAuthError,
    PeteClient,
    PeteError,
    PeteNotFoundError,
    get_configured_cid,
    get_configured_cluster,
    get_configured_database,
    save_pete_config,
    _load_pete_config,
)


# ============================================================================
# Helper Functions
# ============================================================================


def _get_pete_client(
    cid: str | None = None,
    cluster: str | None = None,
) -> PeteClient:
    """Get a configured Pete client instance.

    Args:
        cid: Optional CID override.
        cluster: Optional cluster override.

    Returns:
        Configured PeteClient.
    """
    return PeteClient(cluster=cluster, cid=cid)


def _handle_pete_error(e: Exception) -> dict:
    """Convert Pete exceptions to structured error responses."""
    if isinstance(e, PeteAuthError):
        emit_error(f"🔐 Pete auth error: {e}")
        return {
            "error": str(e),
            "error_type": "auth",
            "hint": (
                "Check your CID or credentials. Create a CID at "
                "https://wmlink/pete → 'Create Credential ID'."
            ),
        }
    if isinstance(e, PeteNotFoundError):
        emit_warning(f"🔍 Pete not found: {e}")
        return {
            "error": str(e),
            "error_type": "not_found",
            "hint": (
                "Check the database connection name. View available "
                "connections at https://wmlink/pete → 'DB Connection List'."
            ),
        }
    if isinstance(e, PeteAPIError):
        emit_error(f"❌ Pete API error: {e}")
        return {
            "error": str(e),
            "error_type": "api_error",
            "status_code": getattr(e, "status_code", None),
        }
    if isinstance(e, PeteError):
        emit_error(f"❌ Pete error: {e}")
        return {"error": str(e), "error_type": "pete_error"}

    emit_error(f"❌ Unexpected error: {e}")
    return {"error": str(e), "error_type": "unknown"}


def _truncate_results(
    response: dict | str, max_rows: int = 200
) -> dict | str:
    """Truncate large result sets to prevent context overflow.

    Args:
        response: Pete API response.
        max_rows: Max data rows to keep per result set.

    Returns:
        Truncated response.
    """
    if not isinstance(response, dict):
        return response

    resp = response.get("response", response)
    results = resp.get("results", {})

    for key, value in results.items():
        if isinstance(value, dict) and "data" in value:
            data = value["data"]
            if isinstance(data, list) and len(data) > max_rows:
                value["data"] = data[:max_rows]
                value["_truncated"] = True
                value["_total_rows"] = len(data)
                value["_shown_rows"] = max_rows

    return response


# ============================================================================
# Tool Implementations
# ============================================================================


async def _pete_configure(
    ctx: RunContext,
    cluster: str | None = None,
    default_cid: str | None = None,
    default_database: str | None = None,
    environment: str | None = None,
) -> dict:
    """Configure Pete connection settings.

    Saves preferences to ~/.code_puppy/pete.json for use across sessions.

    Args:
        ctx: Run context.
        cluster: Pete cluster hostname (e.g. 'prod.wcnp.gbl.gcp.pete.glb.us.walmart.net').
        default_cid: Default Pete Credential ID for database auth.
        default_database: Default predefined database connection name.
        environment: Shortcut: 'prod', 'stage', or 'dev' to set cluster.

    Returns:
        Updated configuration dict.
    """
    config = _load_pete_config()

    env_clusters = {
        "prod": DEFAULT_PETE_CLUSTER,
        "stage": STAGE_PETE_CLUSTER,
        "dev": "dev.wcnp.west.az.pete.glb.us.walmart.net",
    }

    if environment and environment in env_clusters:
        config["cluster"] = env_clusters[environment]
        config["environment"] = environment
    elif cluster:
        config["cluster"] = cluster

    if default_cid is not None:
        config["default_cid"] = default_cid

    if default_database is not None:
        config["default_database"] = default_database

    save_pete_config(config)
    emit_success("✅ Pete configuration saved!")
    return {
        "status": "configured",
        "cluster": config.get("cluster", DEFAULT_PETE_CLUSTER),
        "default_cid": config.get("default_cid"),
        "default_database": config.get("default_database"),
    }


async def _pete_health_check(
    ctx: RunContext,
    cluster: str | None = None,
) -> dict:
    """Check Pete cluster health status.

    Args:
        ctx: Run context.
        cluster: Optional cluster override.

    Returns:
        Health status response.
    """
    try:
        with _get_pete_client(cluster=cluster) as client:
            result = client.health_check()
            emit_success(f"✅ Pete cluster {client.cluster} is healthy")
            return {
                "status": "healthy",
                "cluster": client.cluster,
                "response": result,
            }
    except Exception as e:
        return _handle_pete_error(e)


async def _pete_dynamic_query(
    ctx: RunContext,
    sql: str,
    database: str | None = None,
    cid: str | None = None,
    host_vars: dict[str, Any] | None = None,
    rows: int | None = 100,
    stats: bool = True,
    cluster: str | None = None,
) -> dict:
    """Execute a dynamic SQL query against Pete.

    Sends SQL directly to a database through Pete's dynamic SQL
    interface. Supports any SQL the target engine allows.

    Args:
        ctx: Run context.
        sql: SQL command to execute. Use :var_name for host variables.
        database: Predefined database connection name. Falls back to configured default.
        cid: Pete Credential ID. Falls back to configured default.
        host_vars: Dict mapping host variable names to values (for :var params in SQL).
        rows: Max rows to return (default 100). Set None for unlimited.
        stats: Include execution statistics in response.
        cluster: Optional Pete cluster override.

    Returns:
        Query results with status and data.
    """
    db = database or get_configured_database()
    if not db:
        return {
            "error": "No database specified",
            "hint": (
                "Provide a database= name or run pete_configure to set a default. "
                "View available connections at https://wmlink/pete → 'DB Connection List'."
            ),
        }

    emit_info(f"📊 Executing SQL against Pete [{db}]...")

    try:
        step: dict[str, Any] = {
            "sql": {
                "name": "query",
                "command": sql,
            }
        }
        if host_vars:
            step["sql"]["host_vars"] = host_vars
        if rows is not None:
            step["sql"]["rows"] = rows

        header_cfg: dict[str, Any] = {"stats": stats}

        with _get_pete_client(cid=cid, cluster=cluster) as client:
            result = client.dynamic_query_post(
                database=db,
                steps=[step],
                results={"data": "query"},
                header=header_cfg,
            )

        result = _truncate_results(result)
        emit_success("✅ Query executed successfully")
        return result

    except Exception as e:
        return _handle_pete_error(e)


async def _pete_multi_step_query(
    ctx: RunContext,
    steps: list[dict[str, Any]],
    results: dict[str, str],
    database: str | None = None,
    connections: list[dict[str, Any]] | None = None,
    cid: str | None = None,
    stats: bool = True,
    cluster: str | None = None,
) -> dict:
    """Execute a multi-step SQL query against Pete.

    Supports multiple SQL statements executed in sequence, with
    pass_vars for sharing data between steps.

    Args:
        ctx: Run context.
        steps: Array of step definitions. Each step is a dict like:
            {"sql": {"name": "step1", "command": "SELECT ..."}}
        results: Mapping of output tag names to step names.
        database: Optional predefined database name.
        connections: Optional local connection definitions for multi-DB queries.
        cid: Pete Credential ID.
        stats: Include execution statistics.
        cluster: Optional Pete cluster override.

    Returns:
        Combined query results.
    """
    db = database or get_configured_database()
    emit_info(f"📊 Executing {len(steps)}-step query against Pete...")

    try:
        with _get_pete_client(cid=cid, cluster=cluster) as client:
            result = client.dynamic_query_post(
                database=db,
                steps=steps,
                connections=connections,
                results=results,
                header={"stats": stats},
            )
        result = _truncate_results(result)
        emit_success("✅ Multi-step query executed successfully")
        return result

    except Exception as e:
        return _handle_pete_error(e)


async def _pete_call_service(
    ctx: RunContext,
    domain: str,
    service: str,
    path: str,
    version: str = "default",
    method: str = "GET",
    body: dict[str, Any] | None = None,
    path_params: dict[str, str] | None = None,
    cid: str | None = None,
    cluster: str | None = None,
) -> dict:
    """Call a Pete Instant API service.

    Invokes a pre-configured service endpoint created via the Pete Console.

    Args:
        ctx: Run context.
        domain: Service domain name (e.g. 'finance', 'membership').
        service: Service name.
        path: Service path.
        version: API version (default: 'default').
        method: HTTP method (GET, POST, PUT, DELETE).
        body: Request body for POST/PUT.
        path_params: Additional path parameters.
        cid: Pete Credential ID.
        cluster: Optional Pete cluster override.

    Returns:
        Service response.
    """
    emit_info(f"🔗 Calling Pete service: {domain}/{service}/{path}")

    try:
        with _get_pete_client(cid=cid, cluster=cluster) as client:
            result = client.call_service(
                domain=domain,
                service=service,
                path=path,
                version=version,
                method=method,
                body=body,
                path_params=path_params,
            )
        emit_success("✅ Service call completed")
        return result

    except Exception as e:
        return _handle_pete_error(e)


async def _pete_get_config(
    ctx: RunContext,
) -> dict:
    """Get current Pete configuration.

    Returns:
        Current Pete config with cluster, CID, database, and cluster reference.
    """
    config = _load_pete_config()
    return {
        "cluster": config.get("cluster", DEFAULT_PETE_CLUSTER),
        "environment": config.get("environment", "prod"),
        "default_cid": config.get("default_cid"),
        "default_database": config.get("default_database"),
        "available_clusters": {
            "prod_gcp_global": DEFAULT_PETE_CLUSTER,
            "stage_gcp_global": STAGE_PETE_CLUSTER,
            "prod_azure_east": "prod.wcnp.east.az.pete.glb.us.walmart.net",
            "prod_azure_central": "prod.wcnp.central.az.pete.glb.us.walmart.net",
            "prod_gcp_central": "prod.wcnp.central.gcp.pete.glb.us.walmart.net",
            "dev_azure_west": "dev.wcnp.west.az.pete.glb.us.walmart.net",
        },
        "console_url": "https://wmlink/pete",
    }


# ============================================================================
# Tool Registration Functions
# ============================================================================


def register_pete_configure(agent):
    """Register the pete_configure tool."""
    agent.tool(_pete_configure)


def register_pete_health_check(agent):
    """Register the pete_health_check tool."""
    agent.tool(_pete_health_check)


def register_pete_dynamic_query(agent):
    """Register the pete_dynamic_query tool."""
    agent.tool(_pete_dynamic_query)


def register_pete_multi_step_query(agent):
    """Register the pete_multi_step_query tool."""
    agent.tool(_pete_multi_step_query)


def register_pete_call_service(agent):
    """Register the pete_call_service tool."""
    agent.tool(_pete_call_service)


def register_pete_get_config(agent):
    """Register the pete_get_config tool."""
    agent.tool(_pete_get_config)


# ============================================================================
# Tool Registry (for __init__.py merging)
# ============================================================================

PETE_TOOLS = {
    "pete_configure": register_pete_configure,
    "pete_health_check": register_pete_health_check,
    "pete_dynamic_query": register_pete_dynamic_query,
    "pete_multi_step_query": register_pete_multi_step_query,
    "pete_call_service": register_pete_call_service,
    "pete_get_config": register_pete_get_config,
}
