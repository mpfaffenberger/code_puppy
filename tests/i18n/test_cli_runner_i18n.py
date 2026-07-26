"""i18n coverage for the CLI runner extraction (PUP-480).

A full pseudolocalization run of ``cli_runner.main()`` is impractical (it is a
large async entry point that owns the terminal), so instead we lock in the
``cli.*`` catalog namespace the runner depends on: every key must resolve to
real source text, pseudolocalize, and preserve its placeholders.
"""

import re

import pytest

from code_puppy.i18n import catalog, pseudo, translate

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


@pytest.fixture(autouse=True)
def _reset_locale():
    translate.get_translator().set_locale("en-US")
    catalog.reset()
    yield
    translate.get_translator().set_locale("en-US")
    catalog.reset()


def _cli_keys():
    src = catalog.load_catalog("en-US")
    return [k for k in src if k.startswith("cli.")]


def test_cli_namespace_is_populated():
    # The cli_runner extraction should have added a substantial namespace.
    assert len(_cli_keys()) >= 50


def test_every_cli_key_resolves_to_real_text():
    """No cli.* key echoes back (missing) or resolves empty in the source."""
    translate.set_locale("en-US")
    offenders = []
    for key in _cli_keys():
        text = translate.t(key)
        if not text or text == key:
            offenders.append(key)
    assert not offenders, f"cli.* keys not resolving to source text: {offenders}"


def test_every_cli_key_pseudolocalizes():
    """In the pseudolocale every cli.* string must be bracketed (⟦ … ⟧).

    A raw string that skipped the catalog would come back un-bracketed; this
    proves the keys actually flow through the translation runtime.
    """
    translate.set_locale(pseudo.PSEUDO_LOCALE)
    offenders = [k for k in _cli_keys() if not translate.t(k).startswith("\u27e6")]
    assert not offenders, f"cli.* keys not pseudolocalized: {offenders}"


def test_parametrized_cli_keys_interpolate():
    """Representative parametrized keys interpolate their named fields."""
    translate.set_locale("en-US")
    assert translate.t("cli.model.using", model="gpt-5").endswith("gpt-5")
    assert "demo" in translate.t(
        "cli.resume.resumed", messages=3, tokens=1200, session="demo"
    )
    assert "boom" in translate.t("cli.headless.error", error="boom")
    assert "42" in translate.t("cli.autosave.loaded", messages=42, tokens=999)
    assert "my.pkl" in translate.t("cli.autosave.loaded_path", path="my.pkl")


def test_no_leftover_placeholder_for_supplied_params():
    """Supplying every placeholder must leave no ``{field}`` behind."""
    translate.set_locale("en-US")
    src = catalog.load_catalog("en-US")
    for key in _cli_keys():
        entry = src[key]
        text = entry if isinstance(entry, str) else entry.get("other", "")
        params = {name: "X" for name in _PLACEHOLDER.findall(text)}
        rendered = translate.t(key, **params)
        assert "{" not in rendered.replace("{{", "").replace("}}", ""), (
            f"{key} left an un-substituted placeholder: {rendered!r}"
        )


def test_cli_runner_imports_cleanly():
    """The migrated module must import without syntax/import errors."""
    import code_puppy.cli_runner as cli_runner

    assert hasattr(cli_runner, "interactive_mode")
