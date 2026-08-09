"""Consolidated catalog-namespace health checks (PUP-480).

Every extracted i18n namespace (cli.*, cmd.*, cfg.*, mcp.wizard.*,
oauth.*, cmd.session.*) must:

* resolve to real source text (no echo-back of the key),
* pseudolocalize (any raw string that skipped the catalog would come
  back un-bracketed),
* never leave an un-substituted ``{field}`` placeholder behind.

These checks used to be duplicated verbatim in each per-module i18n
file; they are identical apart from the key-prefix filter and the
"namespace is populated" floor. The per-module files keep their concrete
key/interpolation contracts, this module owns the generic sweep.
"""

import re

import pytest

from code_puppy.i18n import catalog, pseudo, translate

_PLACEHOLDER = re.compile(r"\{(\w+)\}")

# namespace id -> (prefix filter, minimum key count)
_NAMESPACES = {
    "cli": (("cli.",), 50),
    "cmd": (("cmd.",), 32),
    "cfg": (("cfg.",), 20),
    "mcp.wizard": (("mcp.wizard.",), 39),
    "oauth": (
        (
            "oauth.server.",
            "oauth.pasteback.",
            "oauth.state_mismatch",
            "oauth.callback.",
            "oauth.browser.",
            "oauth.auth.",
            "oauth.reauth.",
            "oauth.cmd.",
            "oauth.model.",
            "oauth.claude.",
        ),
        48,
    ),
    "session": (
        (
            "cmd.session.",
            "cmd.clear.",
            "cmd.compact.",
            "cmd.truncate.",
            "cmd.quick_resume.",
            "cmd.dump_context.",
            "cmd.load_context.",
        ),
        35,
    ),
}

_PREFIXES = [prefixes for prefixes, _ in _NAMESPACES.values()]


def _keys(prefixes):
    src = catalog.load_catalog("en-US")
    return [k for k in src if any(k.startswith(p) for p in prefixes)]


@pytest.mark.parametrize(
    "namespace_id",
    list(_NAMESPACES),
    ids=list(_NAMESPACES),
)
def test_namespace_is_populated(namespace_id):
    prefixes, floor = _NAMESPACES[namespace_id]
    assert len(_keys(prefixes)) >= floor


@pytest.mark.parametrize("prefixes", _PREFIXES, ids=list(_NAMESPACES))
def test_every_key_resolves_to_real_text(prefixes):
    """No key echoes back (missing) or resolves empty in the source."""
    translate.set_locale("en-US")
    offenders = [
        k for k in _keys(prefixes) if not translate.t(k) or translate.t(k) == k
    ]
    assert not offenders, f"{prefixes} keys not resolving: {offenders}"


@pytest.mark.parametrize("prefixes", _PREFIXES, ids=list(_NAMESPACES))
def test_every_key_pseudolocalizes(prefixes):
    """In the pseudolocale every string must be bracketed (\u27e6 \u2026 \u27e7)."""
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    offenders = [k for k in _keys(prefixes) if not translate.t(k).startswith("\u27e6")]
    assert not offenders, f"{prefixes} keys not pseudolocalized: {offenders}"


@pytest.mark.parametrize("prefixes", _PREFIXES, ids=list(_NAMESPACES))
def test_no_leftover_placeholder_for_supplied_params(prefixes):
    """Supplying every placeholder must leave no ``{field}`` behind."""
    translate.set_locale("en-US")
    src = catalog.load_catalog("en-US")
    for key in _keys(prefixes):
        entry = src[key]
        text = entry if isinstance(entry, str) else entry.get("other", "")
        # Skip entries with intentional double-brace escapes like {{color_type}}:
        # those render to literal {color_type} — correct display text, not an
        # un-substituted slot.
        if "{{" in text:
            continue
        params = {name: "X" for name in _PLACEHOLDER.findall(text)}
        rendered = translate.t(key, **params)
        assert "{" not in rendered.replace("{{", "").replace("}}", ""), (
            f"{key} left an un-substituted placeholder: {rendered!r}"
        )
