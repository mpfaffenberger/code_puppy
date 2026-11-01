"""Built-in banner definitions: TOOL_REGISTRY coverage, terminal parity, kinds, colours."""

import ast
from pathlib import Path

import pytest

import code_puppy.tools as tools_pkg
from code_puppy import banners, config
from code_puppy.banner_defs import BUILTIN_BANNER_DEFS, register_builtin_banner_defs
from code_puppy.banners import (
    BannerDef,
    banner_for_call,
    get_banner_def,
    has_banner_def,
    register_banner_def,
)
from code_puppy.i18n import catalog, translate
from code_puppy.tools import TOOL_REGISTRY
from code_puppy.tools._browser_registry import BROWSER_TOOL_REGISTRY
from code_puppy.tools._lazy import lazy_registration

VALID_KINDS = frozenset(
    {"read", "edit", "delete", "search", "execute", "think", "fetch", "other"}
)
# Names that intentionally fall back to the default banner colour.
DEFAULT_COLOUR_NAMES = frozenset(
    {
        "delete_file",
        "ask_user_question",
        "load_image_for_analysis",
        "list_available_models",
    }
)
SHELL_ALIASES = (
    "shell",
    "agent_run_shell_command",
    "run_shell_command",
    "run_shell_commmand",
)

# tool, colour name, terminal label, kind, target_args, target_type
PARITY_ROWS = [
    ("read_file", "read_file", "READ FILE", "read", ("file_path",), "path"),
    (
        "list_files",
        "directory_listing",
        "DIRECTORY LISTING",
        "read",
        ("directory",),
        "path",
    ),
    ("grep", "grep", "GREP", "search", ("search_string",), "query"),
    ("shell", "shell_command", "SHELL COMMAND", "execute", ("command",), "command"),
    (
        "agent_run_shell_command",
        "shell_command",
        "SHELL COMMAND",
        "execute",
        ("command",),
        "command",
    ),
    (
        "run_shell_command",
        "shell_command",
        "SHELL COMMAND",
        "execute",
        ("command",),
        "command",
    ),
    (
        "run_shell_commmand",
        "shell_command",
        "SHELL COMMAND",
        "execute",
        ("command",),
        "command",
    ),
    ("create_file", "create_file", "CREATE FILE", "edit", ("file_path",), "path"),
    ("replace_in_file", "replace_in_file", "EDIT FILE", "edit", ("file_path",), "path"),
    ("delete_snippet", "replace_in_file", "EDIT FILE", "edit", ("file_path",), "path"),
    ("edit_file", "edit_file", "EDIT FILE", "edit", ("file_path",), "path"),
    ("delete_file", "delete_file", "DELETE FILE", "delete", ("file_path",), "path"),
    (
        "agent_share_your_reasoning",
        "agent_reasoning",
        "AGENT REASONING",
        "think",
        ("reasoning",),
        "text",
    ),
    ("invoke_agent", "invoke_agent", "INVOKE AGENT", "other", ("agent_name",), "text"),
    (
        "invoke_agent_with_model",
        "invoke_agent",
        "INVOKE AGENT",
        "other",
        ("agent_name",),
        "text",
    ),
    ("list_agents", "list_agents", "LIST AGENTS", "other", (), None),
    (
        "universal_constructor",
        "universal_constructor",
        "UNIVERSAL CONSTRUCTOR",
        "other",
        ("action",),
        "text",
    ),
    ("ask_user_question", "ask_user_question", "ASK USER QUESTION", "other", (), None),
    (
        "load_image_for_analysis",
        "load_image_for_analysis",
        "LOAD IMAGE",
        "read",
        ("image_path",),
        "path",
    ),
    (
        "list_available_models",
        "list_available_models",
        "LIST MODELS",
        "other",
        (),
        None,
    ),
    (
        "activate_skill",
        "agent_response",
        "ACTIVATE SKILL",
        "other",
        ("skill_name",),
        "text",
    ),
    (
        "list_or_search_skills",
        "agent_response",
        "LIST SKILLS",
        "search",
        ("query",),
        "query",
    ),
]

# Browser rows are data-driven, so spot-check one per kind and target type.
BROWSER_SAMPLES = [
    ("browser_navigate", "fetch", ("url",), "url"),
    ("browser_go_back", "fetch", (), None),
    ("browser_find_by_role", "search", ("role", "name"), "text"),
    ("browser_click", "other", ("selector",), "query"),
    ("browser_screenshot_analyze", "read", ("element_selector",), "query"),
]


@pytest.fixture(autouse=True)
def _english_catalog():
    # Parity compares literal English text, so the host locale must not leak in.
    translate.get_translator().set_locale("en-US")
    yield
    translate.get_translator().set_locale("en-US")


@pytest.fixture
def builtins_registry(monkeypatch):
    """Isolated registry populated with only the built-in definitions."""
    monkeypatch.setattr(banners, "_definitions", {})
    monkeypatch.setattr(banners, "_builtins_loaded", True)
    register_builtin_banner_defs()


def _is_core_registration(register_fn) -> bool:
    # Plugins and tests mutate the process-global TOOL_REGISTRY and never clean up,
    # so built-ins are identified by where their registration function is defined.
    module = getattr(register_fn, "__module__", None) or ""
    return module == "code_puppy.tools" or module.startswith("code_puppy.tools.")


def _missing_builtin_definitions() -> list[str]:
    return sorted(
        tool
        for tool, register_fn in TOOL_REGISTRY.items()
        if _is_core_registration(register_fn) and not has_banner_def(tool)
    )


def test_every_tool_registry_key_has_a_banner_definition(builtins_registry):
    missing = _missing_builtin_definitions()
    assert not missing, (
        f"Built-in tools in TOOL_REGISTRY without a BannerDef: {missing}. "
        "Fix: register a BannerDef for each in code_puppy/banner_defs.py."
    )


def test_plugin_registration_is_not_treated_as_builtin(builtins_registry, monkeypatch):
    def plugin_register(agent):
        return None

    monkeypatch.setitem(TOOL_REGISTRY, "fake_plugin_tool", plugin_register)
    assert "fake_plugin_tool" not in _missing_builtin_definitions()


def test_core_style_registration_without_definition_is_reported(
    builtins_registry, monkeypatch
):
    register_fn = lazy_registration(
        "code_puppy.tools.agent_tools", "register_list_agents"
    )
    monkeypatch.setitem(TOOL_REGISTRY, "fake_builtin_tool", register_fn)
    assert "fake_builtin_tool" in _missing_builtin_definitions()


# Core tools registered through a plugin callback, so absent from TOOL_REGISTRY.
PLUGIN_REGISTERED_CORE_TOOLS = (
    "activate_skill",
    "list_or_search_skills",
    "universal_constructor",
)
TOOLS_DIR = Path(tools_pkg.__file__).parent


@pytest.mark.parametrize("tool", PLUGIN_REGISTERED_CORE_TOOLS)
def test_core_tools_registered_by_plugins_have_definitions(builtins_registry, tool):
    assert has_banner_def(tool)


def _tool_names_in_register(register_fn: ast.FunctionDef) -> set[str]:
    # Covers both `@agent.tool(...)` decorators and `return agent.tool(fn)` calls.
    names: set[str] = set()
    for node in ast.walk(register_fn):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node is not register_fn and any(
                "agent.tool" in ast.unparse(dec) for dec in node.decorator_list
            ):
                names.add(node.name)
        elif isinstance(node, ast.Call) and ast.unparse(node.func) == "agent.tool":
            if node.args and isinstance(node.args[0], ast.Name):
                names.add(node.args[0].id)
    return names


def _scan_core_tools() -> dict[str, str]:
    """Map each tool defined in code_puppy/tools/*.py to its register function."""
    found: dict[str, str] = {}
    for path in sorted(TOOLS_DIR.glob("*.py")):
        if path.stem == "__init__" or path.stem.startswith("_"):
            continue
        if "browser" in path.stem:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("register_"):
                for tool in _tool_names_in_register(node):
                    found[tool] = f"{path.stem}.{node.name}"
    return found


def test_source_scan_finds_core_tools_it_guards():
    # A silently empty scan would make the guard below pass vacuously.
    scanned = set(_scan_core_tools())
    assert {"shell", "read_file", "activate_skill", "list_or_search_skills"} <= scanned
    assert "invoke_agent" in scanned


def test_every_core_tool_in_source_has_a_banner_definition(builtins_registry):
    missing = {
        tool: origin
        for tool, origin in _scan_core_tools().items()
        if not has_banner_def(tool)
    }
    assert not missing, (
        f"Core tools defined in code_puppy/tools without a BannerDef: {missing}. "
        "Fix: add each to _CORE in code_puppy/banner_defs.py."
    )


def test_unregistered_tool_is_not_reported_and_falls_back(builtins_registry):
    assert has_banner_def("fake_tool_xyz") is False
    assert get_banner_def("fake_tool_xyz") == BannerDef(
        name="fake_tool_xyz", label="FAKE_TOOL_XYZ", kind="other"
    )


@pytest.mark.parametrize(
    ("tool", "name", "label", "kind", "target_args", "target_type"),
    PARITY_ROWS,
    ids=[row[0] for row in PARITY_ROWS],
)
def test_builtin_definition_matches_terminal_contract(
    builtins_registry, tool, name, label, kind, target_args, target_type
):
    definition = get_banner_def(tool)
    assert (
        definition.name,
        definition.resolved_label(),
        definition.kind,
        definition.target_args,
        definition.target_type,
    ) == (name, label, kind, target_args, target_type)


@pytest.mark.parametrize(
    ("tool", "kind", "target_args", "target_type"),
    BROWSER_SAMPLES,
    ids=[row[0] for row in BROWSER_SAMPLES],
)
def test_browser_definition_kind_and_target(
    builtins_registry, tool, kind, target_args, target_type
):
    definition = get_banner_def(tool)
    assert (definition.name, definition.kind, definition.target_args) == (
        "terminal_tool",
        kind,
        target_args,
    )
    assert definition.target_type == target_type


def test_browser_table_covers_browser_registry_exactly():
    browser_tools = {
        tool
        for tool, definition in BUILTIN_BANNER_DEFS.items()
        if definition.name == "terminal_tool"
    }
    assert browser_tools == set(BROWSER_TOOL_REGISTRY)


@pytest.mark.parametrize("alias", SHELL_ALIASES)
def test_shell_aliases_share_one_execute_definition(builtins_registry, alias):
    assert get_banner_def(alias) == get_banner_def("shell")
    assert get_banner_def(alias).kind == "execute"


def test_agent_run_shell_command_call_banner_is_execute(builtins_registry):
    banner = banner_for_call("agent_run_shell_command", {"command": "ls"})
    assert (banner.kind, banner.title) == ("execute", "SHELL COMMAND ls")


@pytest.mark.parametrize(
    ("tool", "args", "title"),
    [
        ("read_file", {"file_path": "/a/b/c.txt"}, "READ FILE c.txt"),
        (
            "browser_navigate",
            {"url": "https://example.com"},
            "BROWSER NAVIGATE https://example.com",
        ),
        ("ask_user_question", {}, "ASK USER QUESTION"),
    ],
    ids=["path-basename", "browser-url", "no-target"],
)
def test_call_titles_use_definition_label_and_target(
    builtins_registry, tool, args, title
):
    assert banner_for_call(tool, args).title == title


def test_every_builtin_kind_is_a_valid_acp_kind():
    invalid = {
        tool: definition.kind
        for tool, definition in BUILTIN_BANNER_DEFS.items()
        if definition.kind not in VALID_KINDS
    }
    assert not invalid, f"Non-ACP kinds: {invalid}"


def test_every_builtin_label_is_non_empty():
    empty = sorted(
        tool
        for tool, definition in BUILTIN_BANNER_DEFS.items()
        if not definition.resolved_label().strip()
    )
    assert not empty, f"Empty labels: {empty}"


def test_every_label_key_exists_in_english_catalog_with_matching_text():
    english = catalog.load_catalog("en-US")
    problems = []
    for tool, definition in BUILTIN_BANNER_DEFS.items():
        if definition.label_key is None:
            continue
        if definition.label_key not in english:
            problems.append(f"{tool}: missing key {definition.label_key}")
        elif english[definition.label_key] != definition.label:
            problems.append(f"{tool}: catalog text differs from literal label")
    assert not problems, problems


def test_register_builtin_banner_defs_is_idempotent(builtins_registry):
    first = dict(banners._definitions)
    register_builtin_banner_defs()
    assert banners._definitions == first


def test_builtin_registration_keeps_plugin_definitions(builtins_registry):
    plugin_definition = BannerDef("my_plugin.notice", "MY PLUGIN", "other")
    register_banner_def("my_plugin_tool", plugin_definition)
    register_builtin_banner_defs()
    assert get_banner_def("my_plugin_tool") == plugin_definition


def test_builtin_colour_names_exist_or_intentionally_use_default():
    names = {definition.name for definition in BUILTIN_BANNER_DEFS.values()}
    unknown = sorted(names - set(config.DEFAULT_BANNER_COLORS) - DEFAULT_COLOUR_NAMES)
    assert not unknown, (
        f"Colour names without DEFAULT_BANNER_COLORS entry: {unknown}. "
        "Add a colour in config.py or list the name in DEFAULT_COLOUR_NAMES."
    )


def test_default_colour_allow_list_is_not_stale():
    names = {definition.name for definition in BUILTIN_BANNER_DEFS.values()}
    assert DEFAULT_COLOUR_NAMES <= names
    assert not DEFAULT_COLOUR_NAMES & set(config.DEFAULT_BANNER_COLORS)
