# Code Puppy on Docker Sandboxes

Two [Docker Sandboxes](https://docs.docker.com/ai/sandboxes/) kits
(spec v3) that run the Code Puppy agent in an isolated sandbox with
governed network egress and proxy-managed API keys:

| Kit | Kind | What it does |
|---|---|---|
| `code-puppy/` | workload | Starts from the Docker `shell` template image, installs Code Puppy with `uvx code-puppy` (version-pinned, cache pre-warmed at image build), declares provider credentials and egress |
| `code-puppy-config/` | mixin | Injects Code Puppy's user configuration into `/home/agent/.code_puppy/`: `puppy.cfg`, MCP servers, extra models, global `AGENTS.md`, skills, agents, plugins |

## Prerequisites

- `sbx` v0.45 or later ([install](https://docs.docker.com/ai/sandboxes/install/));
  Docker with Buildx to build/publish kit images yourself.
- At least one stored provider key. Keys never enter the sandbox: the
  host proxy injects them on the provider's API domain only.

```console
sbx secret set anthropic    # or: openai, gemini, openrouter, meta
```

No API credits? Use Meta Muse through Code Puppy's bundled
`meta_oauth` core plugin instead — see [Meta Muse via OAuth](#meta-muse-via-oauth-no-api-credits).

## Wizard: bring your own setup

`wizard.py` (stdlib-only Python) turns your existing host setup into a
sandbox: it stores/approves the provider credential, exports your real
configuration secret-free via `code-puppy --setup export --sbx` (from
the `setup_cli` core plugin) into a personal mixin under
`sbx/.personal/` (git-ignored), creates the sandbox, and can
smoke-test it.

Run it with the project environment's Python — not `uv run`, which
re-syncs `.venv` from `uv.lock` and would remove a local editable
`code-puppy-core-plugins` install (needed for `--setup` until
`setup_cli` ships in a core-plugins release):

```console
# one-time, from the code_puppy repo root, with both repos cloned side by side:
uv pip install --python .venv\Scripts\python.exe -e ..\code_puppy_core_plugins

.venv\Scripts\python.exe sbx\wizard.py --name my-pup --provider meta --smoke
.venv\Scripts\python.exe sbx\wizard.py --provider anthropic --dry-run
.venv\Scripts\python.exe sbx\wizard.py --provider codex --sync-tokens
```

(On Linux/macOS use `.venv/bin/python` and `../code_puppy_core_plugins`.)

| Provider | How the sandbox authenticates |
|---|---|
| `meta`, `anthropic`, `openai`, `gemini`, `openrouter` | Proxy-managed key (`sbx secret` + binding); guest sees a sentinel |
| `copilot` | Device-flow login inside the sandbox (`/copilot-login`) |
| `claude-code`, `codex`, `grok` | Experimental: `--sync-tokens` copies the host token file in; host owns refresh |

## Run

Local, from this repository (your current directory becomes the
workspace):

```console
sbx run ./sbx/code-puppy --kit ./sbx/code-puppy-config
```

Cloud ([Docker Agentic Platform](https://agentic-platform.docker.com);
the first run needs interactive Docker Hub sign-in):

```console
sbx --cloud run ./sbx/code-puppy --kit ./sbx/code-puppy-config
```

Kit arguments (prefix matches the kit directory name):

```console
sbx run ./sbx/code-puppy --kit ./sbx/code-puppy-config \
  --kit-arg code-puppy.version=0.0.930 \
  --kit-arg code-puppy-config.puppy_name=Rex \
  --kit-arg code-puppy-config.owner_name="Ada" \
  --kit-arg code-puppy-config.model=<model-name>
```

Headless one-shot inside a running sandbox works as usual:
`code-puppy -p "your prompt"` (via `sbx exec` or an `sbx ssh` session).

## Meta Muse via OAuth (no API credits)

Code Puppy's bundled `meta_oauth` core plugin authenticates a Meta
account with an OAuth device-code flow and mints a Model API key — no
pay-as-you-go API account needed. The plugin reads `META_API_KEY`
first, which is exactly what this kit's `meta` credential supplies as
a proxy-managed sentinel: the real key stays in your host keychain and
is injected only on `api.meta.ai`. One-time host setup:

1. In a **local** Code Puppy session, run `/meta-auth` and approve the
   device code in your browser. Credentials land in
   `~/.code_puppy/meta_oauth.json`. (An existing Muse CLI login at
   `~/.config/muse/auth.json` also works as the source.)
2. Store the minted key with sbx (the value is never printed):

   ```powershell
   (Get-Content -Raw ~\.code_puppy\meta_oauth.json | ConvertFrom-Json).api_key |
     sbx secret set meta
   ```

   ```bash
   jq -r .api_key ~/.code_puppy/meta_oauth.json | sbx secret set meta
   ```

3. Approve the kit's use of it. `sbx` prompts interactively on first
   run, or pre-create the binding in `~/.config/sbx/credentials.yaml`
   (`%APPDATA%\sbx\credentials.yaml` on Windows):

   ```yaml
   bindings:
     meta:
       apiKey:
         domains: [api.meta.ai]
   ```

4. Create the sandbox with a Muse model as default. No
   `extra_models.json` seeding is needed: with `META_API_KEY` present,
   the plugin registers its `meta-*` models automatically (live
   catalog from `api.meta.ai`, with bundled fallbacks).

   ```console
   sbx run ./sbx/code-puppy --kit ./sbx/code-puppy-config \
     --kit-arg code-puppy-config.model=meta-muse-spark-1.2-contributor
   ```

Alternative: run `/meta-auth` *inside* the sandbox (it prints a
verification URL and code to open on the host; `auth.meta.com` egress
is pre-allowed). Simpler, but the minted key then lives in the guest
at `~/.code_puppy/meta_oauth.json` and is lost when the sandbox is
recreated — prefer the proxy-managed route above.

## First run: add a model (API-key providers)

Code Puppy ships with no bundled model catalog — just like a local
install, a new sandbox has no usable API-key-provider model until you
add one (Meta models above register automatically). With a provider
key bound, launch interactively once and run `/add_model`
(the catalog comes from models.dev), **or** seed `extra_models.json`
in your fork of the config mixin:

```json
{
  "anthropic-claude-haiku-5-5": {
    "type": "anthropic",
    "provider": "anthropic",
    "name": "claude-haiku-5-5",
    "context_length": 1000000,
    "supported_settings": ["temperature", "extended_thinking", "budget_tokens"]
  }
}
```

Then pass `--kit-arg code-puppy-config.model=anthropic-claude-haiku-5-5`
(or `/pin` it in-session). The `model` kit argument only selects among
models that exist in `extra_models.json`/OAuth catalogs; it does not
create one.

## What the config mixin injects

Under `/home/agent/.code_puppy/`:

- `puppy.cfg` — generated per sandbox from kit args (lifecycle file).
  Contains no API keys; those arrive as proxy-managed placeholders.
- `onboarding_complete` — skips first-run prompts/wizard, together with
  the pre-seeded `puppy_name`/`owner_name`.
- `mcp_servers.json`, `mcp_agent_bindings.json`, `extra_models.json` —
  seeded empty; replace with your own in your fork of the mixin.
- `AGENTS.md` — global (user-level) agent rules.
- `skills/sandbox-basics/` — a starter skill; add your own skill
  directories beside it.
- `agents/` — example JSON agent (`.example`, inert until renamed).
- `plugins/` — user plugins. **Executable code**: only ship reviewed
  plugins here.

Deliberately **not** injected: secrets (`secrets.json`, keyring data,
OAuth `*_models.json` token files), trust stores (`trusted_mcp.json`,
`trusted_plugins.json` — trust must be re-earned inside the sandbox),
and session state (autosaves, history).

To personalize: edit files in `code-puppy-config/files/home/agent/.code_puppy/`,
then recreate the sandbox. Running sandboxes do not pick up kit edits,
and `sbx kit add` cannot apply a mixin that carries static files.

## MCP servers

Two independent paths:

1. **In-sandbox servers** — declare them in the seeded
   `mcp_servers.json`, e.g. in your fork of the mixin:

   ```json
   {
     "mcp_servers": {
       "fetch": {
         "command": "uvx",
         "args": ["mcp-server-fetch"]
       }
     }
   }
   ```

   Stdio servers run inside the guest, so their egress must be allowed
   by the sandbox network policy too.
2. **Platform MCP gateway** — servers connected in the Agentic Platform
   web UI under **MCP** run outside the guest and need no in-sandbox
   configuration.

## Providers beyond the core four

The workload declares optional credentials for Anthropic, OpenAI,
Gemini, and OpenRouter. For another provider, add both blocks to
`code-puppy/code-puppy.yaml` (network egress and credential injection
are separate grants), then bind the key with `sbx secret set <service>`.
Example for Groq:

```yaml
# under network-policy@1 allow:
- api.groq.com:443
# new top-level capability entry:
- type: com.docker.sandbox/credential@1
  optional: true
  description: Groq API access
  config:
    service: groq
    phase: runtime
    apiKey:
      name: GROQ_API_KEY
      proxyManaged: true
      inject:
        - domain: api.groq.com
          header: Authorization
          format: "Bearer %s"
```

Header-auth API keys work with proxy injection. Non-header auth
(AWS Bedrock SigV4, Azure, OAuth subscription flows) does not and is
out of scope for these kits.

## Publish

```console
docker buildx build ./sbx/code-puppy \
  --file ./sbx/code-puppy/code-puppy.yaml \
  --tag docker.io/<NAMESPACE>/code-puppy:1.0.0 --push
docker buildx build ./sbx/code-puppy-config \
  --file ./sbx/code-puppy-config/code-puppy-config.yaml \
  --tag docker.io/<NAMESPACE>/code-puppy-config:1.0.0 --push

sbx run docker.io/<NAMESPACE>/code-puppy:1.0.0 \
  --kit docker.io/<NAMESPACE>/code-puppy-config:1.0.0
```

Once both kits are published they can be bundled into a single
reference with a [kit set](https://docs.docker.com/ai/sandboxes/customize/author/kit-sets/).

## Troubleshooting

- Blocked request? Check the effective decision, not just the kit:
  `sbx policy check network --sandbox <name> <host>`. Global/per-sandbox
  policy composes with kit rules.
- Config not updating? Recreate the sandbox; kit composition happens at
  creation.
- Playwright browser tools unavailable: browser binaries are not in the
  image. Compose a published Playwright v3 mixin alongside these kits
  if you need them.
- The `docker/sandbox-templates:shell` base tag floats. Pin it by
  digest in `code-puppy.dockerfile` for reproducible published images.
