# 🐶 How to Use Code Puppy in cerebras most effective 

### 1. First Startup & The "Enter" Quirk
After installation, run `code-puppy` in your terminal.
1.  **Name your agent:** Enter any name (e.g., `PuppyBot`).
2.  **The Blank Enter:** Once the tool starts, **hit `Enter` one time** on the blank line.
    *   *Note: The tool often fails to recognize commands like `/set` until this first blank enter is registered.*

### 2. Configuration & Model Pinning
Copy and paste these commands one by one to set up your keys, authentication, and model bindings.

```text
/set cerebras_api_key = "YOUR_API_KEY_HERE"
/set yolo_mode = true

/claude-code-auth 
```
*(Follow the browser instructions to authenticate Claude)*

```text
/model Cerebras-GLM-4.6
/pin_model planning-agent claude-code-claude-opus-4-1-20250805
/pin_model code-reviewer claude-code-claude-haiku-4-5-20251001
/pin_model python-reviewer claude-code-claude-haiku-4-5-20251001
```
*(Note: You can pin different reviewers depending on your language needs, e.g., java-reviewer)*

### 3. Restart
**Close and restart** Code Puppy. This ensures all configurations and pinned models are loaded correctly.

### 4. Running the Planning Agent
To start a task, always switch to the planning agent first. It will plan, verify with you, and then drive the other agents.

```text
/agent planning-agent 
```

### 5. Prompting Strategy
Copy and paste the prompt below to ensure the agent implements features, reviews them automatically, and avoids running the backend prematurely.

```markdown
Your task is to implement "REQUIREMENTS.MD".

For that use code-puppy to implement. Use python-reviewer to verify the implementation. If there are errors give the feedback to code_puppy to fix. Repeat until the reviewer has no more "urgent" fixes, maximum 3 times.

During development never execute the backend. Only verify with compiling!
