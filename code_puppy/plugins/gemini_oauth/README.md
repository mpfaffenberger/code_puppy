# Gemini OAuth (Google Code Assist) Plugin

Use Google's **Gemini** models inside Code Puppy through the **local
Gemini CLI's** existing OAuth login — **no API key required**.

> **Note on "Antigravity":** Google has been rebranding its Gemini CLI
> tooling as *Antigravity*. Whichever name your local install uses, both
> write their OAuth credentials to the same `~/.gemini/` location, so this
> plugin works with either.

## How it works

The [Gemini CLI](https://github.com/google-gemini/gemini-cli) stores an
OAuth token at `~/.gemini/oauth_creds.json` after you sign in. This plugin
reuses that token to call the **Code Assist API**
(`https://cloudcode-pa.googleapis.com`) — the same endpoint the CLI uses —
so you get Gemini access on your existing (often free) Code Assist tier
without pasting an API key into Code Puppy.

It provides the three symbols `model_factory.py` expects for the
`gemini_oauth` model type:

| Symbol | Purpose |
|--------|---------|
| `GEMINI_OAUTH_CONFIG` | Code Assist base URL + API version |
| `get_valid_access_token()` | Reads `~/.gemini/oauth_creds.json`, auto-refreshes when expired |
| `get_project_id()` | Discovers your managed GCP project via `loadCodeAssist`, caches it |

Tokens are refreshed automatically using the refresh token the Gemini CLI
already stored; refreshed credentials are written back with `chmod 600`.

## Prerequisites

1. Install and sign in to the Gemini CLI at least once so
   `~/.gemini/oauth_creds.json` exists:
   ```bash
   npm install -g @google/gemini-cli   # or: brew install gemini-cli
   gemini                              # complete the browser sign-in
   ```

2. **(Optional) Enable automatic token refresh.** Refreshing an expired token
   requires the OAuth client credentials. These are the *public,
   installed-application* values shipped in the open-source Gemini CLI. We do
   **not** hardcode or paste the secret in this repo (secret scanners flag the
   `GOCSPX-` pattern regardless of context). Instead, extract them from your
   own installed Gemini CLI and export them once:

   ```bash
   # Locate the CLI's OAuth module and read the two constants from it:
   grep -rhoE 'OAUTH_CLIENT_(ID|SECRET) *= *[^,]+' \
     "$(dirname "$(readlink -f "$(command -v gemini)")")/.." 2>/dev/null

   # Then export what you find (the ID ends in .apps.googleusercontent.com,
   # the SECRET starts with GOCSPX-):
   export GEMINI_OAUTH_CLIENT_ID="<...>.apps.googleusercontent.com"
   export GEMINI_OAUTH_CLIENT_SECRET="<the GOCSPX-... value>"
   ```

   Without these, the plugin still works while your token is valid; when it
   expires, just re-run `gemini` to refresh `~/.gemini/oauth_creds.json`.

## Setup

Add one or more Gemini models to `~/.code_puppy/extra_models.json`:

```json
{
  "antigravity-flash": {
    "type": "gemini_oauth",
    "name": "gemini-2.5-flash",
    "description": "Gemini 2.5 Flash via Code Assist OAuth",
    "context_length": 1000000
  },
  "antigravity-pro": {
    "type": "gemini_oauth",
    "name": "gemini-2.5-pro",
    "description": "Gemini 2.5 Pro via Code Assist OAuth",
    "context_length": 1000000
  }
}
```

Then, inside Code Puppy:

```text
/model antigravity-flash
```

That's it — the first request discovers your Code Assist project ID and
caches it to `~/.gemini/code_assist_project.json`.

## Troubleshooting

- **`credentials not found`** — run `gemini` once to sign in.
- **`PERMISSION_DENIED` / `Gemini for Google Cloud API has not been used`** —
  your account isn't onboarded to Code Assist; open the Gemini CLI once and
  send a message so Google provisions the managed project.
- **`RESOURCE_EXHAUSTED` (429)** — you hit the Code Assist rate limit for the
  free tier; wait for the reset window shown in the error, or switch models.

## Security

- The OAuth `client_id` / `client_secret` in `config.py` are the **public,
  installed-application** values embedded in the open-source Gemini CLI.
  Per Google's own docs, the secret for installed apps
  [is not treated as confidential](https://developers.google.com/identity/protocols/oauth2#installed).
- Access and refresh tokens are read from and written to `~/.gemini/` only,
  with `0600` permissions. They are never logged.
