"""Tests for code_puppy.scheduler.time_utils.parse_times_hhmm."""

from unittest.mock import MagicMock

import pytest

from code_puppy.scheduler.time_utils import parse_times_hhmm


class TestParseTimesHhmm:
    # -- happy-path parsing ---------------------------------------------------

    def test_single_valid_time(self):
        assert parse_times_hhmm("09:00") == ["09:00"]

    def test_multiple_valid_times(self):
        assert parse_times_hhmm("09:00,17:30") == ["09:00", "17:30"]

    def test_preserves_order(self):
        assert parse_times_hhmm("17:30,09:00") == ["17:30", "09:00"]

    def test_midnight(self):
        assert parse_times_hhmm("00:00") == ["00:00"]

    def test_end_of_day(self):
        assert parse_times_hhmm("23:59") == ["23:59"]

    # -- normalisation --------------------------------------------------------

    def test_normalises_single_digit_hour(self):
        """'9:00' should be normalised to '09:00'."""
        assert parse_times_hhmm("9:00") == ["09:00"]

    def test_normalises_single_digit_minute(self):
        """strptime/strftime round-trip ensures two-digit minute."""
        assert parse_times_hhmm("09:5") == ["09:05"]

    # -- deduplication --------------------------------------------------------

    def test_deduplicates_exact_duplicates(self):
        assert parse_times_hhmm("09:00,09:00") == ["09:00"]

    def test_deduplicates_normalised_equivalents(self):
        """'9:00' and '09:00' represent the same time after normalisation."""
        assert parse_times_hhmm("9:00,09:00") == ["09:00"]

    def test_deduplicate_preserves_first_occurrence(self):
        result = parse_times_hhmm("09:00,17:00,09:00,17:00")
        assert result == ["09:00", "17:00"]

    # -- whitespace handling --------------------------------------------------

    def test_strips_whitespace_around_entries(self):
        assert parse_times_hhmm(" 09:00 , 17:30 ") == ["09:00", "17:30"]

    def test_empty_segments_between_commas_are_ignored(self):
        assert parse_times_hhmm("09:00,,17:30") == ["09:00", "17:30"]

    def test_leading_trailing_commas_are_ignored(self):
        assert parse_times_hhmm(",09:00,") == ["09:00"]

    # -- invalid entries ------------------------------------------------------

    def test_empty_string_returns_empty_list(self):
        assert parse_times_hhmm("") == []

    def test_all_invalid_returns_empty_list(self):
        assert parse_times_hhmm("bad,worse,9am") == []

    def test_mixed_valid_and_invalid_keeps_valid(self):
        assert parse_times_hhmm("09:00,bad,17:30") == ["09:00", "17:30"]

    def test_missing_colon_is_invalid(self):
        assert parse_times_hhmm("0900") == []

    def test_out_of_range_hour_is_invalid(self):
        assert parse_times_hhmm("25:00") == []

    def test_out_of_range_minute_is_invalid(self):
        assert parse_times_hhmm("09:60") == []

    # -- on_invalid callback --------------------------------------------------

    def test_on_invalid_called_for_each_bad_entry(self):
        callback = MagicMock()
        parse_times_hhmm("09:00,bad,worse", on_invalid=callback)
        assert callback.call_count == 2
        callback.assert_any_call("bad")
        callback.assert_any_call("worse")

    def test_on_invalid_not_called_for_valid_entries(self):
        callback = MagicMock()
        parse_times_hhmm("09:00,17:30", on_invalid=callback)
        callback.assert_not_called()

    def test_on_invalid_none_silently_skips(self):
        """Default (no callback) must not raise for invalid input."""
        result = parse_times_hhmm("garbage", on_invalid=None)
        assert result == []

    def test_on_invalid_not_called_for_empty_segments(self):
        """Empty segments (trailing comma, double comma) are dropped silently."""
        callback = MagicMock()
        parse_times_hhmm("09:00,,", on_invalid=callback)
        callback.assert_not_called()
