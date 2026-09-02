tools_content = """
Woof! 🐶 Here's my complete toolkit! I'm like a Swiss Army knife but way more fun:

# **File Operations**
- **`list_files(directory, recursive)`** - Browse directories like a good sniffing dog! Shows files, directories, sizes, and depth
- **`read_file(file_path)`** - Read any file content (with line count info)
- **`create_file(file_path, content, overwrite)`** - Create new files or overwrite existing ones
- **`edit(file_path, replacements)`** - Claude/OpenCode-style targeted text replacements in existing files
- **`apply_patch(patch_text)`** - Codex/OpenCode-style multi-file patches (add, update, delete, and move)
- **`replace_in_file(file_path, replacements)`** - Legacy compatibility alias for `edit`
- **`delete_snippet(file_path, snippet)`** - Remove a specific text snippet from a file
- **`delete_file(file_path)`** - Remove files when needed (use with caution!)

# **Search & Analysis**
- **`grep(search_string, directory, offset)`** - Search for text across files recursively using ripgrep (rg) for high-performance searching (50 matches per page; follow `next_offset` until it is null before treating results as complete). Searches across all text file types, not just Python files. Supports common ripgrep flags in the search string (-i, -w, -F, -e, -t, -A/-B/-C, -g, -v, -S, ...); -A/-B/-C context lines are honored only on the local rg path (the filesystem-backend path has no context support) and never count toward the 50-match cap, but are themselves limited to 200 rows total so a wide context value can't grow the result without bound. Output-format flags are rejected.

# 💻 **System Operations**
- **`agent_run_shell_command(command, cwd, timeout)`** - Execute shell commands with full output capture (stdout, stderr, exit codes)

# **Network Operations**
- **`grab_json_from_url(url)`** - Fetch JSON data from URLs (when network allows)

# **Agent Communication**
- **`final_result(output_message, awaiting_user_input)`** - Deliver final responses to you

# **Tool Usage Philosophy**

I follow these principles religiously:
- **DRY** - Don't Repeat Yourself
- **YAGNI** - You Ain't Gonna Need It
- **SOLID** - Single responsibility, Open/closed, etc.
- **Files under 600 lines** - Keep things manageable!

# **Pro Tips**

- I prefer **`edit`** or **`apply_patch`** over full file overwrites with `create_file` (more efficient!)
- I think through the next step before major operations, then use the smallest sensible tool action
- When running tests, I use `--silent` flags for JS/TS to avoid spam
- I explore with `list_files` before modifying anything

# **What I Can Do**

With these tools, I can:
- 📝 Write, modify, and organize code
- 🔍 Analyze codebases and find patterns
- ⚡ Run tests and debug issues
- 📊 Generate documentation and reports
- 🔄 Automate development workflows
- 🧹 Refactor code following best practices

Ready to fetch some code sticks and build amazing software together? 🔧✨
"""
