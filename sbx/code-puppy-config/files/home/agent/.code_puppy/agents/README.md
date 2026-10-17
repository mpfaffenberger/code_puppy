# User agents

Drop JSON agent definitions (`*.json`) in this directory on the host
copy of the `code-puppy-config` kit and recreate the sandbox to load
them. Required fields: `name`, `description`, `system_prompt`, `tools`
(see `example-agent.json.example`; rename it to `.json` to enable).

Project agents in the workspace (`.code_puppy/agents/`) work unchanged
and do not belong in this kit.
