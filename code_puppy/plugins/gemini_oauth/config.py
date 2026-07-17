"""Configuration for the Gemini OAuth (Code Assist) plugin.

The OAuth client_id/client_secret are the public, installed-application
values embedded in the open-source Gemini CLI
(github.com/google-gemini/gemini-cli). Google notes that the client secret
for installed apps is NOT treated as confidential:
  https://developers.google.com/identity/protocols/oauth2#installed

We still avoid committing the secret literal here (GitHub push protection
flags the ``GOCSPX-`` pattern). Instead the client credentials are read from
the environment at runtime, falling back to the Gemini CLI's public
client_id. Set these to enable automatic token refresh (see the plugin
README for the public values, or just re-run ``gemini`` to refresh):

    GEMINI_OAUTH_CLIENT_ID       (optional; defaults to the public CLI id)
    GEMINI_OAUTH_CLIENT_SECRET   (required for auto-refresh)
"""

import os

# Public installed-app client_id shipped by the Gemini CLI. Not a secret.
DEFAULT_CLIENT_ID = (
    "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
)

GEMINI_OAUTH_CONFIG = {
    "api_base_url": "https://cloudcode-pa.googleapis.com",
    "api_version": "v1internal",
    "client_id": os.environ.get("GEMINI_OAUTH_CLIENT_ID", DEFAULT_CLIENT_ID),
    "client_secret": os.environ.get("GEMINI_OAUTH_CLIENT_SECRET", ""),
    "token_uri": "https://oauth2.googleapis.com/token",
    # Paths (~ expanded at runtime)
    "credentials_path": "~/.gemini/oauth_creds.json",
    "projects_path": "~/.gemini/projects.json",
}
