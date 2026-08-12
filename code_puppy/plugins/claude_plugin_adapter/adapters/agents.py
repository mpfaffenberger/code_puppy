import json
import logging
from pathlib import Path

from code_puppy.config import get_user_agents_directory
from code_puppy.plugins.claude_plugin_adapter.config import get_claude_plugins_dir
from code_puppy.plugins.agent_skills.metadata import (
    parse_yaml_frontmatter,
    FRONTMATTER_PATTERN,
)
from code_puppy.hook_engine.aliases import resolve_internal_name

logger = logging.getLogger(__name__)


def sync_agents_adapter(plugin_name: str, uninstall: bool = False) -> None:
    """
    Sync a Claude plugin's agents (from agents/*.md) into Code Puppy's user agents dir.
    If uninstall is True, only removes the agents managed by this plugin.
    """
    plugin_agents_dir = get_claude_plugins_dir() / plugin_name / "agents"
    agents_dir = Path(get_user_agents_directory())

    managed_tag = f"claude_plugin_adapter:{plugin_name}"

    # 1. Uninstall existing ones managed by this plugin
    if agents_dir.exists():
        for agent_file in agents_dir.glob("*.json"):
            try:
                with open(agent_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("_managed_by") == managed_tag:
                    agent_file.unlink()
                    logger.debug(
                        f"claude_plugin_adapter: Removed managed agent {agent_file}"
                    )
            except Exception as e:
                logger.error(
                    f"claude_plugin_adapter: Failed to process agent {agent_file}: {e}"
                )

    if uninstall:
        return

    # 2. Install from plugin directory
    if not plugin_agents_dir.exists():
        return

    agents_dir.mkdir(parents=True, exist_ok=True)

    for md_file in plugin_agents_dir.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            frontmatter = parse_yaml_frontmatter(content)

            if not frontmatter or not frontmatter.get("name"):
                logger.warning(
                    f"claude_plugin_adapter: Invalid frontmatter in {md_file}"
                )
                continue

            name = frontmatter["name"]
            description = frontmatter.get("description", "")

            # The body is everything after the frontmatter
            body = FRONTMATTER_PATTERN.sub("", content, count=1).strip()

            # Parse tools and map them
            tools = frontmatter.get("tools", [])
            mapped_tools = []

            # YAML parser might return a string if there's only one, handle that
            if isinstance(tools, str):
                tools = [t.strip() for t in tools.split(",") if t.strip()]

            for t in tools:
                if isinstance(t, str):
                    internal_name = resolve_internal_name(t)
                    if internal_name:
                        mapped_tools.append(internal_name)
                    else:
                        mapped_tools.append(t)

            if not mapped_tools:
                # no-tools = sensible default set (Claude's inherit-all semantics)
                mapped_tools = [
                    "agent_run_shell_command",
                    "read_file",
                    "list_files",
                    "replace_in_file",
                    "create_file",
                    "grep_search",
                ]

            # Create agent json
            agent_json = {
                "_managed_by": managed_tag,
                "name": name,
                "description": description,
                "system_prompt": body,
                "tools": mapped_tools,
                # "model" hints ignored as requested
            }

            dest_file = agents_dir / f"{name}.json"
            with open(dest_file, "w", encoding="utf-8") as f:
                json.dump(agent_json, f, indent=2)

            logger.debug(
                f"claude_plugin_adapter: Installed agent {name} from {plugin_name}"
            )

        except Exception as e:
            logger.error(f"claude_plugin_adapter: Failed to sync agent {md_file}: {e}")
