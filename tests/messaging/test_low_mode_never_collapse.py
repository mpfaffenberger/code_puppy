from unittest.mock import patch

import code_puppy.messaging.renderers as r
from code_puppy.messaging.message_queue import MessageType, UIMessage


def _info(content, **meta):
    return UIMessage(type=MessageType.INFO, content=content, metadata=meta)


def test_task_list_is_never_collapsed_in_low_mode():
    msg = _info("📋 Task list\n[ ] 1. a\n[→] 2. b", message_group="task_list")
    with patch.object(r, "_get_output_level", return_value="low"):
        # None == render fully (not collapsed to a one-line peek).
        assert r._build_legacy_peek(msg) is None


def test_plain_info_still_collapses_in_low_mode():
    msg = _info("some routine info line")
    with patch.object(r, "_get_output_level", return_value="low"):
        peek = r._build_legacy_peek(msg)
        assert peek is not None
        assert "info" in peek.plain


def test_non_low_mode_renders_everything_fully():
    msg = _info("📋 Task list", message_group="task_list")
    with patch.object(r, "_get_output_level", return_value="medium"):
        assert r._build_legacy_peek(msg) is None
