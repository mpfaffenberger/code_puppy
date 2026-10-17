# Overlay-only mixin: the files/ tree mirrors the sandbox filesystem, so
# files/home/agent/.code_puppy/... lands in /home/agent/.code_puppy/...
# Static seeds only -- puppy.cfg is generated per-sandbox from kit args by
# the lifecycle capability in code-puppy-config.yaml, and no file here may
# contain a secret.
FROM scratch
COPY --chown=1000:1000 files/ /
