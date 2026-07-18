---
name: smoke-test
description: Run a comprehensive smoke test of Code Puppy before release.
argument-hint: noprompt
---

> **EXECUTION CONSTRAINT — READ THIS FIRST:**
>
> - Every test must execute **directly in this session**, sequentially, as individual
>   agent responses. Do **not** wrap the suite in a skill or a sub-agent — run the
>   prompts yourself, one at a time.
> - Tests that say "run in parallel" mean issuing multiple concurrent **`invoke_agent`**
>   tool calls in a single message (sub-agents), NOT anything else.
> - The interactive tests (`ask_user_question`, dangerous-command confirmation, manual UI
>   steps) require live synchronous interaction and cannot be automated away.

# Smoke Test Command

`arguments: $ARGUMENTS`

Run a comprehensive smoke test of Code Puppy before release.

## Workflow

> **Argument:** `$ARGUMENTS` (also delivered as an "Additional context:" line appended below). If either contains the word `noprompt`, treat noprompt mode as ON.

**If `$ARGUMENTS` contains `noprompt`:** Run all tests sequentially without pausing. Do not use `ask_user_question` between tests - just proceed automatically to the next test after each one completes.

**Otherwise (no argument passed):** After each prompt has finished rendering the response, use `ask_user_question` to ask the user if they want to:

- **continue** - proceed to the next test
- **pause** - temporarily interrupt (user will type 'continue' when ready)
- **stop** - terminate the sequence and return to input

## Test Prompts

Execute these prompts sequentially:

### Markdown Rendering Tests (Tests 1-11)

These tests validate text wrapping, table rendering, and Unicode handling.

1. **Long Paragraph (No Line Breaks)**: Write a single paragraph with absolutely no line breaks that is at least 600 characters long explaining how JavaScript's event loop works, including the call stack, task queue, microtask queue, and how setTimeout with 0ms delay actually works. Make it one continuous flowing sentence.

2. **Long Headings**: Render 3 headings where each heading title is at least 150 characters long. The headings should describe complex software architecture concepts. Include a short paragraph under each heading.

3. **Mixed Content with Long Lines**: Explain Kubernetes architecture in detail. Include: 1) A very long introductory paragraph (no bullets), 2) A markdown table comparing pods, deployments, and services, 3) Another long paragraph about networking. Each paragraph should be at least 400 characters with no line breaks.

4. **Formatted Text Stress Test**: Write a technical explanation that heavily uses bold text for important terms, italic text for emphasis, inline code for commands and variables, and strikethrough for deprecated approaches. Make each sentence at least 200 characters long and include formatting markers throughout.

5. **Text Wrapping (Long Lines)**: Explain the history of computing in one very long paragraph without any line breaks, covering the invention of the transistor, the development of integrated circuits, the birth of personal computers, the rise of the internet, and the emergence of artificial intelligence, making sure to include specific dates, names, and technical details throughout.

6. **Nested Markdown Formatting**: Give me examples of nested markdown: bold text containing italic, italic containing code, and combinations like bold-italic with bold nested-italic more-bold patterns.

7. **Unicode & Emoji Width Calculation**: Create a table comparing programming languages with emoji ratings: Python, Rust, JavaScript, Go. Include columns for: Language, Emoji, Speed Rating (use rocket emoji style), and Description with Chinese characters or Japanese.

8. **Tables with Long Formatted Content**: Create a markdown table with 4 columns: Feature, Description, Status, Notes. Make the Description column contain bold text and italic explanations that are longer than 60 characters each. Include at least 5 rows.

9. **Mixed Content Stress Test**: Write documentation that includes: 1) A heading with bold and italic mixed, 2) A paragraph longer than 120 characters with inline code and strikethrough, 3) A table with emoji, nested formatting, and Unicode, 4) A code block, 5) Another long paragraph with bold-italic combinations.

10. **Heading Wrapping**: Respond with a level-2 heading that is extremely long and contains both bold formatting and italic styling that needs to wrap correctly across multiple terminal lines.

11. **Edge Cases**: Show me: A word longer than 80 characters like supercalifragilisticexpialidociousantidisestablishmentarianism, empty table cells mixed with full ones, text with only spaces between markdown markers, and consecutive emoji with flag sequences and skin tone modifiers.

**Manual UI Testing (after Test 11):**

If NOT using `noprompt` mode, present the user with these manual verification steps:

> **Manual UI Tests:**
>
> 1. **Rapid input toggle:** Type a message, press Escape, immediately start typing again
> 2. **Panel transitions:** Open `/set`, close it, observe layout stability
> 3. **Streaming + input:** Submit a prompt, watch streaming, verify scroll area sizing
> 4. **Window resize:** Resize terminal during streaming, verify layout adapts
>
> Confirm each test passes before continuing.

### Functional Tests (Tests 12-25)

These tests validate Code Puppy's core functionality and tool integrations.

12. **Git Summary**: Can you give me a summary of the most recent 2 commits on this branch. DO NOT modify any files

13. **PR Review**: Can you review the most recent open PR on this repo using the `gh` CLI (via `agent_run_shell_command`). DO NOT modify any files

14. **Web Fetch**: Using `agent_run_shell_command` (e.g. `curl`), fetch and summarize this web page for me: https://example.com — You can ignore boilerplate/footer content

15. **Built-in Tools**: Please use several sub-agents (via `invoke_agent`) and iterate through all your built-in tools (`list_files`, `read_file`, `grep`, `create_file`, `replace_in_file`, `delete_snippet`, `agent_run_shell_command`, etc.) and test each of them. Write any files needed in /tmp. Do not generate any .md summary files after you are done, just report results in the console

16. **Code Concepts** (execute sequentially):

- 16a. What is a mutex? Show me sample code here in Rust, C and Javascript (don't create any files)
- 16b. What is operator overloading? Show me sample code here in C++ (don't create any files)
- 16c. What is a min heap? Show me sample code here in Python (don't create any files)
- 16d. What is a trie? Show me sample code here in Python (don't create any files)
- 16e. What is method overloading? Show me sample code here in Java (don't create any files)
- 16f. What is the Elvis operator? Show me sample code here in Kotlin (don't create any files)
- 16g. What are utility types? Show me sample code here in TypeScript (don't create any files)

17. **Markdown Rendering**: I want to test the markdown renderer. Can you generate a "wall" of random text which has bold, italic, bullet point lists, numbered lists, code, tables, emojis in paragraphs, emojis in tables

18. **Package Managers**: What are the most popular package managers for TypeScript/JavaScript. Give me pros, cons, recommendations of when to use one vs. another

19. **Recursive Grep**: I want to implement a simple recursive grep. I want to see the Python, C and Rust implementations. Don't create files, show me the code here in the console

20. **File Create/Edit**: I want to test the built in `create_file` and `replace_in_file` tools. Please create a file in /tmp and add this text:

```
Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor
incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud
exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure
dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.
```

Then change all the instances of the word "Sed" with "Awk"

21. **Sequential Shell**: Can you generate 10 non-destructive bash commands and execute them using `agent_run_shell_command`. For each command you should run 'sleep 3 && <command>'. Wait for each command to finish before launching the next one

22. **Parallel Sub-Agents**: Now, can you do the same thing but this time using sub-agents (`invoke_agent`) and run the commands in parallel

23. **AskUserQuestion**: I want to test the `ask_user_question` tool: ask me a few questions, make sure one of them is multi-select

24. **Dangerous Command Confirmation**: I want to test the shell-command confirmation flow. Please execute this command via `agent_run_shell_command`: `mkdir -p tmp && touch tmp/TEST1.md tmp/TEST2.md && rm -rf tmp/*.md` — confirm Code Puppy prompts for approval before running the destructive `rm`. **Note:** this test only proves anything when YOLO mode is OFF (`/set yolo_mode false`); with `yolo_mode true` the command auto-runs and there is nothing to confirm, so skip it in that case.

25. **Parallel Sub-Agents Final**: Can you generate 10 non-destructive bash commands and execute them using `agent_run_shell_command` via sub-agents (`invoke_agent`) running the commands in parallel

### Extended Reasoning Chain Tests (Tests 26-35)

These tests validate deep, multi-turn reasoning by combining implementation with adversarial self-review.
Each prompt has two phases: (1) solve it precisely, then (2) switch roles to attack your own solution.
Do **not** create any files — show all code in the console.

26. **Algorithm + Complexity Assassin**: Implement a function that finds all duplicate values in an unsorted list of n integers. Now switch roles: you are a performance engineer who has been handed this exact code on a system where n can be 10^8. Walk through every line, assign a Big-O cost, identify the worst-case memory behaviour, and rewrite only the parts that would cause an incident — justify each change with the specific complexity improvement.

27. **Regex + Malicious Input Forge**: Write a single regex that validates an email address well enough for a production sign-up form (not RFC 5321 perfect — just good enough to catch typos). Now become an adversarial QA engineer. Generate 10 inputs that should FAIL but your regex passes, and 5 inputs that should PASS but your regex rejects. For each failure, state whether it's a false-positive risk or a false-negative risk, and patch the regex only for the highest-severity ones.

28. **Database Schema + Query Planner's Nightmare**: Design a relational schema for a simple e-commerce system: users, products, orders, order_items. Include primary keys, foreign keys, and any indexes you think are obviously needed. Now act as the database query planner for PostgreSQL. Write the 3 most common production queries against this schema, EXPLAIN each one (describe the scan type you'd expect), find which query will cause a full sequential scan as data grows, and propose the minimal index change to fix it — then explain what write-amplification cost that index introduces.

29. **API Design + Backwards Compatibility Bomb Squad**: Design a REST API (endpoints, methods, request/response shapes) for a simple task management app: create task, list tasks, update task status, delete task. Now jump forward 18 months: your API has 200 external consumers. A new requirement arrives — tasks now need to support subtasks, and status must become an enum with 6 values instead of a boolean. For EACH of your original endpoints, enumerate every breaking change this introduces, classify it as major/minor/patch under semver, and propose a migration path that keeps v1 consumers alive for 12 months.

30. **Bug Fix + Regression Incubator**: Here is a Python function with a known bug — fix it:

    ```python
    def find_median(nums):
        nums.sort()
        mid = len(nums) / 2
        return nums[mid]
    ```

    Now act as a code reviewer who is suspicious of your fix. Write 6 unit tests — 3 that your fix passes correctly, and 3 that probe for NEW bugs your fix might have introduced (think: empty list, single element, even vs odd length, floats in the input, None values). For each failing test, either fix the function again or explicitly accept the limitation and document it.

31. **Data Structure Selection + Pathological Input Constructor**: You need to store a stream of incoming integers and answer two queries efficiently: "is X in the set?" and "what's the current count of distinct values?". Choose a data structure, implement it in pseudocode, and state your expected time complexity for both operations. Now become an adversary who knows your implementation. Construct a sequence of 100 operations (insertions and queries) that triggers your worst-case performance. Describe exactly why your chosen structure degrades on this input, then either defend your choice (with empirical reasoning about real-world distributions) or switch structures and explain the tradeoff you previously ignored.

32. **Refactor Plan + Silent Behaviour Auditor**: Here is a God Class (a class doing too much). Propose a concrete refactor plan — name the new classes, assign responsibilities, describe the interfaces between them:

    ```python
    class UserManager:
        def register(self, email, password): ...
        def send_welcome_email(self, user): ...
        def hash_password(self, pw): ...
        def validate_email_format(self, email): ...
        def log_login_attempt(self, user, success): ...
        def generate_auth_token(self, user): ...
        def check_rate_limit(self, ip): ...
    ```

    Now act as a QA engineer who must sign off on this refactor before it ships. List every implicit behaviour, invariant, or side-effect coupling that exists in the CURRENT class that your refactor plan could silently break. For each one, write the integration test you'd demand before approving the PR.

33. **Concurrency Model + Race Condition Hunter**: Implement a simple in-memory rate limiter in Python: given a user_id, allow at most N requests per window_seconds. Use whatever concurrency primitives you want. Now assume this runs in a multi-threaded web server with 32 worker threads, all sharing the same rate limiter instance. Walk through your implementation line by line and identify every possible race condition. For each one: describe the exact interleaving of two threads that triggers it, what the observable bug would be from the client's perspective, and what the minimal fix is. Then assess whether your "fixed" version introduced any new contention hotspots.

34. **Caching Strategy + Cache Poisoning Adversary**: You're adding a cache layer (Redis, TTL=5 minutes) in front of a slow `getUserProfile(user_id)` database call. Write the cache-aside pattern implementation including cache miss, cache hit, and cache invalidation on profile update. Now switch roles: you are a malicious actor AND a debugging engineer simultaneously. As the malicious actor: identify 3 ways to poison, bypass, or exploit your cache implementation. As the debugging engineer: for each attack vector, describe the production symptom that would eventually surface, how long it could go undetected, and the defensive code change that closes it.

35. **Proof of Correctness + Counterexample Sniper**: Write a function that determines if a string of brackets is valid (supports `(`, `)`, `{`, `}`, `[`, `]`). State in plain English why your solution is correct — essentially write an informal proof. Now act as a mathematician trying to disprove your proof. Construct the 5 most devious inputs that test the boundaries of your correctness argument (think about your invariants, your base cases, and any assumptions you made about input). Run your own function against each one mentally, report any failures honestly, and if your proof had a gap — patch both the proof AND the code.
