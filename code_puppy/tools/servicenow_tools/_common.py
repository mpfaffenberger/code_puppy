"""Common utilities for ServiceNow tools.

Shared helpers, constants, and error handling for all ServiceNow tool modules.
"""

import re

from markdownify import markdownify as md

from code_puppy.messaging import emit_error, emit_warning
from code_puppy.plugins.walmart_specific.servicenow_client import (
    ServiceNowAPIError,
    ServiceNowAuthError,
    ServiceNowClient,
    ServiceNowError,
    ServiceNowNotFoundError,
)


# ============================================================================
# Constants
# ============================================================================

SERVICENOW_BASE_URL = "https://walmartglobal.service-now.com"
MAX_CHARACTER_LIMIT = 30000


# ============================================================================
# Helper Functions
# ============================================================================


def get_servicenow_client() -> ServiceNowClient:
    """Get a ServiceNow client instance.

    Returns:
        ServiceNowClient: A configured ServiceNow client
    """
    return ServiceNowClient()


def convert_html_to_markdown(html_content: str) -> str:
    """Convert HTML content to markdown.

    Args:
        html_content: HTML content from ServiceNow article

    Returns:
        Markdown-formatted string
    """
    if not html_content:
        return ""

    # Use markdownify to convert HTML to markdown
    markdown = md(html_content, heading_style="ATX", strip=["script", "style"])
    return markdown.strip()


def clean_text(text: str | None) -> str:
    """Clean text content by removing excess whitespace.

    Args:
        text: Raw text content

    Returns:
        Cleaned text string
    """
    if not text:
        return ""
    # Remove excess whitespace and normalize line breaks
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def handle_servicenow_error(e: Exception) -> dict:
    """Convert ServiceNow exceptions to structured error responses.

    Args:
        e: Exception raised by ServiceNow client

    Returns:
        Dict with success=False and error details
    """
    error_str = str(e)

    # Check for validation/mandatory field errors and provide helpful guidance
    retry_hint = None
    if "mandatory" in error_str.lower() or "required" in error_str.lower():
        retry_hint = (
            "This error indicates missing required fields. Try different variable names "
            "(e.g., 'group_name' vs 'groupname' vs 'ad_group_name'). "
            "You can also try submitting with all the variables the user provided."
        )
    elif "invalid" in error_str.lower() or "validation" in error_str.lower():
        retry_hint = (
            "This error indicates invalid field values. Check the variable names and values. "
            "Try using sys_id values instead of display names for reference fields."
        )

    if isinstance(e, ServiceNowAuthError):
        error_msg = f"Authentication failed: {error_str}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "authentication",
            "retry_hint": "Use servicenow_authenticate() to re-authenticate, then retry.",
        }
    elif isinstance(e, ServiceNowNotFoundError):
        error_msg = f"Resource not found: {error_str}"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "not_found",
        }
    elif isinstance(e, ServiceNowAPIError):
        error_msg = f"API error: {error_str}"
        emit_error(error_msg)
        result = {
            "success": False,
            "error": error_msg,
            "error_type": "api_error",
            "raw_error": error_str,  # Include full error for debugging
        }
        if retry_hint:
            result["retry_hint"] = retry_hint
        return result
    elif isinstance(e, ServiceNowError):
        error_msg = f"ServiceNow error: {error_str}"
        emit_error(error_msg)
        result = {
            "success": False,
            "error": error_msg,
            "error_type": "servicenow",
            "raw_error": error_str,
        }
        if retry_hint:
            result["retry_hint"] = retry_hint
        return result
    else:
        error_msg = f"Unexpected error: {error_str}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "unknown",
            "raw_error": error_str,
        }


def analyze_automation_feasibility(item_data: dict) -> dict:
    """Analyze a catalog item to determine if it can be automated via API.

    Checks for patterns that indicate the form requires browser-based interaction:
    - External API calls in client scripts (Tableau, Azure, etc.)
    - Dynamically populated dropdowns (empty choices)
    - Hidden validation fields checked by onSubmit
    - GlideAjax or REST calls in scripts

    Args:
        item_data: The raw catalog item data from ServiceNow API

    Returns:
        Dict containing:
            - automatable (bool): Whether the form can likely be automated
            - confidence (str): "high", "medium", "low"
            - blockers (list): List of reasons why automation may fail
            - warnings (list): Potential issues that may cause problems
    """
    blockers = []
    warnings = []

    # Patterns that indicate external API calls
    external_api_patterns = [
        (r"tableau", "Tableau API integration detected"),
        (r"azure", "Azure API integration detected"),
        (r"Bearer\\s+", "Bearer token authentication detected (external API)"),
        (r"XMLHttpRequest|fetch\\s*\\(", "Direct HTTP requests to external services"),
        (r"api_version\\s*=", "External API versioning detected"),
        (r"\\.service-now\\.com.*api(?!/now)", "Custom ServiceNow API endpoint"),
    ]

    # Patterns that indicate browser-required validation
    validation_patterns = [
        (
            r"g_form\\.getValue\\(['\\\"]submit_form['\\\"]\\)",
            "Hidden submit validation field",
        ),
        (r"g_form\\.addErrorMessage", "Client-side error validation"),
        (r"return\\s+false", "Form submission blocking logic"),
    ]

    # Patterns that indicate dynamic data loading
    dynamic_patterns = [
        (r"GlideAjax", "Server-side script calls (GlideAjax)"),
        (r"addParam.*sysparm_", "Dynamic parameter loading"),
    ]

    # Analyze client scripts
    client_scripts = item_data.get("client_script", {})
    all_scripts = []

    for script_type in ["onChange", "onSubmit", "onLoad"]:
        for script in client_scripts.get(script_type, []):
            script_content = script.get("script", "")
            all_scripts.append((script_type, script_content))

    # Check for external API patterns
    for script_type, script_content in all_scripts:
        script_lower = script_content.lower()

        for pattern, message in external_api_patterns:
            if re.search(pattern, script_lower, re.IGNORECASE):
                blockers.append(f"{message} in {script_type} script")

        for pattern, message in validation_patterns:
            if re.search(pattern, script_content):  # Case-sensitive for JS
                if script_type == "onSubmit":
                    blockers.append(f"{message} in {script_type} script")
                else:
                    warnings.append(f"{message} in {script_type} script")

        for pattern, message in dynamic_patterns:
            if re.search(pattern, script_content):
                warnings.append(f"{message} in {script_type} script")

    # Check for empty dynamic dropdowns
    variables = item_data.get("variables", [])
    for var in variables:
        var_type = var.get("friendly_type", var.get("display_type", ""))
        var_name = var.get("name", "unknown")
        choices = var.get("choices", [])

        # Select box with only "None" option = dynamically populated
        if var_type == "select_box" and choices:
            non_empty_choices = [c for c in choices if c.get("value", "")]
            if not non_empty_choices:
                blockers.append(
                    f"Field '{var_name}' has no choices (dynamically populated by JavaScript)"
                )

    # Determine overall feasibility
    if blockers:
        automatable = False
        confidence = "high"
    elif warnings:
        automatable = True  # Might still work
        confidence = "medium"
    else:
        automatable = True
        confidence = "high"

    # Deduplicate
    blockers = list(dict.fromkeys(blockers))
    warnings = list(dict.fromkeys(warnings))

    return {
        "automatable": automatable,
        "confidence": confidence,
        "blockers": blockers,
        "warnings": warnings,
    }
