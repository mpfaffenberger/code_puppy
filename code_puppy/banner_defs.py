"""Built-in banner definitions for every core and browser tool.

Each core tool, including core tools registered by plugins, needs an entry here;
tests/test_banner_defs.py fails for any tool without one. ``name`` must be a colour key in
config.DEFAULT_BANNER_COLORS (or be listed as default-coloured in that test).

Depends on: banners.py :: BannerDef, register_banner_def().
Called by: banners.py :: _ensure_builtins().
Browser rows must cover tools/_browser_registry.py :: BROWSER_TOOL_REGISTRY exactly (tests/test_banner_defs.py).
"""

from code_puppy.banners import BannerDef, register_banner_def

_BROWSER_COLOUR = "terminal_tool"
_INVOKE_AGENT = BannerDef(
    "invoke_agent",
    "INVOKE AGENT",
    "other",
    ("agent_name",),
    "text",
    "renderer.invoke_agent",
)
_SHELL = BannerDef(
    "shell_command",
    "SHELL COMMAND",
    "execute",
    ("command",),
    "command",
    "renderer.shell_command",
)
_EDIT_FILE = BannerDef("replace_in_file", "EDIT FILE", "edit", ("file_path",), "path")

_CORE: dict[str, BannerDef] = {
    "list_agents": BannerDef("list_agents", "LIST AGENTS", "other"),
    "invoke_agent": _INVOKE_AGENT,
    "invoke_agent_with_model": _INVOKE_AGENT,
    "list_available_models": BannerDef(
        "list_available_models",
        "LIST MODELS",
        "other",
        label_key="banner.list_available_models",
    ),
    "list_files": BannerDef(
        "directory_listing",
        "DIRECTORY LISTING",
        "read",
        ("directory",),
        "path",
        "renderer.directory_listing",
    ),
    "read_file": BannerDef(
        "read_file", "READ FILE", "read", ("file_path",), "path", "renderer.read_file"
    ),
    "grep": BannerDef(
        "grep", "GREP", "search", ("search_string",), "query", "renderer.grep"
    ),
    "edit_file": BannerDef("edit_file", "EDIT FILE", "edit", ("file_path",), "path"),
    "create_file": BannerDef(
        "create_file", "CREATE FILE", "edit", ("file_path",), "path"
    ),
    "replace_in_file": _EDIT_FILE,
    "delete_snippet": _EDIT_FILE,
    "delete_file": BannerDef(
        "delete_file", "DELETE FILE", "delete", ("file_path",), "path"
    ),
    "shell": _SHELL,
    "agent_run_shell_command": _SHELL,
    "run_shell_command": _SHELL,
    "run_shell_commmand": _SHELL,
    "agent_share_your_reasoning": BannerDef(
        "agent_reasoning",
        "AGENT REASONING",
        "think",
        ("reasoning",),
        "text",
        "renderer.agent_reasoning",
    ),
    "ask_user_question": BannerDef(
        "ask_user_question",
        "ASK USER QUESTION",
        "other",
        label_key="banner.ask_user_question",
    ),
    "load_image_for_analysis": BannerDef(
        "load_image_for_analysis",
        "LOAD IMAGE",
        "read",
        ("image_path",),
        "path",
        "banner.load_image_for_analysis",
    ),
    "universal_constructor": BannerDef(
        "universal_constructor",
        "UNIVERSAL CONSTRUCTOR",
        "other",
        ("action",),
        "text",
        "renderer.universal_constructor",
    ),
    "activate_skill": BannerDef(
        "agent_response", "ACTIVATE SKILL", "other", ("skill_name",), "text"
    ),
    "list_or_search_skills": BannerDef(
        "agent_response", "LIST SKILLS", "search", ("query",), "query"
    ),
}

# (tool, label, kind, target_args, target_type). Labels are catalog keys
# ``banner.<tool>``; tests pin that every row has one.
_BROWSER_ROWS: tuple[tuple[str, str, str, tuple[str, ...], str | None], ...] = (
    ("browser_initialize", "BROWSER INITIALIZE", "other", (), None),
    ("browser_close", "BROWSER CLOSE", "other", (), None),
    ("browser_status", "BROWSER STATUS", "other", (), None),
    ("browser_new_page", "BROWSER NEW PAGE", "fetch", ("url",), "url"),
    ("browser_list_pages", "BROWSER LIST PAGES", "other", (), None),
    ("browser_navigate", "BROWSER NAVIGATE", "fetch", ("url",), "url"),
    ("browser_get_page_info", "BROWSER GET PAGE INFO", "other", (), None),
    ("browser_go_back", "BROWSER GO BACK", "fetch", (), None),
    ("browser_go_forward", "BROWSER GO FORWARD", "fetch", (), None),
    ("browser_reload", "BROWSER RELOAD", "fetch", (), None),
    ("browser_wait_for_load", "BROWSER WAIT FOR LOAD", "other", (), None),
    (
        "browser_find_by_role",
        "BROWSER FIND BY ROLE",
        "search",
        ("role", "name"),
        "text",
    ),
    ("browser_find_by_text", "BROWSER FIND BY TEXT", "search", ("text",), "text"),
    ("browser_find_by_label", "BROWSER FIND BY LABEL", "search", ("text",), "text"),
    (
        "browser_find_by_placeholder",
        "BROWSER FIND BY PLACEHOLDER",
        "search",
        ("text",),
        "text",
    ),
    (
        "browser_find_by_test_id",
        "BROWSER FIND BY TEST ID",
        "search",
        ("test_id",),
        "text",
    ),
    ("browser_xpath_query", "BROWSER XPATH QUERY", "search", ("xpath",), "query"),
    (
        "browser_find_buttons",
        "BROWSER FIND BUTTONS",
        "search",
        ("text_filter",),
        "text",
    ),
    ("browser_find_links", "BROWSER FIND LINKS", "search", ("text_filter",), "text"),
    ("browser_page_snapshot", "BROWSER PAGE SNAPSHOT", "search", (), None),
    ("browser_click", "BROWSER CLICK", "other", ("selector",), "query"),
    ("browser_double_click", "BROWSER DOUBLE CLICK", "other", ("selector",), "query"),
    ("browser_hover", "BROWSER HOVER", "other", ("selector",), "query"),
    ("browser_set_text", "BROWSER SET TEXT", "other", ("selector",), "query"),
    ("browser_get_text", "BROWSER GET TEXT", "other", ("selector",), "query"),
    ("browser_get_value", "BROWSER GET VALUE", "other", ("selector",), "query"),
    ("browser_select_option", "BROWSER SELECT OPTION", "other", ("selector",), "query"),
    ("browser_check", "BROWSER CHECK", "other", ("selector",), "query"),
    ("browser_uncheck", "BROWSER UNCHECK", "other", ("selector",), "query"),
    (
        "browser_click_by_role",
        "BROWSER CLICK BY ROLE",
        "other",
        ("role", "name"),
        "text",
    ),
    ("browser_click_by_text", "BROWSER CLICK BY TEXT", "other", ("text",), "text"),
    (
        "browser_set_text_by_label",
        "BROWSER SET TEXT BY LABEL",
        "other",
        ("label",),
        "text",
    ),
    ("browser_execute_js", "BROWSER EXECUTE JS", "other", (), None),
    ("browser_scroll", "BROWSER SCROLL", "other", ("element_selector",), "query"),
    (
        "browser_scroll_to_element",
        "BROWSER SCROLL TO ELEMENT",
        "other",
        ("selector",),
        "query",
    ),
    ("browser_set_viewport", "BROWSER SET VIEWPORT", "other", (), None),
    (
        "browser_wait_for_element",
        "BROWSER WAIT FOR ELEMENT",
        "other",
        ("selector",),
        "query",
    ),
    ("browser_highlight_element", "BROWSER HIGHLIGHT", "other", ("selector",), "query"),
    ("browser_clear_highlights", "BROWSER CLEAR HIGHLIGHTS", "other", (), None),
    (
        "browser_screenshot_analyze",
        "BROWSER SCREENSHOT",
        "read",
        ("element_selector",),
        "query",
    ),
    ("browser_save_workflow", "BROWSER SAVE WORKFLOW", "edit", ("name",), "text"),
    ("browser_list_workflows", "BROWSER LIST WORKFLOWS", "other", (), None),
    ("browser_read_workflow", "BROWSER READ WORKFLOW", "read", ("name",), "text"),
)

_BROWSER: dict[str, BannerDef] = {
    tool: BannerDef(
        _BROWSER_COLOUR,
        label,
        kind,
        target_args,
        target_type,
        label_key=f"banner.{tool}",
    )
    for tool, label, kind, target_args, target_type in _BROWSER_ROWS
}

BUILTIN_BANNER_DEFS: dict[str, BannerDef] = {**_CORE, **_BROWSER}


def register_builtin_banner_defs() -> None:
    """Register every built-in definition; repeated calls leave the same state."""
    for tool_name, definition in BUILTIN_BANNER_DEFS.items():
        register_banner_def(tool_name, definition)
