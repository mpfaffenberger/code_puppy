try:
    from code_puppy.token_utils import estimate_tokens_for_message
    from code_puppy.tools.common import get_model_context_length
except ImportError:
    # Fallback if these modules aren't available in the internal version
    def get_model_context_length():
        return 128000  # Default context length

    def estimate_tokens_for_message(msg):
        # Simple fallback estimation
        return len(str(msg)) // 4  # Rough estimate: 4 chars per token


def token_guard(num_tokens: int):
    try:
        from code_puppy import state_management

        current_history = state_management.get_message_history()
        message_hist_tokens = sum(
            estimate_tokens_for_message(msg) for msg in current_history
        )

        if message_hist_tokens + num_tokens > (get_model_context_length() * 0.9):
            raise ValueError(
                "Tokens produced by this tool call would exceed model capacity"
            )
    except ImportError:
        # Fallback: simple check against a reasonable limit
        if num_tokens > 10000:
            raise ValueError(
                f"Token count {num_tokens} exceeds safety limit of 10,000 tokens"
            )
