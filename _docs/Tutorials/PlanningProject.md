# Tutorial: Planning a Multi-File Project

## What You'll Achieve

In this tutorial, you'll use Code Puppy's **Planning Agent** to tackle a project that spans multiple files — a REST API with separate modules for routes, data models, and configuration. You'll learn how to:

- Switch to the Planning Agent for strategic thinking
- Get a structured execution plan before writing any code
- Execute the plan step by step with Code Puppy
- Coordinate between planning and implementation

By the end, you'll have a multi-file project built from a well-organized roadmap — and a workflow you can reuse for any complex task.

## Before You Begin

**Time needed:** ~20 minutes

**You'll need:**
- Code Puppy installed and working (see [Installation](../Getting-Started/Installation))
- At least one AI model configured (see [Configuration](../Getting-Started/Configuration))
- A folder where you're comfortable creating files

**You should already know:**
- How to launch Code Puppy and interact with it — covered in [Your First Coding Task](FirstCodingTask)
- How to use slash commands like `/agent` and `/help`

## The Scenario

You want to build a simple bookmark manager API — a REST service where you can save, list, tag, and search your bookmarks. This is too complex for a single file, so you need:

- A data model for bookmarks
- API routes for CRUD operations
- A configuration module
- A main entry point
- Tests

Instead of diving straight into code, you'll start with a plan.

## Step 1: Set Up Your Workspace

Open your terminal and create a project directory:

```bash
mkdir bookmark-api && cd bookmark-api
```

Launch Code Puppy:

```bash
uvx code-puppy -i
```

**What happened:** You're in Code Puppy's interactive mode, ready to start planning.

## Step 2: Switch to the Planning Agent

The default Code-Puppy agent is great for writing code, but for strategic planning you want the **Planning Agent**. Switch to it:

```
/agent planning-agent
```

You should see a confirmation that you've switched:

```
Switched to Planning Agent 📋
```

> [!TIP]
> You can also use the shorthand `/a planning-agent`, or just type `/agent` to open the interactive agent picker and select it from the list.

**What happened:** Code Puppy is now in planning mode. It will analyze your request, explore your project, and produce a structured roadmap — without writing any code yet.

## Step 3: Describe Your Project

Now give the Planning Agent a clear description of what you want to build:

```
I want to build a bookmark manager REST API using Python and FastAPI. It should support:
- Adding a bookmark with a URL, title, and optional tags
- Listing all bookmarks, with optional filtering by tag
- Deleting a bookmark by ID
- Searching bookmarks by title or URL
- Storing data in a local JSON file for simplicity

Please create a plan for this project.
```

The Planning Agent will:
1. Explore your current directory to understand the starting point
2. Break down the request into specific tasks
3. Identify dependencies between tasks
4. Recommend which order to build things

You'll get back a structured plan that looks something like this:

```
🎯 OBJECTIVE: Build a bookmark manager REST API with FastAPI

📊 PROJECT ANALYSIS:
- Project type: REST API
- Tech stack: Python, FastAPI, Pydantic
- Current state: Empty directory, starting from scratch

📋 EXECUTION PLAN:

Phase 1: Foundation
- [ ] Task 1.1: Create project structure and configuration
      Files: config.py, requirements.txt
- [ ] Task 1.2: Define data models
      Files: models.py

Phase 2: Core Implementation
- [ ] Task 2.1: Implement JSON storage layer
      Files: storage.py
- [ ] Task 2.2: Create API routes
      Files: routes.py
- [ ] Task 2.3: Wire up the main application
      Files: main.py

Phase 3: Testing & Polish
- [ ] Task 3.1: Write tests
      Files: test_api.py
- [ ] Task 3.2: Create README with usage examples
      Files: README.md

⚠️ RISKS & CONSIDERATIONS:
- JSON file storage won't handle concurrent writes
- Consider adding input validation for URLs

🚀 NEXT STEPS:
Say "execute plan" to start building!
```

> [!NOTE]
> The exact plan will vary based on your AI model and the Planning Agent's analysis. The key elements — phased tasks, file lists, dependencies, and risks — will always be present.

**What happened:** You now have a clear roadmap before writing a single line of code. The plan shows what to build, in what order, and what to watch out for.

## Step 4: Review and Refine the Plan

This is your chance to adjust before implementation begins. If you want changes, just ask:

```
Can you also add a task for adding pagination to the list endpoint? And let's skip the README for now — I'll add that later.
```

The Planning Agent will update the plan to incorporate your feedback.

> [!TIP]
> Take a moment to really look at the plan. Are the tasks in the right order? Are any missing? It's much cheaper to change a plan than to rewrite code.

**What happened:** The plan was revised based on your input. The Planning Agent adjusts without losing the overall structure.

## Step 5: Start Executing the Plan

Once you're happy with the plan, tell the Planning Agent to proceed:

```
Looks good — let's do it!
```

The Planning Agent will begin coordinating implementation, working through the plan phase by phase. It may delegate tasks to the default Code-Puppy agent or other specialized agents.

Alternatively, you can switch back to the Code-Puppy agent and execute the plan yourself, one task at a time:

```
/agent code-puppy
```

Then reference the plan as you go:

```
Let's start with Phase 1, Task 1.1 from the plan. Create config.py with settings for the API (host, port, storage file path) and a requirements.txt with fastapi and uvicorn.
```

**What happened:** You've moved from planning to building. Whether the Planning Agent coordinates execution or you drive it manually, the plan keeps you on track.

## Step 6: Build Phase by Phase

Work through each task in the plan. Here's what a typical flow looks like:

**Task 1.2 — Define data models:**
```
Create models.py with a Pydantic model for Bookmark. Fields: id (auto-generated UUID), url (required), title (required), tags (optional list of strings), created_at (auto-set timestamp).
```

**Task 2.1 — Implement storage:**
```
Create storage.py with functions to load and save bookmarks from a JSON file. Include functions for add, list, delete, and search.
```

**Task 2.2 — Create routes:**
```
Create routes.py with FastAPI routes for: POST /bookmarks, GET /bookmarks (with optional tag filter), DELETE /bookmarks/{id}, and GET /bookmarks/search?q=query
```

> [!TIP]
> You don't have to type out every detail for each task — the plan already provides context. Short, clear prompts referencing the plan work great.

**What happened:** By following the plan's phases, you're building the project in a logical order — models before routes, storage before API endpoints.

## Step 7: Check Your Progress

At any point, use `/ls` to see what's been created:

```
/ls
```

You should see your project structure taking shape:

```
config.py
main.py
models.py
requirements.txt
routes.py
storage.py
```

You can also switch back to the Planning Agent to ask about remaining work:

```
/agent planning-agent
```

```
What tasks from the plan are still remaining?
```

**What happened:** You can move between planning and implementation at any time. The Planning Agent remembers the conversation within its session.

## Step 8: Test and Verify

Once all the core tasks are done, switch back to Code-Puppy and run your API:

```
/agent code-puppy
```

```
Install the requirements and start the API server so I can test it.
```

Code Puppy will run the necessary commands. You should see something like:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

Then ask Code Puppy to test it:

```
Use curl to add a bookmark for https://example.com with title "Example" and tags ["test", "demo"], then list all bookmarks.
```

**What happened:** Your multi-file project is running and functional, built from a structured plan rather than ad-hoc coding.

## Final Result

You've built a complete multi-file REST API with:
- ✅ A structured plan created before any code was written
- ✅ Separate modules for models, storage, routes, and configuration
- ✅ CRUD operations for bookmarks with tag filtering and search
- ✅ A clear build order that avoided dependency issues

## What You Learned

- **Plan before you build**: The Planning Agent creates structured roadmaps that break complex projects into manageable phases
- **Switch agents for different tasks**: Use `/agent planning-agent` for strategy, `/agent code-puppy` for implementation
- **Plans are flexible**: You can refine the plan before executing, and check progress at any time
- **Phase-based building**: Working through tasks in dependency order avoids backtracking and rework
- **Agent sessions are independent**: Each agent keeps its own conversation history, so you can switch back and forth

## Going Further: The Pack Leader

For even larger projects, Code Puppy includes the **Pack Leader** agent (`/agent pack-leader`), which orchestrates multiple specialized agents working in parallel — with automated code review and quality checks before any work is merged. This is ideal for team-sized projects where you want:

- Parallel task execution across isolated workspaces
- Automated code review (Shepherd agent) and QA (Watchdog agent)
- Issue tracking and dependency management

Explore it when you're ready to tackle truly complex, multi-component projects.

## Next Steps

- [How to Switch and Use Agents](../Guides/UseAgents) — Learn about all available agents
- [How to Create Custom Agents](../Guides/CreateCustomAgents) — Build agents tailored to your workflow
- [How to Manage Sessions](../Guides/ManageSessions) — Save and resume your planning sessions
- [Slash Commands Reference](../Reference/Commands) — The complete list of commands
