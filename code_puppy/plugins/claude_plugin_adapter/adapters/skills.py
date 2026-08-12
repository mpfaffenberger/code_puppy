import logging
from code_puppy.plugins.agent_skills.config import add_skill_directory, remove_skill_directory
from code_puppy.plugins.claude_plugin_adapter.config import get_claude_plugins_dir

logger = logging.getLogger(__name__)

def sync_skills_adapter(plugin_name: str, uninstall: bool = False) -> None:
    """
    Wire up the skills directory for a Claude plugin into Code Puppy's skill system.
    """
    plugin_skills_dir = get_claude_plugins_dir() / plugin_name / "skills"
    
    if uninstall:
        remove_skill_directory(str(plugin_skills_dir))
        logger.debug(f"claude_plugin_adapter: Removed skills directory for {plugin_name}")
    elif plugin_skills_dir.exists() and plugin_skills_dir.is_dir():
        if add_skill_directory(str(plugin_skills_dir)):
            logger.debug(f"claude_plugin_adapter: Added skills directory for {plugin_name}")
