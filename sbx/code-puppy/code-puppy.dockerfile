FROM docker/sandbox-templates:shell

USER agent

# Skip the interactive onboarding wizard; the code-puppy-config mixin
# pre-seeds puppy.cfg and the onboarding_complete sentinel instead.
ENV CODE_PUPPY_SKIP_TUTORIAL=1

ARG CODE_PUPPY_VERSION=0.0.930

# Install uv if the template lacks it, pre-warm the uv cache with the
# pinned code-puppy release, and bake a launcher that always starts the
# agent through uvx at that exact version.
RUN set -eu; \
    if ! command -v uvx >/dev/null 2>&1; then \
        curl -LsSf https://astral.sh/uv/install.sh | sh; \
    fi; \
    export PATH="/home/agent/.local/bin:$PATH"; \
    uvx --from "code-puppy==${CODE_PUPPY_VERSION}" code-puppy --version; \
    mkdir -p /home/agent/.local/bin; \
    printf '%s\n' '#!/bin/sh' \
        "exec uvx --from \"code-puppy==${CODE_PUPPY_VERSION}\" code-puppy \"\$@\"" \
        > /home/agent/.local/bin/code-puppy-launch; \
    chmod 0755 /home/agent/.local/bin/code-puppy-launch

ENTRYPOINT ["/home/agent/.local/bin/code-puppy-launch"]
CMD []
