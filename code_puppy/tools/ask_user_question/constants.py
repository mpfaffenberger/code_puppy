"""Constants for the ask_user_question tool."""

from typing import Final

# Question constraints
MAX_QUESTIONS_PER_CALL: Final[int] = 10  # Reasonable limit for a single TUI interaction
MIN_OPTIONS_PER_QUESTION: Final[int] = 2
MAX_OPTIONS_PER_QUESTION: Final[int] = 6
MAX_HEADER_LENGTH: Final[int] = 12
MAX_LABEL_LENGTH: Final[int] = 50
MAX_DESCRIPTION_LENGTH: Final[int] = 200
MAX_QUESTION_LENGTH: Final[int] = 500
MAX_OTHER_TEXT_LENGTH: Final[int] = 500

# UI settings
DEFAULT_TIMEOUT_SECONDS: Final[int] = 300  # 5 minutes
TIMEOUT_WARNING_SECONDS: Final[int] = 60  # Show warning at 60s remaining
AUTO_ADD_OTHER_OPTION: Final[bool] = True

# Other option configuration
OTHER_OPTION_LABEL: Final[str] = "Other"
OTHER_OPTION_DESCRIPTION: Final[str] = "Enter a custom option"

# Left panel width magic numbers (extracted for clarity)
LEFT_PANEL_PADDING: Final[int] = (
    14  # left(2) + cursor(2) + checkmark(2) + right(2) + buffer(6)
)
MIN_LEFT_PANEL_WIDTH: Final[int] = 21
MAX_LEFT_PANEL_WIDTH: Final[int] = 36

# Horizontal padding for panel content (matches left panel's "  " prefix)
PANEL_CONTENT_PADDING: Final[str] = "  "

# CI environment variables to check for non-interactive detection
# Use tuple for true immutability (Final only prevents reassignment, not mutation)
CI_ENV_VARS: Final[tuple[str, ...]] = (
    "CI",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "JENKINS_URL",
    "TRAVIS",
    "CIRCLECI",
    "BUILDKITE",
    "AZURE_PIPELINES",
    "TEAMCITY_VERSION",
)

# Terminal escape sequences for alternate screen buffer
ENTER_ALT_SCREEN: Final[str] = "\033[?1049h"
EXIT_ALT_SCREEN: Final[str] = "\033[?1049l"
CLEAR_AND_HOME: Final[str] = "\033[2J\033[H"

# Unicode symbols for TUI rendering
CURSOR_POINTER: Final[str] = "\u276f"  # ❯
CURSOR_TRIANGLE: Final[str] = "\u25b6"  # ▶
CHECK_MARK: Final[str] = "\u2713"  # ✓
RADIO_FILLED: Final[str] = "\u25cf"  # ●
BORDER_DOUBLE: Final[str] = "\u2550"  # ═
ARROW_LEFT: Final[str] = "\u2190"  # ←
ARROW_RIGHT: Final[str] = "\u2192"  # →
ARROW_UP: Final[str] = "\u2191"  # ↑
ARROW_DOWN: Final[str] = "\u2193"  # ↓
PIPE_SEPARATOR: Final[str] = "\u2502"  # │

# Panel rendering
MAX_READABLE_WIDTH: Final[int] = 120
HELP_BORDER_WIDTH: Final[int] = 50

# Error formatting
MAX_VALIDATION_ERRORS_SHOWN: Final[int] = 3

# Terminal synchronization delay (seconds)
TERMINAL_SYNC_DELAY: Final[float] = 0.05
