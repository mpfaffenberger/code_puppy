import logging

from code_puppy.callbacks import register_callback
from code_puppy.plugins.prewarm_sdks.prewarm import start_prewarm_for_active_model

logger = logging.getLogger(__name__)


def _on_prompt_ready() -> None:
    try:
        start_prewarm_for_active_model()
    except MemoryError:
        raise
    except Exception:
        logger.debug("SDK prewarm skipped after prompt", exc_info=True)


register_callback("prompt_ready", _on_prompt_ready)
