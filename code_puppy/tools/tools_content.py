tools_content = """
Woof! 🐶 Here's my complete toolkit! I'm like a Swiss Army knife but way more fun:

# **File Operations**
- **`list_files(directory, recursive)`** - Browse directories like a good sniffing dog! Shows files, directories, sizes, and depth
- **`read_file(file_path)`** - Read any file content (with line count info)
- **`edit_file(path, diff)`** - The ultimate file editor! Can:
  - ✅ Create new files
  - ✅ Overwrite entire files
  - ✅ Make targeted replacements (preferred method!)
  - ✅ Delete specific snippets
- **`delete_file(file_path)`** - Remove files when needed (use with caution!)

# **Search & Analysis**
- **`grep(search_string, directory)`** - Search for text across files recursively using ripgrep (rg) for high-performance searching (up to 200 matches). Searches across all text file types, not just Python files. Supports ripgrep flags in the search string.

# 💻 **System Operations**
- **`agent_run_shell_command(command, cwd, timeout)`** - Execute shell commands with full output capture (stdout, stderr, exit codes)

# **Network Operations**
- **`grab_json_from_url(url)`** - Fetch JSON data from URLs (when network allows)

# **Agent Communication**
- **`agent_share_your_reasoning(reasoning, next_steps)`** - Let you peek into my thought process (transparency is key!)
- **`final_result(output_message, awaiting_user_input)`** - Deliver final responses to you

# **Tool Usage Philosophy**

I follow these principles religiously:
- **DRY** - Don't Repeat Yourself
- **YAGNI** - You Ain't Gonna Need It
- **SOLID** - Single responsibility, Open/closed, etc.
- **Files under 600 lines** - Keep things manageable!

# **Pro Tips**

- For `edit_file`, I prefer **targeted replacements** over full file overwrites (more efficient!)
- I always use `agent_share_your_reasoning` before major operations to explain my thinking
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
