"""Regression tests: a lone surrogate must never brick the config file.

Background: a user pasted a name whose bytes were not valid UTF-8 (Latin-1
``0xC3``). Python decoded them as a lone surrogate (``\\udcc3``), the value
landed in ``puppy.cfg``, and writing the config raised::

    UnicodeEncodeError: 'utf-8' codec can't encode character '\\udcc3'

Because the write is atomic, the exception left **no config file at all**:
the app then failed on every single start, with no way back except
hand-editing ``~/.code_puppy/puppy.cfg``.

The fix keeps the invariant "a persisted config value is valid UTF-8" at the
two places that own it:

* :func:`code_puppy.config_file.sanitize_config_text` -- the writer
  sanitizes before encoding, so no write path can crash;
* the first-run prompt -- the typed value is sanitized before it reaches
  the in-memory parser, so it is clean in memory too (it is echoed back to
  the terminal).
"""

import configparser

import pytest

from code_puppy import config as cp_config
from code_puppy import config_file

#: The name the user typed: "Tar<0xC3>o", where the lone byte 0xC3 was
#: decoded by Python as the surrogate U+DCC3 (it is not valid UTF-8).
SURROGATE = "Tar\udcc3o"


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    """Point CONFIG_FILE at a real (temp) path so os.replace behaves."""
    cfg_dir = tmp_path / "cfgdir"
    cfg_dir.mkdir()
    path = cfg_dir / "puppy.cfg"
    monkeypatch.setattr(cp_config, "CONFIG_FILE", str(path))
    return path


class TestSanitizeConfigText:
    def test_clean_text_is_untouched(self):
        text = "Taro \U0001f436 owner= Pablo"

        assert config_file.sanitize_config_text(text) == text

    def test_empty_text_is_untouched(self):
        assert config_file.sanitize_config_text("") == ""

    def test_lone_surrogate_is_replaced(self):
        cleaned = config_file.sanitize_config_text(SURROGATE)

        assert SURROGATE != cleaned
        assert "\udcc3" not in cleaned
        # The rest of the value survives verbatim.
        assert cleaned.startswith("Tar") and cleaned.endswith("o")
        # ...and the result is encodable as UTF-8.
        cleaned.encode("utf-8")


class TestWriteNeverRaises:
    def test_mutate_config_with_surrogate_persists_clean_utf8(self, cfg_path):
        """The write path must not raise, and the file must be valid UTF-8."""

        def _apply(parser: configparser.ConfigParser) -> None:
            if cp_config.DEFAULT_SECTION not in parser:
                parser[cp_config.DEFAULT_SECTION] = {}
            parser[cp_config.DEFAULT_SECTION]["puppy_name"] = SURROGATE

        config_file.mutate_config(str(cfg_path), _apply)

        raw = cfg_path.read_bytes()
        # No crash, and the file decodes as strict UTF-8.
        text = raw.decode("utf-8")
        assert "\udcc3" not in text
        # The config is still a loadable INI file.
        parser = configparser.ConfigParser()
        parser.read_string(text)
        assert parser[cp_config.DEFAULT_SECTION]["puppy_name"].startswith("Tar")

    def test_surrogate_value_survives_a_round_trip(self, cfg_path):
        """A config written with a surrogate can be read back and rewritten."""
        cp_config.set_config_value("puppy_name", SURROGATE)

        # Reading it back must not explode and must be encodable.
        value = cp_config.get_value("puppy_name")
        assert value is not None
        value.encode("utf-8")

        # ...and a second write of the (clean) value still works.
        cp_config.set_config_value("puppy_name", value)
        assert cfg_path.exists()


class TestFirstRunPrompt:
    def test_onboarding_survives_a_surrogate_typed_name(self, cfg_path, monkeypatch):
        """The first-run prompt must not crash on a non-UTF-8 paste.

        This is the exact path that bricked the user's install: the typed
        name went straight into the config and the write exploded.
        """
        answers = iter([SURROGATE, "Pablo"])
        monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: next(answers))

        config = cp_config.ensure_config_exists()

        stored = config[cp_config.DEFAULT_SECTION]["puppy_name"]
        assert "\udcc3" not in stored
        stored.encode("utf-8")

        # The file the app will read on the next start is valid UTF-8.
        cfg_path.read_bytes().decode("utf-8")

        # ...and the app can read its own config back.
        assert cp_config.get_value("puppy_name") == stored
