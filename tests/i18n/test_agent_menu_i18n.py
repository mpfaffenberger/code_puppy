"""Source-level extraction contract for the agent menu."""

from pathlib import Path

from code_puppy.i18n import audit


def test_agent_menu_has_no_raw_emit_sites():
    """Every literal message-bus string in agent_menu must use the catalog."""
    root = Path(__file__).resolve().parents[2]
    source_path = root / "code_puppy" / "command_line" / "agent_menu.py"
    sites = audit.audit_source(source_path.read_text(), str(source_path))
    raw_sites = [site for site in sites if site.kind == "raw"]
    assert not raw_sites, [f"{site.path}:{site.line}" for site in raw_sites]
