import os
import fnmatch

from typing import Optional, Tuple
import tiktoken
from rapidfuzz.distance import JaroWinkler
from rich.console import Console

# get_model_context_length will be imported locally where needed to avoid circular imports

NO_COLOR = bool(int(os.environ.get("CODE_PUPPY_NO_COLOR", "0")))
console = Console(no_color=NO_COLOR)


def get_model_context_length() -> int:
    """
    Get the context length for the currently configured model from models.json
    """
    # Import locally to avoid circular imports
    from code_puppy.model_factory import ModelFactory
    from code_puppy.config import get_model_name
    import os
    from pathlib import Path

    # Load model configuration
    models_path = os.environ.get("MODELS_JSON_PATH")
    if not models_path:
        models_path = Path(__file__).parent.parent / "models.json"
    else:
        models_path = Path(models_path)

    model_configs = ModelFactory.load_config(str(models_path))
    model_name = get_model_name()

    # Get context length from model config
    model_config = model_configs.get(model_name, {})
    context_length = model_config.get("context_length", 128000)  # Default value

    # Reserve 10% of context for response
    return int(context_length)


# -------------------
# Shared ignore patterns/helpers
# -------------------
IGNORE_PATTERNS = [
    "**/node_modules/**",
    "**/node_modules/**/*.js",
    "node_modules/**",
    "node_modules",
    "**/.git/**",
    "**/.git",
    ".git/**",
    ".git",
    "**/__pycache__/**",
    "**/__pycache__",
    "__pycache__/**",
    "__pycache__",
    "**/.DS_Store",
    ".DS_Store",
    "**/.env",
    ".env",
    "**/.venv/**",
    "**/.venv",
    "**/venv/**",
    "**/venv",
    "**/.idea/**",
    "**/.idea",
    "**/.vscode/**",
    "**/.vscode",
    "**/dist/**",
    "**/dist",
    "**/build/**",
    "**/build",
    "**/*.pyc",
    "**/*.pyo",
    "**/*.pyd",
    "**/*.so",
    "**/*.dll",
    "**/.*",
]


def should_ignore_path(path: str) -> bool:
    """Return True if *path* matches any pattern in IGNORE_PATTERNS."""
    for pattern in IGNORE_PATTERNS:
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


def _find_best_window(
    haystack_lines: list[str],
    needle: str,
) -> Tuple[Optional[Tuple[int, int]], float]:
    """
    Return (start, end) indices of the window with the highest
    Jaro-Winkler similarity to `needle`, along with that score.
    If nothing clears JW_THRESHOLD, return (None, score).
    """
    needle = needle.rstrip("\n")
    needle_lines = needle.splitlines()
    win_size = len(needle_lines)
    best_score = 0.0
    best_span: Optional[Tuple[int, int]] = None
    best_window = ""
    # Pre-join the needle once; join windows on the fly
    for i in range(len(haystack_lines) - win_size + 1):
        window = "\n".join(haystack_lines[i : i + win_size])
        score = JaroWinkler.normalized_similarity(window, needle)
        if score > best_score:
            best_score = score
            best_span = (i, i + win_size)
            best_window = window

    console.log(f"Best span: {best_span}")
    console.log(f"Best window: {best_window}")
    console.log(f"Best score: {best_score}")
    return best_span, best_score
