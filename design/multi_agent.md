## 1. Overview and Goals
### What Are We Building?
A multi-agent system for Code Puppy where a "controller" agent (the main instance) can dispatch tasks to "sub-agents" (workers) for parallel or background 
execution. This turns your single CLI tool into a pack of digital pups, handling complex workflows like one refactoring code while another runs tests.

**Key Features:**
- **Dispatching:** Controller sends prompts/tasks to sub-agents synchronously or in the background.
- **Parallelism:** Run multiple sub-agents without blocking the controller.
- **Status Monitoring:** Tools to check progress, including last "chain of thought" from `share_your_reasoning`.
- **Management:** Kill, restart, or query sub-agents if they go rogue.
- **Visibility (Optional):** Spawn sub-agents in new terminal windows for live output watching (platform-specific hacks).
- **Model Pinning:** Allow users to specify and pin a particular AI model to a sub-agent for consistent behavior.
- **Extensibility:** Start local/simple, with hooks for future distributed modes (e.g., across machines).

**Why?** To make Code Puppy scale for big tasks without turning it into a bloated IDE. Your "open 10 terminals" vision evolves into auto-spawning child 
processes—easier, less manual.

**Assumptions:**
- All local to one machine for now (no network deps unless we add 'em later).
- Builds on existing tools: `invoke_agent`, `share_your_reasoning`, `state_management.py`.
- Testing: Everything gets `uv run pytest` love. Suppress noisy outputs (e.g., `npm run test -- --silent`).

**Non-Goals (YAGNI):** No full distributed system yet (e.g., no Socket.io unless we prototype it). No persistence beyond in-memory unless crashes become an issue.

---

## 2. Evolution of Ideas
We started with your brainstorm and iterated—here's the journey for context:

- **Your Initial Plan:**
  - Socket.io/FastAPI server: First puppy launches it, others connect and listen in "chatrooms" for tasks.
  - Synchronous invocation with parallelism: Build on `invoke_agent`, but make it async/background.
  - Status tool: `check_status(agent_id)` to peek at progress (e.g., last `share_your_reasoning`).

- **Refined Options:**
  - **Option 1: Simple Local Parallelism** – Threads/multiprocessing for background tasks, no server. Simple, but not distributed.
  - **Option 2: Distributed with Lightweight Messaging** – ZeroMQ for pub/sub across terminals. Cool for multi-terminal, but adds deps.
  - **Option 3: Child Process Mode (Our Winner)** – Fork sub-agents as child processes, track PIDs in memory, add management tools. Local, efficient, with 
optional visible terminals.

We landed on Option 3 as the core, with visible terminals via platform-specific hacks (your "holy shit hot" pick). It's a refined take on local parallelism: No 
network overhead, easy to implement, and extensible.

---

## 3. High-Level Architecture
### Components
- **Controller (Main Code Puppy Instance):** The alpha pup. Handles user input, dispatches tasks, monitors status. Lives in the primary terminal.
- **Sub-Agents (Workers):** Lightweight instances of Code Puppy launched in "child mode" (e.g., via CLI flag `--child-mode`). They execute a single prompt/task 
and exit.
- **Dispatcher:** New module (`process_dispatcher.py`, ~200 lines) that spawns/manages sub-agents using `subprocess.Popen`.
- **State Manager:** Extended `state_management.py` with an in-memory table for tracking agent states (PIDs, status, thoughts).
- **Tools Integration:**
  - New: `dispatch_to_agent(agent_name, prompt, background=True, visible=False, model=None)` – Spawns and tracks, optionally pinning a specific AI model.
  - New: `manage_agent_process(agent_id, action="status|kill|restart")` – Controls running agents.
  - Existing: `check_status(agent_id)` aliases to management's "status" for quick peeks.
  - Existing: Sub-agents use `share_your_reasoning` to emit thoughts, which controller captures via IPC.

### Data Flow
- **In-Memory State Table (Example Structure):**
  ```
  agent_states = {
      "agent_id_123": {
          "pid": 4567,  // Process ID for killing/polling
          "status": "running|idle|completed|errored|terminated",
          "last_reasoning": "Woof, refactoring now...",  // From share_your_reasoning
          "result": "Task done!" | None,  // Final output
          "start_time": timestamp,  // For timeouts
          "visible": True | False,  // If in a new terminal window
          "session_info": "Terminal tab ID or name"  // For visible mode
          "model": "gpt-4" | None,  // Pinned model if specified
      }
  }
  ```
  - Thread-safe with locks. Auto-polls PIDs (e.g., via `psutil`) to update status if processes exit unexpectedly.

- **IPC (Inter-Process Communication):** Use pipes from Popen (stdout/stderr) or `multiprocessing.Queue` for sub-agents to push updates (e.g., reasoning 
emissions) back to controller. Keeps it real-time without sockets.

### Visibility Mode (Option 3 Details)
- **Why Hot?** Pops new terminal windows for each sub-agent, making output visible and interactive—no hidden background magic.
- **Platform-Specific Hacks:**
  - **macOS (Detected: Darwin):** Use `osascript` to open Terminal.app tabs/windows. Command: `osascript -e 'tell application "Terminal" to do script "code_puppy 
--child-mode ..."'`.
  - **Linux:** `gnome-terminal -- bash -c 'code_puppy ...; exec bash'` or fallback to `xterm`.
  - **Windows:** `start cmd /c "code_puppy ... && pause"`.
- **OS Detection:** Use `platform.system()` or shell `uname` to choose dynamically.
- **Integration:** Flag in dispatch (`visible=True`). PID capture via echo/parsing or post-spawn `ps` polling. Windows stay open with "pause"; add "read" for Unix
to persist.

---

## 4. Key Flows
### Dispatch Flow
1. User/controller calls `dispatch_to_agent("refactor_pup", "Refactor main.py", background=True, visible=True)`.
2. Dispatcher generates unique `agent_id`, spawns Popen with child-mode command (visible hack if enabled).
3. Stores PID/status in state table, sets "running".
4. Sub-agent runs prompt synchronously in its process/window, emits thoughts via IPC.
5. Controller listens/updates table. If background, returns agent_id immediately.

### Status Check Flow
1. Call `check_status(agent_id)` or `manage_agent_process(agent_id, "status")`.
2. Pull from state table: Returns dict with status, last_reasoning, etc.
3. If visible: Add note like "Check your new Terminal window for live logs!"

### Management Flow
1. `manage_agent_process(agent_id, "kill")`: Graceful `os.kill(pid, SIGTERM)`, update status to "terminated".
2. "restart": Kill then re-dispatch with same prompt.
3. Timeouts: Dispatcher auto-kills after inactivity (e.g., 5min, configurable).

### Sub-Agent Execution Flow
1. Launched with `--child-mode --task-id=123 --prompt="..." --model="gpt-4"` (if specified).
2. Runs agent logic synchronously.
3. Uses `share_your_reasoning` to emit progress.
4. Exits with result (captured by controller via pipes).

---

## 5. Pros, Cons, and Tradeoffs
### Pros
- **Simplicity:** Local processes > network servers. Builds on existing sync `invoke_agent`.
- **Performance:** Parallel via multiprocessing, no GIL issues.
- **Visibility:** Option 3 makes debugging fun—watch pups in action!
- **Safety:** Management tool prevents runaway processes. In-memory table is lightweight.
- **Extensibility:** Add distributed later (e.g., ZeroMQ for multi-terminal).

### Cons
- **Resource Use:** Spawning full Code Puppy instances could be heavy—optimize child mode to be "lite" (skip CLI overhead).
- **Visibility Hacks:** Platform-dependent and brittle (e.g., no Terminal.app? Fails). Windows might spam dialogs.
- **State Fragility:** In-memory table lost on crash—add optional SQLite if needed.
- **Not Truly Distributed:** For your "10 terminals" dream, we'd need to layer on messaging (back to Option 2).

### Tradeoffs
- Background vs. Sync: Default to background for parallelism, but allow sync for simple cases.
- Visible vs. Hidden: Optional to avoid window spam—YAGNI for automated runs.
- Complexity: Keeps core small, but IPC/polling adds ~100 lines. Refactor if it bloats!

---

## 6. Implementation Notes and Best Practices
- **File Organization:** 
  - New: `process_dispatcher.py` (spawning logic).
  - Extend: `state_management.py` (table + polling).
  - Keep all <600 lines—split if needed (e.g., `visibility_handlers.py` for OS hacks).
- **Dependencies:** Minimal—`psutil` for PID polling (optional). No tmux/screen unless added as fallback.
- **Error Handling:** Timeouts, retries, graceful kills. Log everything (e.g., "Spawned Puppy #123 in new window!").
- **Testing:** Unit tests for dispatcher (mock Popen). Integration: Suppress outputs, run single tests if verbose needed.
- **Pedantic Principles:**
  - **SOLID/DRY:** Dispatcher does one thing (spawn/manage). Reuse existing tools.
  - **Zen:** Simple > complex—start with hidden mode, add visible as config.
  - **Code Quality:** Type hints everywhere. Run `ruff check --fix` and `ruff format .` before commits.
- **Future-Proofing:** Config flags for modes (e.g., `--distributed` to enable ZeroMQ). Git workflow: No force pushes!
