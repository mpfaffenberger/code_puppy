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

# Cache parsers so we don’t re-create them file-after-file
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

    root_label = Path(filepath).name
    base = RichTree(Text(root_label, style="bold cyan"))

    if tree.root_node.has_error:
        base.add(Text("⚠️  syntax error", style="bold red"))

    _walk(tree.root_node, base, info)
    return base


def make_code_map(directory: str, ignore_tests: bool = True) -> str:
    base_tree = RichTree(Text(Path(directory).name, style="bold magenta"))

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if (
                should_ignore_path(os.path.join(root, f))
                or ignore_tests
                and "test" in f
            ):
                continue
            try:
                file_tree = map_code_file(os.path.join(root, f))
                if file_tree is not None:
                    base_tree.add(file_tree)
            except Exception:
                base_tree.add(Text(f"[error reading {f}]", style="bold red"))

    buf = Console(record=True, width=120)
    buf.print(base_tree)
    return buf.export_text()[-1000:]
