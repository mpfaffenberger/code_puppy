"""Tests for motd.py - cover remaining lines 41-44."""

from unittest.mock import patch

from code_puppy.command_line.motd import MOTD_MESSAGE, MOTD_VERSION, get_motd_content


class TestGetMotdContent:
    @patch("code_puppy.callbacks.on_get_motd", return_value=[])
    def test_no_plugin_results(self, mock_motd):
        msg, ver = get_motd_content()
        assert msg == MOTD_MESSAGE
        assert ver == MOTD_VERSION

    @patch("code_puppy.callbacks.on_get_motd", return_value=[("custom msg", "v2")])
    def test_plugin_result(self, mock_motd):
        msg, ver = get_motd_content()
        assert msg == "custom msg"
        assert ver == "v2"

    @patch("code_puppy.callbacks.on_get_motd", return_value=[None, ("last", "v3")])
    def test_last_non_none(self, mock_motd):
        msg, ver = get_motd_content()
        assert msg == "last"

    @patch("code_puppy.callbacks.on_get_motd", return_value=[None])
    def test_all_none(self, mock_motd):
        msg, ver = get_motd_content()
        assert msg == MOTD_MESSAGE

    @patch("code_puppy.callbacks.on_get_motd", side_effect=Exception("err"))
    def test_exception(self, mock_motd):
        msg, ver = get_motd_content()
        assert msg == MOTD_MESSAGE

    @patch("code_puppy.callbacks.on_get_motd", return_value=["not a tuple"])
    def test_non_tuple_result(self, mock_motd):
        msg, ver = get_motd_content()
        assert msg == MOTD_MESSAGE
