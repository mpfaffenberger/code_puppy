import os
import ast
from typing import List, Tuple
from rich.tree import Tree
from rich.text import Text
from pathlib import Path
import pathspec


def summarize_node(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        return f"class {node.name}"
    if isinstance(node, ast.FunctionDef):
        return f"def {node.name}()"
    return ""


def get_docstring(node: ast.AST) -> str:
    doc = ast.get_docstring(node)
    if doc:
        lines = doc.strip().split("\n")
        return lines[0] if lines else doc.strip()
    return ""


def map_python_file(file_path: str, show_doc: bool = True) -> Tree:
    tree = Tree(Text(file_path, style="bold cyan"))
    with open(file_path, "r", encoding="utf-8") as f:
        root = ast.parse(f.read(), filename=file_path)
    for node in root.body:
        summary = summarize_node(node)
        if summary:
            t = Tree(summary)
            if show_doc:
                doc = get_docstring(node)
                if doc:
                    t.add(Text(f'"{doc}"', style="dim"))
            # Add inner functions
            if hasattr(node, 'body'):
                for subnode in getattr(node, 'body'):
                    subsum = summarize_node(subnode)
                    if subsum:
                        sub_t = Tree(subsum)
                        doc2 = get_docstring(subnode)
                        if doc2:
                            sub_t.add(Text(f'"{doc2}"', style="dim"))
                        t.add(sub_t)
            tree.add(t)
    return tree


def load_gitignore(directory: str):
    gitignore_file = os.path.join(directory, '.gitignore')
    if os.path.exists(gitignore_file):
        with open(gitignore_file, 'r') as f:
            spec = pathspec.PathSpec.from_lines('gitwildmatch', f)
        return spec
    else:
        return pathspec.PathSpec.from_lines('gitwildmatch', [])

def make_code_map(directory: str, show_doc: bool = True) -> Tree:
    """
    Recursively build a Tree displaying the code structure of all .py files in a directory,
    ignoring files listed in .gitignore if present.
    """
    base_tree = Tree(Text(directory, style="bold magenta"))

    spec = load_gitignore(directory)
    abs_directory = os.path.abspath(directory)

    for root, dirs, files in os.walk(directory):
        rel_root = os.path.relpath(root, abs_directory)
        # Remove ignored directories in-place for os.walk to not descend
        dirs[:] = [d for d in dirs if not spec.match_file(os.path.normpath(os.path.join(rel_root, d)))]
        for fname in files:
            rel_file = os.path.normpath(os.path.join(rel_root, fname))
            if fname.endswith('.py') and not fname.startswith("__"):
                if not spec.match_file(rel_file):
                    fpath = os.path.join(root, fname)
                    try:
                        file_tree = map_python_file(fpath, show_doc=show_doc)
                        base_tree.add(file_tree)
                    except Exception as e:
                        err = Tree(Text(f"[error reading {fname}: {e}]", style="bold red"))
                        base_tree.add(err)
    return base_tree
