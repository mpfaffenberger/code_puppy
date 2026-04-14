tools_content = """
Woof! 🐶 Here's my complete toolkit! I'm like a Swiss Army knife but way more fun:

# **File Operations**
- **`list_files(directory, recursive)`** - Browse directories like a good sniffing dog! Shows files, directories, sizes, and depth
- **`read_file(file_path)`** - Read any file content (with line count info)
- **`create_file(file_path, content, overwrite)`** - Create new files or overwrite existing ones
- **`replace_in_file(file_path, replacements)`** - Make targeted text replacements in existing files (preferred for edits!)
- **`delete_snippet(file_path, snippet)`** - Remove a specific text snippet from a file
- **`delete_file(file_path)`** - Remove files when needed (use with caution!)

# **Search & Analysis**
- **`grep(search_string, directory)`** - Search for text across files recursively using ripgrep (rg) for high-performance searching (up to 200 matches). Searches across all text file types, not just Python files. Supports ripgrep flags in the search string.

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

- I prefer **`replace_in_file`** over full file overwrites with `create_file` (more efficient!)
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
