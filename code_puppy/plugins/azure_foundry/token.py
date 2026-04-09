"""Azure AD token provider for Azure AI Foundry authentication.

This module provides token management for authenticating with Azure AI Foundry
using credentials from the Azure CLI (`az login`).

The token provider uses `AzureCliCredential` from the `azure-identity` library
to obtain tokens without requiring API keys.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional, Tuple

from .config import AZURE_COGNITIVE_SCOPE, TOKEN_REFRESH_BUFFER

logger = logging.getLogger(__name__)

# Singleton instance of the token provider
_token_provider_instance: Optional["AzureFoundryTokenProvider"] = None


class AzureFoundryTokenProvider:
    """Provides Azure AD tokens for Anthropic Foundry using az login credentials.

    This class wraps the Azure CLI credential to provide tokens for
    authenticating with Azure AI Foundry. It handles token caching and
    provides status checking functionality.

    Example:
        >>> provider = AzureFoundryTokenProvider()
        >>> token = provider.get_token()
        >>> # Use token for API calls
    """

    def __init__(self, scope: str = AZURE_COGNITIVE_SCOPE):
        """Initialize the token provider.

        Args:
            scope: The Azure AD scope for token acquisition.
                   Defaults to the Cognitive Services scope.
        """
        self._scope = scope
        self._credential = None
        self._token_provider_func: Optional[Callable[[], str]] = None
        self._initialized = False
        self._init_error: Optional[str] = None

    def _ensure_initialized(self) -> bool:
        """Lazily initialize the Azure credential.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        if self._initialized:
            return self._init_error is None

        try:
            from azure.identity import AzureCliCredential, get_bearer_token_provider

            self._credential = AzureCliCredential()
            self._token_provider_func = get_bearer_token_provider(
                self._credential, self._scope
            )
            self._initialized = True
            self._init_error = None
            logger.debug("Azure CLI credential initialized successfully")
            return True

        except ImportError as e:
            self._initialized = True
            self._init_error = f"azure-identity package not installed: {e}"
            logger.error(self._init_error)
            return False

        except Exception as e:
            self._initialized = True
            self._init_error = f"Failed to initialize Azure credential: {e}"
            logger.error(self._init_error)
            return False

    def get_token(self) -> str:
        """Get a valid access token for Azure AI Foundry.

        The token is obtained from the Azure CLI credential and is
        automatically refreshed when needed by the underlying provider.

        Returns:
            A valid access token string.

        Raises:
            RuntimeError: If the token provider is not initialized or
                         if token acquisition fails.
        """
        if not self._ensure_initialized():
            raise RuntimeError(self._init_error or "Token provider not initialized")

        if self._token_provider_func is None:
            raise RuntimeError("Token provider function not available")

        try:
            return self._token_provider_func()
        except Exception as e:
            logger.error(f"Failed to acquire token: {e}")
            raise RuntimeError(f"Failed to acquire Azure AD token: {e}") from e

    def check_auth_status(self) -> Tuple[bool, str, Optional[str]]:
        """Check if Azure CLI authentication is valid.

        Returns:
            A tuple of (is_authenticated, status_message, user_info):
            - is_authenticated: True if auth is valid, False otherwise
            - status_message: Human-readable status description
            - user_info: Email/UPN of logged-in user if available
        """
        if not self._ensure_initialized():
            return False, self._init_error or "Not initialized", None

        try:
            # Try to get a token to verify authentication
            token = self._credential.get_token(self._scope)
            expires_in = int(token.expires_on - time.time())

            # Try to get user info from the token
            user_info = None
            try:
                # The token is a JWT, we can decode the payload to get user info
                import base64
                import json

                # Split the JWT and decode the payload (second part)
                parts = token.token.split(".")
                if len(parts) >= 2:
                    # Add padding if needed
                    payload = parts[1]
                    padding = 4 - len(payload) % 4
                    if padding != 4:
                        payload += "=" * padding
                    decoded = base64.urlsafe_b64decode(payload)
                    claims = json.loads(decoded)
                    user_info = claims.get("upn") or claims.get("email") or claims.get("preferred_username")
            except Exception:
                # Ignore errors in user info extraction
                pass

            if expires_in > TOKEN_REFRESH_BUFFER:
                return True, f"Valid (expires in {expires_in // 60} minutes)", user_info
            else:
                return True, f"Valid but expiring soon ({expires_in} seconds)", user_info

        except Exception as e:
            error_name = type(e).__name__
            if "CredentialUnavailableError" in error_name:
                return False, "Not authenticated - run 'az login'", None
            return False, f"Authentication error: {e}", None


def get_token_provider() -> AzureFoundryTokenProvider:
    """Get the singleton token provider instance.

    Returns:
        The global AzureFoundryTokenProvider instance.
    """
    global _token_provider_instance
    if _token_provider_instance is None:
        _token_provider_instance = AzureFoundryTokenProvider()
    return _token_provider_instance


def reset_token_provider() -> None:
    """Reset the singleton token provider (useful for testing)."""
    global _token_provider_instance
    _token_provider_instance = None
