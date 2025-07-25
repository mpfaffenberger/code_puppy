from code_puppy.config import get_theme
from code_puppy.themes import get_themed_prompt

def get_system_prompt():
    """Returns the main system prompt, using the configured theme."""
    current_theme = get_theme()
    return get_themed_prompt(current_theme)
