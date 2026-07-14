"""Tests for the retry *policy* layer (selectable, guard-railed backoff profiles).

These verify the guarantees that stop a user from configuring a pathological
retry policy (e.g. "10 retries in 10s"), the per-role defaults, and the
per-model > global > default resolution hierarchy.
"""

import asyncio
import random

import pytest

from code_puppy.agents import retry_profiles as rp


class TestStrategies:
    def test_exactly_three_strategies(self):
        # The feature promised THREE flavors of exponential+jitter.
        assert set(rp.STRATEGY_NAMES) == {"gentle", "balanced", "aggressive"}

    def test_strategies_are_strictly_ordered_by_aggressiveness(self):
        # Adversarial: the old test only checked ``aggressive[-1] >= gentle[-1]``,
        # which is tautological -- both strategies saturate to the 30s cap at the
        # last index, so it asserted ``x >= x`` and would pass even if the
        # gentle/aggressive curves were SWAPPED. Compare cumulative spacing with
        # a shared seed instead: aggressive must ramp strictly faster than
        # balanced, which must ramp strictly faster than gentle. This fails loudly
        # if anyone swaps or flattens the exponents.
        def total(strategy):
            return sum(
                rp.RetryProfile("main", strategy, 6).compute_delays(random.Random(0))
            )

        assert total("gentle") < total("balanced") < total("aggressive")

    def test_aggressive_reaches_cap_before_gentle(self):
        # A second, independent angle: at an early index (before either
        # saturates) aggressive must already be waiting strictly longer.
        g = rp.RetryProfile("main", "gentle", 8).compute_delays(random.Random(0))
        a = rp.RetryProfile("main", "aggressive", 8).compute_delays(random.Random(0))
        assert a[2] > g[2]


class TestGuardrails:
    @pytest.mark.parametrize("strategy", ["gentle", "balanced", "aggressive"])
    def test_no_delay_ever_exceeds_30s(self, strategy):
        # The hard 30s ceiling the user cannot escape.
        delays = rp.RetryProfile("subagent", strategy, 15).compute_delays(
            random.Random(1)
        )
        assert all(d <= rp.MAX_DELAY_SECONDS for d in delays)

    @pytest.mark.parametrize("strategy", ["gentle", "balanced", "aggressive"])
    def test_no_delay_below_one_second_floor(self, strategy):
        delays = rp.RetryProfile("main", strategy, 15).compute_delays(random.Random(2))
        assert all(d >= rp.MIN_DELAY_SECONDS for d in delays)

    def test_cannot_configure_10_retries_in_10_seconds(self):
        # The headline guardrail: even the gentlest strategy with lots of
        # attempts can't cram many retries into a tiny window. 10 attempts means
        # 9 sleeps; with a 1s floor and exponential ramp that's WAY more than 10s.
        delays = rp.make("main", "gentle", 10).compute_delays(random.Random(3))
        assert len(delays) == 9
        assert sum(delays) > 10  # impossible to be "10 retries in 10s"

    def test_attempts_clamped_to_ceiling(self):
        # A hand-edited config with an absurd attempt count clamps down.
        assert rp.make("main", "balanced", 999).max_attempts == rp.MAX_ATTEMPTS_CEILING

    def test_worst_case_backoff_is_bounded_far_below_24h(self):
        # The whole point of the ceiling: even at max attempts + max strategy,
        # total *sleep* time must stay well under 24h (86400s). Worst case is
        # (ceiling - 1) * 30s. Assert both the structural bound and that the
        # ceiling itself is far below the 24h/30s runaway threshold (2880).
        assert rp.MAX_ATTEMPTS_CEILING < 2880  # 86400s / 30s -- runaway line
        worst_case_sleep = (rp.MAX_ATTEMPTS_CEILING - 1) * rp.MAX_DELAY_SECONDS
        assert worst_case_sleep < 3600  # under an hour, nowhere near 24h
        # And the actual computed delays never exceed that structural bound.
        for strategy in rp.STRATEGY_NAMES:
            delays = rp.RetryProfile(
                "subagent", strategy, rp.MAX_ATTEMPTS_CEILING
            ).compute_delays()
            assert sum(delays) <= worst_case_sleep

    def test_attempts_clamped_to_floor(self):
        assert rp.make("main", "balanced", 0).max_attempts == rp.MIN_ATTEMPTS_FLOOR
        assert rp.make("main", "balanced", -5).max_attempts == rp.MIN_ATTEMPTS_FLOOR

    def test_unknown_strategy_falls_back_to_balanced(self):
        assert rp.make("main", "turbo-nonsense", 5).strategy == "balanced"

    def test_non_string_strategy_falls_back_not_crashes(self):
        # ``make`` is module-public; a caller passing a non-str strategy must
        # fall back gracefully rather than AttributeError on ``.lower()``.
        assert rp.make("main", 123, 5).strategy == "balanced"  # type: ignore[arg-type]
        assert rp.make("main", ["gentle"], 5).strategy == "balanced"  # type: ignore[arg-type]

    def test_none_strategy_falls_back_to_role_default(self):
        assert rp.make("main", None, 5).strategy == "balanced"

    def test_n_attempts_yields_n_minus_1_delays(self):
        assert len(rp.RetryProfile("main", "balanced", 1).compute_delays()) == 0
        assert len(rp.RetryProfile("main", "balanced", 5).compute_delays()) == 4


class TestRoleDefaults:
    def test_subagent_defaults_to_more_attempts_than_main(self):
        # Sub-agents are more precious (accumulated work), so they retry longer.
        main = rp.make("main", None, None)
        sub = rp.make("subagent", None, None)
        assert sub.max_attempts > main.max_attempts

    def test_unknown_role_treated_as_main(self):
        assert (
            rp.make("bogus", None, None).max_attempts
            == rp.make("main", None, None).max_attempts
        )


class TestResolution:
    def test_global_default_when_unset(self, monkeypatch):
        monkeypatch.setattr(rp, "_read_raw_setting", lambda role, field, model: None)
        profile = rp.resolve("main")
        assert profile.strategy == "balanced"
        assert profile.max_attempts == 5

    def test_global_setting_overrides_default(self, monkeypatch):
        def fake(role, field, model):
            return {"strategy": "aggressive", "max_attempts": "7"}[field]

        monkeypatch.setattr(rp, "_read_raw_setting", fake)
        profile = rp.resolve("main")
        assert profile.strategy == "aggressive"
        assert profile.max_attempts == 7

    def test_per_model_override_beats_global(self, monkeypatch):
        from code_puppy import config

        stored = {
            "retry_main_strategy": "gentle",
            "retry_model_gpt_5_main_strategy": "aggressive",
        }
        monkeypatch.setattr(config, "get_value", lambda k: stored.get(k))
        monkeypatch.setattr(
            config,
            "_sanitize_model_name_for_key",
            lambda name: name.replace("-", "_"),
        )
        # With a model that has an override -> aggressive; without -> gentle.
        assert rp.resolve("main", "gpt-5").strategy == "aggressive"
        assert rp.resolve("main", "other-model").strategy == "gentle"

    def test_per_model_override_is_role_specific(self, monkeypatch):
        # Per-model overrides are role-SPECIFIC: a model can retry differently as
        # the main agent vs. as a sub-agent. Only the overridden role changes.
        from code_puppy import config

        stored = {
            "retry_main_strategy": "gentle",
            "retry_subagent_strategy": "gentle",
            "retry_model_gpt_5_subagent_strategy": "aggressive",
        }
        monkeypatch.setattr(config, "get_value", lambda k: stored.get(k))
        monkeypatch.setattr(
            config, "_sanitize_model_name_for_key", lambda name: name.replace("-", "_")
        )
        # Only the sub-agent role was overridden for gpt-5.
        assert rp.resolve("subagent", "gpt-5").strategy == "aggressive"
        assert rp.resolve("main", "gpt-5").strategy == "gentle"

    def test_per_model_key_format(self, monkeypatch):
        from code_puppy import config

        monkeypatch.setattr(
            config, "_sanitize_model_name_for_key", lambda name: name.replace("-", "_")
        )
        assert (
            rp.per_model_key("gpt-5", "main", "strategy")
            == "retry_model_gpt_5_main_strategy"
        )
        assert (
            rp.per_model_key("gpt-5", "subagent", "max_attempts")
            == "retry_model_gpt_5_subagent_max_attempts"
        )
        # Must NOT collide with the model_settings_ namespace scraped by /model.
        assert not rp.per_model_key("gpt-5", "main", "strategy").startswith(
            "model_settings_"
        )

    def test_garbage_int_config_falls_back_not_crashes(self, monkeypatch):
        def fake(role, field, model):
            return "not-a-number" if field == "max_attempts" else "balanced"

        monkeypatch.setattr(rp, "_read_raw_setting", fake)
        # Bad int -> role default (5 for main), never an exception.
        assert rp.resolve("main").max_attempts == 5


class TestAdversarialConfig:
    """Regressions for bugs found in adversarial self-review."""

    @pytest.mark.parametrize("bad", ["inf", "-inf", "1e999", "nan"])
    def test_non_finite_attempts_never_crash_hot_path(self, monkeypatch, bad):
        # BUG: int(float('inf')) raises OverflowError; resolve() is on the
        # unwrapped hot path, so a hand-edited config would crash EVERY run.
        # Must clamp to the role default instead.
        def fake(role, field, model):
            return bad if field == "max_attempts" else "balanced"

        monkeypatch.setattr(rp, "_read_raw_setting", fake)
        profile = rp.resolve("main")  # must not raise
        assert profile.max_attempts == 5

    def test_huge_attempt_count_does_not_overflow_the_exponent(self):
        # BUG: exponent ** i OverflowErrors for large i. Even though the ceiling
        # clamps user input to 15, compute_delays must be robust if the ceiling
        # is ever raised -- a policy knob should never be a landmine.
        delays = rp.RetryProfile("main", "aggressive", 2000).compute_delays()
        assert len(delays) == 1999
        assert all(d <= rp.MAX_DELAY_SECONDS for d in delays)

    def test_per_model_override_uses_dedicated_namespace(self):
        # BUG: per-model overrides originally reused the model_settings_ prefix,
        # which the /model settings editor scrapes wholesale -- leaking retry
        # knobs as bogus editable model settings. They must live under the
        # dedicated retry_model_ namespace and NOT appear in model settings.
        from code_puppy import config

        config.set_value("retry_model_gpt_5_main_strategy", "aggressive")
        try:
            assert rp.resolve("main", "gpt-5").strategy == "aggressive"
            leaked = config.get_all_model_settings("gpt-5")
            assert not any("retry" in k for k in leaked)
        finally:
            config.reset_value("retry_model_gpt_5_main_strategy")

    def test_make_streaming_retry_falls_back_when_resolve_explodes(self, monkeypatch):
        # Defense-in-depth: a retry-config problem must never crash the run the
        # retry machinery exists to protect. If resolve() blows up, we still get
        # a working decorator built from the role default.
        from unittest.mock import AsyncMock, patch

        from pydantic_ai import UnexpectedModelBehavior

        def boom(role, model=None):
            raise RuntimeError("corrupt retry config")

        monkeypatch.setattr(rp, "resolve", boom)

        attempts = {"n": 0}
        retry = rp.make_streaming_retry("subagent", "some-model")  # must not raise

        @retry
        async def _flaky():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise UnexpectedModelBehavior("rate limited, please retry")
            return "ok"

        with patch("code_puppy.agents._runtime.asyncio.sleep", new_callable=AsyncMock):
            result = asyncio.run(_flaky())

        assert result == "ok"
        assert attempts["n"] == 2


class TestMakeStreamingRetry:
    @pytest.mark.asyncio
    async def test_bridges_profile_into_working_retry_decorator(self, monkeypatch):
        # The bridge must produce a decorator that actually retries using the
        # resolved profile's attempt count. Use a 2-attempt profile + no sleep.
        from unittest.mock import AsyncMock, patch

        from pydantic_ai import UnexpectedModelBehavior

        monkeypatch.setattr(
            rp, "resolve", lambda role, model=None: rp.RetryProfile(role, "balanced", 2)
        )

        attempts = {"n": 0}
        retry = rp.make_streaming_retry("subagent", "some-model")

        @retry
        async def _flaky():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise UnexpectedModelBehavior("rate limited, please retry")
            return "ok"

        with patch("code_puppy.agents._runtime.asyncio.sleep", new_callable=AsyncMock):
            result = await _flaky()

        assert result == "ok"
        assert attempts["n"] == 2

    def test_role_plumbing_differentiates_main_vs_subagent(self, monkeypatch):
        # End-to-end through resolve() -> streaming_retry(): with default config,
        # 'main' exhausts after 5 attempts and 'subagent' after 9. If the role
        # string were ignored/swapped, these counts would collide -- so this
        # guards the role-plumbing all the way through the bridge. Force role
        # defaults (ignore any ambient puppy.cfg) so the test is hermetic.
        from unittest.mock import AsyncMock, patch

        from pydantic_ai import UnexpectedModelBehavior

        monkeypatch.setattr(rp, "_read_raw_setting", lambda role, field, model: None)

        def run_until_exhausted(role):
            attempts = {"n": 0}
            retry = rp.make_streaming_retry(role)

            @retry
            async def _always_down():
                attempts["n"] += 1
                raise UnexpectedModelBehavior("rate limited, please retry")

            with patch(
                "code_puppy.agents._runtime.asyncio.sleep", new_callable=AsyncMock
            ):
                with pytest.raises(UnexpectedModelBehavior):
                    asyncio.run(_always_down())
            return attempts["n"]

        assert run_until_exhausted("main") == 5
        assert run_until_exhausted("subagent") == 9
