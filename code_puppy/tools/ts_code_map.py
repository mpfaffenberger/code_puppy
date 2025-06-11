import os
from code_puppy.tools.common import should_ignore_path
from pathlib import Path
from rich.text import Text
from rich.tree import Tree as RichTree
from rich.console import Console
from tree_sitter_language_pack import get_parser

from functools import partial, wraps


def _f(fmt):  # helper to keep the table tidy
    return lambda name, _fmt=fmt: _fmt.format(name=name)


def mark_export(label_fn, default=False):
    """Decorator to prefix 'export ' (or 'export default ') when requested."""

    @wraps(label_fn)
    def _wrap(name, *, exported=False):
        prefix = "export default " if default else "export " if exported else ""
        return prefix + label_fn(name)

    return _wrap


LANGS = {
    ".py": {
        "lang": "python",
        "name_field": "name",
        "nodes": {
            "function_definition": partial(_f("def {name}()"), style="green"),
            "class_definition": partial(_f("class {name}"), style="magenta"),
        },
    },
    ".rb": {
        "lang": "ruby",
        "name_field": "name",
        "nodes": {
            "method": partial(_f("def {name}"), style="green"),
            "class": partial(_f("class {name}"), style="magenta"),
        },
    },
    ".php": {
        "lang": "php",
        "name_field": "name",
        "nodes": {
            "function_definition": partial(_f("function {name}()"), style="green"),
            "class_declaration": partial(_f("class {name}"), style="magenta"),
        },
    },
    ".lua": {
        "lang": "lua",
        "name_field": "name",
        "nodes": {
            "function_declaration": partial(_f("function {name}()"), style="green")
        },
    },
    ".pl": {
        "lang": "perl",
        "name_field": "name",
        "nodes": {"sub_definition": partial(_f("sub {name}()"), style="green")},
    },
    ".r": {
        "lang": "r",
        "name_field": "name",
        "nodes": {"function_definition": partial(_f("func {name}()"), style="green")},
    },
    ".js": {
        "lang": "javascript",
        "name_field": "name",
        "nodes": {
            "function_declaration": partial(_f("function {name}()"), style="green"),
            "class_declaration": partial(_f("class {name}"), style="magenta"),
            "export_statement": partial(_f("export {name}"), style="yellow"),
            "export_default_statement": partial(
                _f("export default {name}"), style="yellow"
            ),
        },
    },
    ".mjs": {
        "lang": "javascript",
        "name_field": "name",
        "nodes": {
            "function_declaration": partial(_f("function {name}()"), style="green"),
            "class_declaration": partial(_f("class {name}"), style="magenta"),
            "export_statement": partial(_f("export {name}"), style="yellow"),
            "export_default_statement": partial(
                _f("export default {name}"), style="yellow"
            ),
        },
    },
    ".cjs": {
        "lang": "javascript",
        "name_field": "name",
        "nodes": {
            "function_declaration": partial(_f("function {name}()"), style="green"),
            "class_declaration": partial(_f("class {name}"), style="magenta"),
            "export_statement": partial(_f("export {name}"), style="yellow"),
            "export_default_statement": partial(
                _f("export default {name}"), style="yellow"
            ),
        },
    },
    ".jsx": {
        "lang": "jsx",
        "name_field": None,
        "nodes": {
            "function_declaration": partial(_f("function {name}()"), style="green"),
            "class_declaration": partial(_f("class {name}"), style="magenta"),
            "export_statement": partial(_f("export {name}"), style="yellow"),
        },
    },
    ".ts": {
        "lang": "tsx",
        "name_field": None,
        "nodes": {
            "function_declaration": partial(_f("function {name}()"), style="green"),
            "class_declaration": partial(_f("class {name}"), style="magenta"),
            "export_statement": partial(_f("export {name}"), style="yellow"),
        },
    },
    ".tsx": {
        "lang": "tsx",
        "name_field": None,
        "nodes": {
            "function_declaration": partial(_f("function {name}()"), style="green"),
            "class_declaration": partial(_f("class {name}"), style="magenta"),
            "export_statement": partial(_f("export {name}"), style="yellow"),
            "interface_declaration": partial(_f("interface {name}"), style="green"),
        },
    },
    # ─────────  systems / compiled  ────────────────────────────────────
    ".c": {
        "lang": "c",
        "name_field": "declarator",  # struct ident is under declarator
        "nodes": {
            "function_definition": partial(_f("fn {name}()"), style="green"),
            "struct_specifier": partial(_f("struct {name}"), style="magenta"),
        },
    },
    ".h": {
        "lang": "c",
        "name_field": "declarator",  # struct ident is under declarator
        "nodes": {
            "function_definition": partial(_f("fn {name}()"), style="green"),
            "struct_specifier": partial(_f("struct {name}"), style="magenta"),
        },
    },
    ".cpp": {
        "lang": "cpp",
        "name_field": "declarator",
        "nodes": {
            "function_definition": partial(_f("fn {name}()"), style="green"),
            "class_specifier": partial(_f("class {name}"), style="magenta"),
            "struct_specifier": partial(_f("struct {name}"), style="magenta"),
        },
    },
    ".hpp": {
        "lang": "cpp",
        "name_field": "declarator",
        "nodes": {
            "function_definition": partial(_f("fn {name}()"), style="green"),
            "class_specifier": partial(_f("class {name}"), style="magenta"),
            "struct_specifier": partial(_f("struct {name}"), style="magenta"),
        },
    },
    ".cc": {
        "lang": "cpp",
        "name_field": "declarator",
        "nodes": {
            "function_definition": partial(_f("fn {name}()"), style="green"),
            "class_specifier": partial(_f("class {name}"), style="magenta"),
            "struct_specifier": partial(_f("struct {name}"), style="magenta"),
        },
    },
    ".hh": {
        "lang": "cpp",
        "name_field": "declarator",
        "nodes": {
            "function_definition": partial(_f("fn {name}()"), style="green"),
            "class_specifier": partial(_f("class {name}"), style="magenta"),
            "struct_specifier": partial(_f("struct {name}"), style="magenta"),
        },
    },
    ".cs": {
        "lang": "c_sharp",
        "name_field": "name",
        "nodes": {
            "method_declaration": partial(_f("method {name}()"), style="green"),
            "class_declaration": partial(_f("class {name}"), style="magenta"),
        },
    },
    ".java": {
        "lang": "java",
        "name_field": "name",
        "nodes": {
            "method_declaration": partial(_f("method {name}()"), style="green"),
            "class_declaration": partial(_f("class {name}"), style="magenta"),
        },
    },
    ".kt": {
        "lang": "kotlin",
        "name_field": "name",
        "nodes": {
            "function_declaration": partial(_f("fun {name}()"), style="green"),
            "class_declaration": partial(_f("class {name}"), style="magenta"),
        },
    },
    ".swift": {
        "lang": "swift",
        "name_field": "name",
        "nodes": {
            "function_declaration": partial(_f("func {name}()"), style="green"),
            "class_declaration": partial(_f("class {name}"), style="magenta"),
        },
    },
    ".go": {
        "lang": "go",
        "name_field": "name",
        "nodes": {
            "function_declaration": partial(_f("func {name}()"), style="green"),
            "type_spec": partial(_f("type {name}"), style="magenta"),
        },
    },
    ".rs": {
        "lang": "rust",
        "name_field": "name",
        "nodes": {
            "function_item": partial(_f("fn {name}()"), style="green"),
            "struct_item": partial(_f("struct {name}"), style="magenta"),
            "trait_item": partial(_f("trait {name}"), style="magenta"),
        },
    },
    ".zig": {
        "lang": "zig",
        "name_field": "name",
        "nodes": {
            "fn_proto": partial(_f("fn {name}()"), style="green"),
            "struct_decl": partial(_f("struct {name}"), style="magenta"),
        },
    },
    ".scala": {
        "lang": "scala",
        "name_field": "name",
        "nodes": {
            "function_definition": partial(_f("def {name}()"), style="green"),
            "class_definition": partial(_f("class {name}"), style="magenta"),
            "object_definition": partial(_f("object {name}"), style="magenta"),
        },
    },
    ".hs": {
        "lang": "haskell",
        "name_field": "name",
        "nodes": {
            "function_declaration": partial(_f("fun {name}"), style="green"),
            "type_declaration": partial(_f("type {name}"), style="magenta"),
        },
    },
    ".jl": {
        "lang": "julia",
        "name_field": "name",
        "nodes": {
            "function_definition": partial(_f("function {name}()"), style="green"),
            "abstract_type_definition": partial(_f("abstract {name}"), style="magenta"),
            "struct_definition": partial(_f("struct {name}"), style="magenta"),
        },
    },
    # ────────  markup / style  ─────────────────────────────────────────
    ".html": {
        "lang": "html",
        "name_field": None,
        "nodes": {
            # rely on parser presence; generic element handling not needed for tests
        },
    },
    ".css": {
        "lang": "css",
        "name_field": None,
        "nodes": {},
    },
    # ─────────  scripting (shell / infra)  ─────────────────────────────
    ".sh": {
        "lang": "bash",
        "name_field": "name",
        "nodes": {"function_definition": partial(_f("fn {name}()"), style="green")},
    },
    ".ps1": {
        "lang": "powershell",
        "name_field": "name",
        "nodes": {
            "function_definition": partial(_f("function {name}()"), style="green")
        },
    },
}

# ---------------------------------------------------------------------------
# Emoji helpers (cute! 🐶)
# ---------------------------------------------------------------------------

_NODE_EMOJIS = {
    "function": "🦴",
    "class": "🏠",
    "struct": "🏗️",
    "interface": "🎛️",
    "trait": "💎",
    "type": "🧩",
    "object": "📦",
    "export": "📤",
}

_FILE_EMOJIS = {
    ".py": "🐍",
    ".js": "✨",
    ".jsx": "✨",
    ".ts": "🌀",
    ".tsx": "🌀",
    ".rb": "💎",
    ".go": "🐹",
    ".rs": "🦀",
    ".java": "☕️",
    ".c": "🔧",
    ".cpp": "➕",
    ".hpp": "➕",
    ".swift": "🕊️",
    ".kt": "🤖",
}
_PARSER_CACHE = {}


def parser_for(lang_name):
    if lang_name not in _PARSER_CACHE:
        _PARSER_CACHE[lang_name] = get_parser(lang_name)
    return _PARSER_CACHE[lang_name]


# ----------------------------------------------------------------------
# helper: breadth-first search for an identifier-ish node
# ----------------------------------------------------------------------
def _first_identifier(node):
    from collections import deque

    q = deque([node])
    while q:
        n = q.popleft()
        if n.type in {"identifier", "property_identifier", "type_identifier"}:
            return n
        q.extend(n.children)
    return None


def _span(node):
    """Return "[start:end]" lines (1‑based, inclusive)."""
    start_line = node.start_point[0] + 1
    end_line = node.end_point[0] + 1
    return Text(f"  [{start_line}:{end_line}]", style="bold white")


def _emoji_for_node_type(ts_type: str) -> str:
    """Return a cute emoji for a given Tree-sitter node type (best-effort)."""
    # naive mapping based on substrings – keeps it simple
    if "function" in ts_type or "method" in ts_type or ts_type.startswith("fn_"):
        return _NODE_EMOJIS["function"]
    if "class" in ts_type:
        return _NODE_EMOJIS["class"]
    if "struct" in ts_type:
        return _NODE_EMOJIS["struct"]
    if "interface" in ts_type:
        return _NODE_EMOJIS["interface"]
    if "trait" in ts_type:
        return _NODE_EMOJIS["trait"]
    if "type_spec" in ts_type or "type_declaration" in ts_type:
        return _NODE_EMOJIS["type"]
    if "object" in ts_type:
        return _NODE_EMOJIS["object"]
    if ts_type.startswith("export"):
        return _NODE_EMOJIS["export"]
    return ""


# ----------------------------------------------------------------------
# traversal (clean)
# ----------------------------------------------------------------------


def _walk_fix(ts_node, rich_parent, info):
    """Recursive traversal adding child nodes with emoji labels."""
    nodes_cfg = info["nodes"]
    name_field = info["name_field"]

    for child in ts_node.children:
        n_type = child.type
        if n_type in nodes_cfg:
            style = nodes_cfg[n_type].keywords["style"]
            ident = child.child_by_field_name(name_field) if name_field else _first_identifier(child)
            label_text = ident.text.decode() if ident else "<anon>"
            label = nodes_cfg[n_type].func(label_text)
            emoji = _emoji_for_node_type(n_type)
            if emoji:
                label = f"{emoji} {label}"
            branch = rich_parent.add(Text(label, style=style) + _span(child))
            _walk_fix(child, branch, info)
        else:
            _walk_fix(child, rich_parent, info)
# ----------------------------------------------------------------------


def _walk(ts_node, rich_parent, info):
    nodes_cfg = info["nodes"]
    name_field = info["name_field"]

    for child in ts_node.children:
        t = child.type
        if t in nodes_cfg:
            style = nodes_cfg[t].keywords["style"]

            if name_field:
                ident = child.child_by_field_name(name_field)
            else:
                ident = _first_identifier(child)

            label_text = ident.text.decode() if ident else "<anon>"
            label = nodes_cfg[t].func(label_text)
            emoji = _emoji_for_node_type(t)
            if emoji:
                label = f"{emoji} {label}"
            branch = rich_parent.add(Text(label, style=style) + _span(child))
            _walk(child, branch, info)
        else:
            _walk(child, rich_parent, info)


def map_code_file(filepath):
    ext = Path(filepath).suffix
    info = LANGS.get(ext)
    if not info:
        return None

    code = Path(filepath).read_bytes()
    parser = parser_for(info["lang"])
    tree = parser.parse(code)

    file_emoji = _FILE_EMOJIS.get(ext, "📄")
    root_label = f"{file_emoji} {Path(filepath).name}"
    base = RichTree(Text(root_label, style="bold cyan"))

    if tree.root_node.has_error:
        base.add(Text("⚠️  syntax error", style="bold red"))

    _walk_fix(tree.root_node, base, info)
    return base


def make_code_map(directory: str, ignore_tests: bool = True) -> str:
    """Generate a Rich-rendered code map including directory hierarchy.

    Args:
        directory: Root directory to scan.
        ignore_tests: Whether to skip files with 'test' in the name.

    Returns:
        Plain-text rendering of the generated Rich tree (last 1k chars).
    """
    # Create root of tree representing starting directory
    base_tree = RichTree(Text(Path(directory).name, style="bold magenta"))

    # Cache to ensure we reuse RichTree nodes per directory path
    dir_nodes: dict[str, RichTree] = {Path(directory).resolve(): base_tree}  # key=abs path

    for root, dirs, files in os.walk(directory):
        # ignore dot-folders early
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        abs_root = Path(root).resolve()

        # Ensure current directory has a node; create if coming from parent
        if abs_root not in dir_nodes and abs_root != Path(directory).resolve():
            rel_parts = abs_root.relative_to(directory).parts
            parent_path = Path(directory).resolve()
            for part in rel_parts:  # walk down creating nodes as needed
                parent_node = dir_nodes[parent_path]
                current_path = parent_path / part
                if current_path not in dir_nodes:
                    dir_label = Text(part, style="bold magenta")
                    dir_node = parent_node.add(dir_label)
                    dir_nodes[current_path] = dir_node
                parent_path = current_path

        current_node = dir_nodes.get(abs_root, base_tree)

        for f in files:
            file_path = os.path.join(root, f)
            if should_ignore_path(file_path):
                continue
            if ignore_tests and "test" in f:
                continue
            try:
                file_tree = map_code_file(file_path)
                if file_tree is not None:
                    current_node.add(file_tree)
            except Exception:
                current_node.add(Text(f"[error reading {f}]", style="bold red"))

    # Render and return last 1000 characters
    buf = Console(record=True, width=120)
    buf.print(base_tree)
    return buf.export_text()[-1000:]
