"""DBOS sampling logic for Walmart users.

This module determines if a user should have DBOS enabled by default based on
a deterministic sampling of the user population using their puppy token username.
"""

import hashlib

from code_puppy.config import get_puppy_token
from code_puppy.plugins.walmart_specific.auth import decode_jwt_without_validation


def is_user_in_dbos_sample() -> bool:
    """
    Check if the current user (based on puppy token username) is in the 2% DBOS sample.
    Uses SHA1 hash of username to deterministically sample 2% of users.

    Returns:
        bool: True if user should have DBOS enabled by default, False otherwise
    """
    try:
        token = get_puppy_token()
        if not token:
            return False

        # Decode the JWT to get username
        decoded = decode_jwt_without_validation(token)
        if not decoded:
            return False

        # Extract username from common JWT claims (same order as confluence_client.py)
        username = (
            decoded.get("sub")
            or decoded.get("user_id")
            or decoded.get("userId")
            or decoded.get("uid")
        )

        if not username:
            return False

        # Hash username with SHA1
        username_hash = hashlib.sha1(str(username).encode("utf-8")).hexdigest()

        # Convert first 8 hex chars to int and mod 100 to get 0-99 range
        # Users with hash % 100 < 2 are in the 2% sample
        hash_value = int(username_hash[:8], 16)
        is_sampled = (hash_value % 100) < 2

        return is_sampled

    except Exception:
        # If anything fails, don't enable DBOS by default
        return False
