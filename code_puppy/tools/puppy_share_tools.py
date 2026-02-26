"""Puppy Share tools for publishing HTML pages to Code Puppy's sharing platform.

These tools let agents push reports, dashboards, and HTML pages to
puppy.walmart.com/sharing so associates can view them in a browser.

By default, pages are published to the production server (puppy.walmart.com).
Pass `local=True` to target a local dev server on localhost:8080 instead.
"""

import json
import os
import urllib.request
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Output Models
# =============================================================================


class PuppyShareUploadOutput(BaseModel):
    """Result of uploading a page to Puppy Share."""

    success: bool = Field(description="Whether the upload succeeded")
    url: Optional[str] = Field(
        default=None, description="Public URL of the published page"
    )
    name: Optional[str] = Field(default=None, description="Page slug")
    business: Optional[str] = Field(default=None, description="Business unit slug")
    version: Optional[int] = Field(default=None, description="Page version number")
    action: Optional[str] = Field(
        default=None, description="'created' or 'updated'"
    )
    message: Optional[str] = Field(
        default=None, description="Human-readable result message"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if upload failed"
    )


class PuppyShareDeleteOutput(BaseModel):
    """Result of deleting a page from Puppy Share."""

    success: bool
    message: Optional[str] = None
    error: Optional[str] = None


class PuppyShareListOutput(BaseModel):
    """Result of listing the current user's shared pages."""

    success: bool
    pages: List[dict] = Field(default_factory=list)
    error: Optional[str] = None


# =============================================================================
# Helpers
# =============================================================================


def _get_puppy_token() -> Optional[str]:
    """Read the puppy token straight from ~/.code_puppy/puppy.cfg."""
    import configparser

    cfg = configparser.ConfigParser()
    cfg.read(Path.home() / ".code_puppy" / "puppy.cfg")
    return cfg.get("puppy", "puppy_token", fallback=None)


def _make_request(
    url: str,
    *,
    method: str = "GET",
    data: Optional[dict] = None,
    token: Optional[str] = None,
    timeout: int = 30,
) -> dict:
    """Thin urllib wrapper — no external deps required."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode() if data else None

    # Bypass corporate proxy for localhost / remote puppy endpoints
    os.environ.setdefault("no_proxy", "localhost,127.0.0.1")

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("detail", str(exc))
        except Exception:
            detail = str(exc)
        return {"success": False, "error": f"HTTP {exc.code}: {detail}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _is_local(local: bool) -> bool:
    """Normalise the local flag."""
    return bool(local)


# =============================================================================
# Core Functions
# =============================================================================


def puppy_share_upload(
    html_content: str,
    name: str,
    business: str = "general",
    description: str = "",
    access_level: str = "business",
    local: bool = False,
) -> PuppyShareUploadOutput:
    """Push an HTML page to Puppy Share."""
    from code_puppy.plugins.walmart_specific.urls import get_sharing_upload_url

    token = _get_puppy_token()
    if not token:
        return PuppyShareUploadOutput(
            success=False,
            error=(
                "No puppy token found. Run `puppy login` or ensure "
                "~/.code_puppy/puppy.cfg has a valid puppy_token."
            ),
        )

    url = get_sharing_upload_url(local=_is_local(local))
    payload = {
        "name": name,
        "business": business,
        "html_content": html_content,
        "description": description,
        "access_level": access_level,
    }

    result = _make_request(url, method="POST", data=payload, token=token)

    if result.get("success"):
        data = result.get("data", {})
        # Build the full view URL so the user can click it
        from code_puppy.plugins.walmart_specific.urls import (
            get_sharing_page_view_url,
        )

        view_url = get_sharing_page_view_url(
            data.get("business", business),
            data.get("name", name),
            local=_is_local(local),
        )
        return PuppyShareUploadOutput(
            success=True,
            url=view_url,
            name=data.get("name", name),
            business=data.get("business", business),
            version=data.get("version"),
            action=data.get("action"),
            message=result.get("message"),
        )

    return PuppyShareUploadOutput(
        success=False,
        error=result.get("error", "Unknown upload error"),
    )


def puppy_share_upload_file(
    file_path: str,
    name: str,
    business: str = "general",
    description: str = "",
    access_level: str = "business",
    local: bool = False,
) -> PuppyShareUploadOutput:
    """Read an HTML file from disk and push it to Puppy Share."""
    path = Path(file_path).expanduser().resolve()
    if not path.is_file():
        return PuppyShareUploadOutput(
            success=False, error=f"File not found: {path}"
        )
    try:
        html_content = path.read_text(encoding="utf-8")
    except Exception as exc:
        return PuppyShareUploadOutput(
            success=False, error=f"Failed to read file: {exc}"
        )

    return puppy_share_upload(
        html_content=html_content,
        name=name,
        business=business,
        description=description,
        access_level=access_level,
        local=local,
    )


def puppy_share_delete(
    name: str,
    business: str = "general",
    local: bool = False,
) -> PuppyShareDeleteOutput:
    """Delete a page from Puppy Share (owner only)."""
    from code_puppy.plugins.walmart_specific.urls import get_sharing_delete_url

    token = _get_puppy_token()
    if not token:
        return PuppyShareDeleteOutput(
            success=False,
            error="No puppy token found.",
        )

    url = get_sharing_delete_url(business, name, local=_is_local(local))
    result = _make_request(url, method="DELETE", token=token)

    if result.get("success"):
        return PuppyShareDeleteOutput(
            success=True, message=result.get("message")
        )
    return PuppyShareDeleteOutput(
        success=False, error=result.get("error", "Unknown delete error")
    )


def puppy_share_list_my_pages(
    local: bool = False,
) -> PuppyShareListOutput:
    """List the current user's shared pages."""
    from code_puppy.plugins.walmart_specific.urls import get_sharing_my_pages_url

    token = _get_puppy_token()
    if not token:
        return PuppyShareListOutput(
            success=False, error="No puppy token found."
        )

    url = get_sharing_my_pages_url(local=_is_local(local))
    result = _make_request(url, token=token)

    # The endpoint might return a list directly or wrapped in {"pages": [...]}
    if isinstance(result, list):
        return PuppyShareListOutput(success=True, pages=result)
    if result.get("error"):
        return PuppyShareListOutput(
            success=False, error=result["error"]
        )
    return PuppyShareListOutput(
        success=True,
        pages=result.get("pages", result.get("data", [])),
    )


# =============================================================================
# Tool Registration Functions
# =============================================================================


def register_puppy_share_upload(agent):
    """Register the puppy_share_upload tool with an agent."""
    from pydantic_ai import RunContext

    @agent.tool
    def puppy_share_upload_tool(
        context: RunContext,
        html_content: str,
        name: str,
        business: str = "general",
        description: str = "",
        access_level: str = "business",
        local: bool = False,
    ) -> PuppyShareUploadOutput:
        """Publish an HTML page to Puppy Share (puppy.walmart.com/sharing).

        Pushes HTML content directly. Re-uploading the same name+business
        combo auto-bumps the version.

        Args:
            context: Run context (injected automatically).
            html_content: Full HTML document as a string.
            name: URL-safe slug for the page (kebab-case, 1-100 chars).
            business: Business unit slug (default "general"). Use an SVP slug
                      or a custom slug like "my-team".
            description: Short description (max 500 chars).
            access_level: "public", "business" (default), or "private".
            local: If True, push to localhost:8080 instead of puppy.walmart.com.

        Returns:
            PuppyShareUploadOutput with the published page URL.
        """
        return puppy_share_upload(
            html_content=html_content,
            name=name,
            business=business,
            description=description,
            access_level=access_level,
            local=local,
        )


def register_puppy_share_upload_file(agent):
    """Register the puppy_share_upload_file tool with an agent."""
    from pydantic_ai import RunContext

    @agent.tool
    def puppy_share_upload_file_tool(
        context: RunContext,
        file_path: str,
        name: str,
        business: str = "general",
        description: str = "",
        access_level: str = "business",
        local: bool = False,
    ) -> PuppyShareUploadOutput:
        """Upload an HTML file from disk to Puppy Share.

        Reads the file at file_path and publishes it. Handy when you've
        already written the report to a file.

        Args:
            context: Run context (injected automatically).
            file_path: Path to the HTML file on disk.
            name: URL-safe slug for the page (kebab-case, 1-100 chars).
            business: Business unit slug (default "general").
            description: Short description (max 500 chars).
            access_level: "public", "business" (default), or "private".
            local: If True, push to localhost:8080 instead of puppy.walmart.com.

        Returns:
            PuppyShareUploadOutput with the published page URL.
        """
        return puppy_share_upload_file(
            file_path=file_path,
            name=name,
            business=business,
            description=description,
            access_level=access_level,
            local=local,
        )


def register_puppy_share_delete(agent):
    """Register the puppy_share_delete tool with an agent."""
    from pydantic_ai import RunContext

    @agent.tool
    def puppy_share_delete_tool(
        context: RunContext,
        name: str,
        business: str = "general",
        local: bool = False,
    ) -> PuppyShareDeleteOutput:
        """Delete a page from Puppy Share (owner only).

        Args:
            context: Run context (injected automatically).
            name: Slug of the page to delete.
            business: Business unit the page belongs to.
            local: If True, target localhost:8080.

        Returns:
            PuppyShareDeleteOutput with success/error.
        """
        return puppy_share_delete(
            name=name, business=business, local=local
        )


def register_puppy_share_list_my_pages(agent):
    """Register the puppy_share_list_my_pages tool with an agent."""
    from pydantic_ai import RunContext

    @agent.tool
    def puppy_share_list_my_pages_tool(
        context: RunContext,
        local: bool = False,
    ) -> PuppyShareListOutput:
        """List all pages the current user has published on Puppy Share.

        Args:
            context: Run context (injected automatically).
            local: If True, query localhost:8080.

        Returns:
            PuppyShareListOutput with the list of pages.
        """
        return puppy_share_list_my_pages(local=local)
