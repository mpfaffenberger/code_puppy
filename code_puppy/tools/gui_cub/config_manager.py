"""Platform configuration manager for GUI-Cub (QA-Kitten pattern).

Follows the same pattern as QA-Kitten's Camoufox manager:
- Check config on initialization
- Run calibration on first run
- Cache for fast subsequent runs
- Auto re-calibrate if environment changes
"""

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pyautogui

from code_puppy.messaging import emit_info, emit_warning
from code_puppy.tools.common import generate_group_id


def get_gui_cub_base_dir() -> Path:
    """Get the base directory for GUI-Cub data storage."""
    base_dir = Path.home() / ".code_puppy" / "agents" / "gui_cub"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def get_config_path() -> Path:
    """Get the config.json path."""
    return get_gui_cub_base_dir() / "config.json"


def _compute_config_hash(config: Dict[str, Any]) -> str:
    """Compute SHA256 hash of important config fields for validation."""
    # Hash platform, display, and capabilities (not metadata)
    hashable = {
        "platform": config.get("platform", {}),
        "display": config.get("display", {}),
        "capabilities": config.get("capabilities", {}),
    }
    content = json.dumps(hashable, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def load_config() -> Optional[Dict[str, Any]]:
    """Load cached config from disk.
    
    Returns:
        Config dict if exists and valid, None otherwise
    """
    config_path = get_config_path()
    
    if not config_path.exists():
        return None
    
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
        
        # Validate hash
        stored_hash = config.get("metadata", {}).get("hash")
        if stored_hash:
            computed_hash = _compute_config_hash(config)
            if stored_hash != computed_hash:
                emit_warning("[yellow]Config hash mismatch, may be corrupted[/yellow]")
        
        return config
    
    except Exception as e:
        emit_warning(f"[yellow]Failed to load config: {e}[/yellow]")
        return None


def save_config(config: Dict[str, Any]) -> bool:
    """Save config to disk.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        True if saved successfully, False otherwise
    """
    config_path = get_config_path()
    
    try:
        # Add hash for validation
        config["metadata"]["hash"] = _compute_config_hash(config)
        
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        
        return True
    
    except Exception as e:
        emit_warning(f"[red]Failed to save config: {e}[/red]")
        return False


def validate_config(config: Dict[str, Any]) -> tuple[bool, str]:
    """Validate if cached config is still valid.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Tuple of (is_valid, reason)
    """
    # Check screen resolution hasn't changed
    try:
        current_resolution = list(pyautogui.size())
        cached_resolution = config.get("display", {}).get("primary_resolution")
        
        if current_resolution != cached_resolution:
            return False, f"Display resolution changed: {cached_resolution} → {current_resolution}"
    except Exception as e:
        return False, f"Failed to check display: {e}"
    
    # Check OS hasn't changed (unlikely but possible in VMs)
    current_os = sys.platform
    cached_os = config.get("platform", {}).get("os")
    
    if current_os != cached_os:
        return False, f"OS changed: {cached_os} → {current_os}"
    
    # On Windows, check if dependencies are actually installed
    if sys.platform == "win32":
        capabilities = config.get("capabilities", {})
        
        # Check if pywinauto is marked as available but isn't actually installed
        if capabilities.get("pywinauto", False):
            try:
                import pywinauto
            except ImportError:
                return False, "Windows dependencies missing (pywinauto not installed)"
        
        # If pywinauto was marked unavailable, we should try to install it
        if not capabilities.get("pywinauto", False):
            return False, "Windows dependencies not installed, will attempt installation"
        
        # Check if pytesseract/Tesseract is marked as available but isn't actually installed
        if capabilities.get("pytesseract", False):
            try:
                import pytesseract
                pytesseract.get_tesseract_version()
            except Exception:
                return False, "Tesseract OCR missing or broken, will attempt reinstallation"
        
        # If pytesseract was marked unavailable, check if we should retry installation
        # Only retry if missing_capabilities indicates it was due to admin_required
        # and user might have gained admin rights
        if not capabilities.get("pytesseract", False):
            missing = config.get("missing_capabilities", {}).get("pytesseract", {})
            if missing.get("reason") == "admin_required":
                # User might have admin now, let's retry
                return False, "Tesseract not installed, will retry installation (you may have admin now)"
            # If it failed for other reasons, still valid but keep the missing capability info
            # Don't force re-calibration every time for non-admin failures
    
    # Config is valid
    return True, "Config is valid"


async def ensure_calibrated() -> Dict[str, Any]:
    """Ensure platform is calibrated (QA-Kitten pattern).
    
    This runs on agent initialization and checks if calibration is needed.
    Fast on subsequent runs (just reads cached config).
    
    Similar to QA-Kitten's _prefetch_camoufox().
    
    Returns:
        Dict with success status and config
    """
    group_id = generate_group_id("ensure_calibrated")
    emit_info(
        "[bold cyan]🔍 Checking platform configuration...[/bold cyan]",
        message_group=group_id,
    )
    
    config_path = get_config_path()
    
    # Check if config exists
    if not config_path.exists():
        emit_info(
            "[cyan]📋 First run detected, calibrating platform...[/cyan]",
            message_group=group_id,
        )
        from code_puppy.tools.gui_cub.calibration import run_calibration
        return await run_calibration()
    
    # Load cached config
    config = load_config()
    if not config:
        emit_info(
            "[cyan]♻️ Failed to load config, re-calibrating...[/cyan]",
            message_group=group_id,
        )
        from code_puppy.tools.gui_cub.calibration import run_calibration
        return await run_calibration()
    
    # Validate config
    is_valid, reason = validate_config(config)
    if not is_valid:
        emit_info(
            f"[cyan]♻️ {reason}, re-calibrating...[/cyan]",
            message_group=group_id,
        )
        from code_puppy.tools.gui_cub.calibration import run_calibration
        return await run_calibration()
    
    # Config is valid, use cached version
    emit_info(
        "[cyan]🗃️ Using cached platform config[/cyan]",
        message_group=group_id,
    )
    
    return {
        "success": True,
        "config": config,
        "cached": True,
        "path": str(config_path),
    }


# Tool registration functions (following QA-Kitten patterns)

def register_config_tools(agent):
    """Register config management tools."""
    
    from pydantic_ai import RunContext
    
    @agent.tool
    async def gui_cub_get_config(context: RunContext) -> Dict[str, Any]:
        """Get current platform configuration.
        
        Returns cached config if valid, otherwise triggers re-calibration.
        Similar to browser_status in QA-Kitten.
        
        Returns:
            Dict with success, config, and metadata
        """
        return await ensure_calibrated()
    
    @agent.tool
    async def gui_cub_calibrate(context: RunContext) -> Dict[str, Any]:
        """Force platform re-calibration.
        
        Useful when:
        - You changed monitors
        - You updated libraries
        - Config seems incorrect
        
        Returns:
            Dict with success, config, and calibration results
        """
        group_id = generate_group_id("gui_cub_calibrate")
        emit_info(
            "[bold green] CALIBRATE [/bold green] 🔧 Forcing platform re-calibration...",
            message_group=group_id,
        )
        
        from code_puppy.tools.gui_cub.calibration import run_calibration
        return await run_calibration()
    
    @agent.tool
    async def gui_cub_validate_config(context: RunContext) -> Dict[str, Any]:
        """Validate current cached config without re-calibrating.
        
        Quick check to see if config is still valid.
        
        Returns:
            Dict with valid status and reason
        """
        group_id = generate_group_id("gui_cub_validate")
        emit_info(
            "[bold cyan] VALIDATE CONFIG [/bold cyan] ✓",
            message_group=group_id,
        )
        
        config = load_config()
        if not config:
            return {
                "success": False,
                "valid": False,
                "message": "No config found",
            }
        
        is_valid, reason = validate_config(config)
        
        if is_valid:
            emit_info(
                f"[green]✅ {reason}[/green]",
                message_group=group_id,
            )
        else:
            emit_info(
                f"[yellow]⚠️ {reason}[/yellow]",
                message_group=group_id,
            )
        
        return {
            "success": True,
            "valid": is_valid,
            "message": reason,
            "config": config if is_valid else None,
        }
    
    @agent.tool
    async def gui_cub_reset_config(context: RunContext) -> Dict[str, Any]:
        """Delete cached config to force re-calibration on next run.
        
        Useful for troubleshooting config issues.
        
        Returns:
            Dict with success status
        """
        group_id = generate_group_id("gui_cub_reset")
        emit_info(
            "[bold yellow] RESET CONFIG [/bold yellow] 🗑️",
            message_group=group_id,
        )
        
        config_path = get_config_path()
        
        if config_path.exists():
            try:
                config_path.unlink()
                emit_info(
                    "[green]✅ Config deleted, will re-calibrate on next run[/green]",
                    message_group=group_id,
                )
                return {
                    "success": True,
                    "message": "Config reset successfully",
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to delete config: {e}",
                }
        else:
            return {
                "success": True,
                "message": "No config found to delete",
            }
