from code_puppy.tools.common import get_model_context_length
from code_puppy.token_utils import estimate_tokens_for_message


def token_guard(num_tokens: int):
    from code_puppy import state_management

    current_history = state_management.get_message_history()
    message_hist_tokens = sum(
        estimate_tokens_for_message(msg) for msg in current_history
    )

    if message_hist_tokens + num_tokens > (get_model_context_length() * 0.9):
        raise ValueError(
            "Tokens produced by this tool call would exceed model capacity"
        )
