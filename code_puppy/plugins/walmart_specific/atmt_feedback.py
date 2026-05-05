"""ATMT Feedback submission for Code Puppy CLI.

Provides a privacy-conscious async function for submitting feedback
directly to the ATMT API. NOT registered as an LLM tool — feedback
is collected via the `/feedback` slash command (see feedback_menu.py)
so that no model ever sees user feedback content.
"""

import json
import uuid
from typing import Any, Literal

from code_puppy.config import get_puppy_token, CONFIG_DIR
from code_puppy.http_utils import create_async_client


# =============================================================================
# ATMT Configuration (mirrors puppy_frontend/config.py)
# =============================================================================

ATMT_CONFIG = {
    "dev": {
        "product_id": "56141a02-570f-4c93-bc87-cdd8df22e306",
        "base_url": "https://api.atmt-feedback.dev.walmart.com",
    },
    "stage": {
        "product_id": "fc839fef-2631-425c-8715-94f89db23bfd",
        "base_url": "https://api.atmt-feedback.qa.walmart.com",
    },
    "prod": {
        "product_id": "11fd3091-61b9-4346-a81a-ade6560f52a3",
        "base_url": "https://api.atmt-feedback.prod.walmart.com",
    },
}

# API endpoints for different feedback types
ENDPOINTS = {
    "bug": "/feedback/api/v2/bugs",
    "feature": "/feedback/api/v2/featurerequests",
    "rating": "/feedback/api/v2/ratings",
}

# Valid feedback types
FeedbackType = Literal["bug", "feature", "rating"]


def _get_atmt_config() -> dict:
    """Get ATMT config based on environment.
    
    Uses CODEPUPPY_LOCAL_AGENT_MARKETPLACE env var:
    - "1" -> dev
    - "2" -> stage
    - anything else -> prod
    """
    import os
    
    env = os.environ.get("CODEPUPPY_LOCAL_AGENT_MARKETPLACE")
    env_name = {
        "1": "dev",
        "2": "stage",
    }.get(env, "prod")
    
    return ATMT_CONFIG[env_name]


def _get_auth_token() -> str | None:
    """Get the puppy token for ATMT API auth.
    
    This token is obtained during Code Puppy startup authentication.
    No separate auth flow needed - uses the existing puppy_token.
    """
    return get_puppy_token()


def _get_user_id() -> str:
    """Get the current user ID from puppy token or config."""
    from pathlib import Path
    
    # Try marketplace token file first (has user info)
    token_file = Path(CONFIG_DIR) / "marketplace_token.json"
    if token_file.exists():
        try:
            with open(token_file) as f:
                data = json.load(f)
                user = data.get("user", {})
                user_id = (
                    user.get("preferredUsername") or 
                    user.get("preferred_username") or
                    user.get("email") or
                    user.get("mail") or
                    user.get("sub")
                )
                if user_id:
                    return user_id
        except Exception:
            pass
    
    # Try to decode user from puppy token JWT
    token = get_puppy_token()
    if token:
        try:
            import base64
            # JWT is header.payload.signature - we want the payload
            parts = token.split('.')
            if len(parts) >= 2:
                # Add padding if needed
                payload = parts[1]
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += '=' * padding
                decoded = json.loads(base64.urlsafe_b64decode(payload))
                return (
                    decoded.get("preferred_username") or
                    decoded.get("email") or
                    decoded.get("sub") or
                    "anonymous"
                )
        except Exception:
            pass
    
    return "anonymous"


def _get_code_puppy_version() -> str:
    """Get the Code Puppy version."""
    try:
        from code_puppy import __version__
        return __version__
    except ImportError:
        return "unknown"


# =============================================================================
# ATMT Submit Feedback
# =============================================================================


async def atmt_submit_feedback(
    feedback_type: FeedbackType,
    comment: str,
    subject: str = "",
    rating: int = 0,
) -> dict[str, Any]:
    """Submit feedback to ATMT (Application Telemetry and Management Tool).

    This is a plain async function — NOT a PydanticAI tool. It is invoked
    only from the `/feedback` slash command UI, never by an LLM. This
    keeps user feedback content (which may include sensitive details)
    out of any model context.

    Args:
        feedback_type: Type of feedback - "bug", "feature", or "rating"
        comment: The feedback comment/description from the user
        subject: Optional subject/title for the feedback
        rating: Star rating 1-5 (required for "rating" type)

    Returns:
        Dict with success status and message or error details. This
        function is intentionally silent (no UI emits) — callers are
        responsible for surfacing the result to the user.
    """
    # Get auth token
    token = _get_auth_token()
    if not token:
        return {
            "success": False,
            "error": "Not authenticated. Restart Code Puppy and complete the authentication flow.",
            "action_required": "Restart Code Puppy",
        }

    # Get config
    config = _get_atmt_config()
    product_id = config["product_id"]
    base_url = config["base_url"]
    
    # Get user info
    user_id = _get_user_id()
    version = _get_code_puppy_version()
    
    # Build subject line
    if feedback_type == "bug":
        default_subject = "Report a Problem"
    elif feedback_type == "feature":
        default_subject = "Feature Request"
    else:  # rating
        default_subject = "General Feedback"
    
    final_subject = subject if subject else default_subject
    
    # Build the ATMT payload (matches API spec from Confluence)
    import platform as plat
    os_name = plat.system().lower()  # 'darwin', 'windows', 'linux'
    
    payload = {
        "productId": product_id,
        "countryCd": "US",
        "userId": user_id,
        "subject": final_subject,
        "body": comment,
        "version": version,
        "data": json.dumps({"source": "code-puppy-cli", "platform": os_name}),
    }
    
    # Add score field for rating type
    if feedback_type == "rating" and rating > 0:
        payload["score"] = max(1, min(5, rating))  # Clamp 1-5
    
    # Get endpoint for this feedback type
    endpoint = f"{base_url}{ENDPOINTS[feedback_type]}"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "wm_consumer.id": product_id,
        "wm_qos.correlation_id": str(uuid.uuid4()),
    }

    try:
        async with create_async_client(timeout=30) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers=headers,
            )

            if response.status_code in (200, 201):
                return {
                    "success": True,
                    "message": f"Your {feedback_type} feedback has been submitted to ATMT.",
                    "feedback_type": feedback_type,
                }
            elif response.status_code == 401:
                return {
                    "success": False,
                    "error": "Authentication expired. Restart Code Puppy to re-authenticate.",
                    "status_code": 401,
                    "action_required": "Restart Code Puppy",
                }
            else:
                error_msg = (response.text[:500] if response.text else "Unknown error")
                return {
                    "success": False,
                    "error": f"ATMT API error ({response.status_code}): {error_msg}",
                    "status_code": response.status_code,
                }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to submit feedback: {e}",
        }



