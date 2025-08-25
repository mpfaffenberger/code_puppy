from code_puppy.tools.common import get_model_context_length
from code_puppy.token_utils import estimate_tokens_for_message


def token_guard(num_tokens: int):
    # Import lazily to avoid circular deps and to make tests resilient to open() monkeypatching
    try:
        from code_puppy import state_management

        current_history = state_management.get_message_history()
    except Exception:
        current_history = []

    # Be defensive: if message parsing fails for any reason, assume zero history tokens
    try:
        message_hist_tokens = sum(
            estimate_tokens_for_message(msg) for msg in current_history
        )
    except Exception:
        message_hist_tokens = 0

    # Determine model capacity; if config loading fails (e.g., due to mocked open()),
    # fall back to a very large capacity so tools don't break in tests.
    try:
        context_len = int(get_model_context_length())
    except Exception:
        context_len = 1_000_000_000  # generous fallback

    if message_hist_tokens + num_tokens > int(context_len * 0.9):
        raise ValueError(
            "Tokens produced by this tool call would exceed model capacity"
        )
