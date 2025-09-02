"""
🐶 MOTD (Message of the Day) feature for code-puppy! 🐕
Stores seen versions in ~/.code_puppy/motd.txt - woof woof! 🐾
"""

import os

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info

MOTD_VERSION = "2025-09-02"
MOTD_MESSAGE = """```
# 🐶🎆🔌 WOOF WOOF BARK BARK! SEPTEMBER 02 MCP MEGA OVERHAUL! 🔌🎆🐶
# 🐕‍🦺 MASSIVE MCP INFRASTRUCTURE REVOLUTION! 🚀🌙🐕

🎉🎊🔌 EPIC MCP (Model Context Protocol) OVERHAUL ALERT! 🔌🎊🎉
🐶🔧🐕‍🦺 ENTERPRISE-GRADE MCP SERVER MANAGEMENT IS HERE!!! 🏆🐶🚀

🔌 THE NEW `/mcp` COMMAND UNIVERSE:
🚀 `/mcp` or `/mcp list` - Show beautiful server status dashboard! 📊🐕‍🦺
🟢 `/mcp start <server>` - Start any MCP server like a good boy! ▶️🐶
🔴 `/mcp stop <server>` - Stop servers when they're naughty! ⏹️🐕
🔄 `/mcp restart <server>` - Give servers a fresh puppy restart! 🔄🐶
🌟 `/mcp start-all` - Wake up ALL the server puppies! 🐕‍🦺🚀
🛑 `/mcp stop-all` - Put all servers down for nap time! 😴🐶
💾 `/mcp status <server>` - Detailed health checkup for your server! 🩺🐕
🧪 `/mcp test <server>` - Test if your server is being a good puppy! ✅🐶
📋 `/mcp logs <server>` - Read server diary entries! 📖🐕‍🦺
🔍 `/mcp search <term>` - Find servers in the registry catalog! 🕵️🐶
➕ `/mcp add` - Interactive wizard to adopt new server puppies! 🎭🐕
🗑️ `/mcp remove <server>` - Say goodbye to server (with confirmation)! 👋🐶
📦 `/mcp install <server>` - One-command server installation magic! ✨🐕‍🦺
❓ `/mcp help` - Learn all the MCP tricks! 📚🐶

🏗️ ENTERPRISE-GRADE INFRASTRUCTURE:
🔧 **Server Lifecycle Management** - Full start/stop/restart control! 🐕‍🦺
📊 **Rich Status Dashboard** - Beautiful tables with uptime & health! 📈🐶
🛡️ **Circuit Breaker Pattern** - Auto-quarantine misbehaving servers! ⚡🐕
🔄 **Retry Manager** - Smart retry logic with exponential backoff! 🧠🐶
🩺 **Health Monitor** - Continuous server health tracking! ❤️🐕‍🦺
🏥 **Error Isolation** - Contains server failures like a smart puppy! 🚧🐶
📦 **Server Registry Catalog** - 40+ pre-configured servers ready to adopt! 🐕‍🦺📚
🎭 **Interactive Install Wizard** - Guides you through server setup! 🧙‍♂️🐶
🛠️ **System Requirements Detection** - Checks if tools are installed! 🔍🐕
🌐 **Environment Variable Management** - Handles secrets securely! 🔐🐶
💼 **Command Line Arguments** - Flexible server configuration! ⚙️🐕‍🦺
🔄 **Auto Agent Reload** - Servers integrate instantly! ⚡🐶

🎾 ADDITIONAL SMART PUPPY FEATURES:
🔌 **Managed Server Classes** - Object-oriented server management! 🏗️🐕
⏱️ **Uptime Tracking** - Know how long servers have been good boys! ⏰🐶
📝 **Event Logging** - Detailed audit trail of all server activities! 📋🐕‍🦺
🎯 **Async Lifecycle** - Non-blocking server operations! 🚀🐶
🖥️ **TUI Integration** - Use Ctrl+T for graphical install wizard! 🎨🐕
📊 **Status Indicators** - Color-coded server states with emojis! 🌈🐶

🐛🔧 Bug Squashing Squad:
🚀 Rock-solid MCP server management with enterprise reliability! 💪🐕‍🦺
🛡️ Bulletproof error handling and graceful degradation! 🛡️🐶
⚡ Lightning-fast server operations with async goodness! ⚡🐕

🚀🐶 WOOF WOOF! Your MCP servers are now SUPER MANAGEABLE! 🐕‍🦺🎾🦴
🔌 Go forth and `/mcp` like the coding champion you are! 🏆🐶💖
``"
"""
MOTD_TRACK_FILE = os.path.join(CONFIG_DIR, "motd.txt")


def has_seen_motd(version: str) -> bool:  # 🐕 Check if puppy has seen this MOTD!
    if not os.path.exists(MOTD_TRACK_FILE):
        return False
    with open(MOTD_TRACK_FILE, "r") as f:
        seen_versions = {line.strip() for line in f if line.strip()}
    return version in seen_versions


def mark_motd_seen(version: str):  # 🐶 Mark MOTD as seen by this good puppy!
    # Create directory if it doesn't exist 🏠🐕
    os.makedirs(os.path.dirname(MOTD_TRACK_FILE), exist_ok=True)

    # Check if the version is already in the file 📋🐶
    seen_versions = set()
    if os.path.exists(MOTD_TRACK_FILE):
        with open(MOTD_TRACK_FILE, "r") as f:
            seen_versions = {line.strip() for line in f if line.strip()}

    # Only add the version if it's not already there 📝🐕‍🦺
    if version not in seen_versions:
        with open(MOTD_TRACK_FILE, "a") as f:
            f.write(f"{version}\n")


def print_motd(
    console=None, force: bool = False
) -> bool:  # 🐶 Print exciting puppy MOTD!
    """
    🐕 Print the message of the day to the user - woof woof! 🐕

    Args:
        console: Optional console object (for backward compatibility) 🖥️🐶
        force: Whether to force printing even if the MOTD has been seen 💪🐕‍🦺

    Returns:
        True if the MOTD was printed, False otherwise 🐾
    """
    if force or not has_seen_motd(MOTD_VERSION):
        # Create a Rich Markdown object for proper rendering 🎨🐶
        from rich.markdown import Markdown

        markdown_content = Markdown(MOTD_MESSAGE)
        emit_info(markdown_content)
        mark_motd_seen(MOTD_VERSION)
        return True
    return False
