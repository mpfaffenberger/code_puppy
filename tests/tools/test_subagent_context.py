"""Tests for code_puppy.tools.subagent_context.

This module tests the sub-agent context management functionality including
ContextVar state tracking, context manager behavior, and async isolation.
"""

import asyncio
import importlib.util
from pathlib import Path

import pytest

# Import directly from the module file
spec = importlib.util.spec_from_file_location(
    "subagent_context_module",
    Path(__file__).parent.parent.parent
    / "code_puppy"
    / "tools"
    / "subagent_context.py",
)
subagent_context_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subagent_context_module)

subagent_context = subagent_context_module.subagent_context
is_subagent = subagent_context_module.is_subagent
get_subagent_name = subagent_context_module.get_subagent_name
get_subagent_depth = subagent_context_module.get_subagent_depth


class TestSubagentContextBasics:
    """Test basic sub-agent context functionality."""

    def test_initial_state_is_main_agent(self):
        """Test that initial state indicates main agent (not sub-agent)."""
        assert is_subagent() is False
        assert get_subagent_name() is None
        assert get_subagent_depth() == 0

    def test_context_sets_subagent_state(self):
        """Test that entering context sets sub-agent state."""
        assert is_subagent() is False

        with subagent_context("retriever"):
            assert is_subagent() is True
            assert get_subagent_name() == "retriever"
            assert get_subagent_depth() == 1

        # Should restore to main agent state
        assert is_subagent() is False
        assert get_subagent_name() is None
        assert get_subagent_depth() == 0

    def test_context_restores_on_exit(self):
        """Test that context properly restores state on exit."""
        initial_depth = get_subagent_depth()
        initial_name = get_subagent_name()

        with subagent_context("husky"):
            assert get_subagent_depth() == initial_depth + 1
            assert get_subagent_name() == "husky"

        assert get_subagent_depth() == initial_depth
        assert get_subagent_name() == initial_name

    def test_context_restores_on_exception(self):
        """Test that context restores state even when exception occurs."""
        initial_depth = get_subagent_depth()
        initial_name = get_subagent_name()

        with pytest.raises(ValueError):
            with subagent_context("terrier"):
                assert is_subagent() is True
                raise ValueError("Test exception")

        # State should be restored despite exception
        assert get_subagent_depth() == initial_depth
        assert get_subagent_name() == initial_name


class TestNestedSubagents:
    """Test nested sub-agent contexts."""

    def test_nested_contexts_increment_depth(self):
        """Test that nested contexts properly increment depth."""
        assert get_subagent_depth() == 0

        with subagent_context("retriever"):
            assert get_subagent_depth() == 1
            assert get_subagent_name() == "retriever"

            with subagent_context("terrier"):
                assert get_subagent_depth() == 2
                assert get_subagent_name() == "terrier"

                with subagent_context("husky"):
                    assert get_subagent_depth() == 3
                    assert get_subagent_name() == "husky"

                # Back to terrier
                assert get_subagent_depth() == 2
                assert get_subagent_name() == "terrier"

            # Back to retriever
            assert get_subagent_depth() == 1
            assert get_subagent_name() == "retriever"

        # Back to main agent
        assert get_subagent_depth() == 0
        assert get_subagent_name() is None

    def test_nested_contexts_track_name_correctly(self):
        """Test that nested contexts track the current agent name."""
        with subagent_context("outer"):
            assert get_subagent_name() == "outer"

            with subagent_context("middle"):
                assert get_subagent_name() == "middle"

                with subagent_context("inner"):
                    assert get_subagent_name() == "inner"

                assert get_subagent_name() == "middle"

            assert get_subagent_name() == "outer"

    def test_nested_exception_restores_properly(self):
        """Test that exceptions in nested contexts restore properly."""
        with subagent_context("outer"):
            assert get_subagent_depth() == 1
            assert get_subagent_name() == "outer"

            with pytest.raises(RuntimeError):
                with subagent_context("inner"):
                    assert get_subagent_depth() == 2
                    assert get_subagent_name() == "inner"
                    raise RuntimeError("Inner error")

            # Should restore to outer context
            assert get_subagent_depth() == 1
            assert get_subagent_name() == "outer"


class TestAsyncIsolation:
    """Test async context isolation."""

    @pytest.mark.asyncio
    async def test_async_tasks_have_independent_context(self):
        """Test that concurrent async tasks have isolated contexts."""
        results = {}

        async def task_a():
            with subagent_context("task_a_agent"):
                # Small delay to ensure tasks overlap
                await asyncio.sleep(0.01)
                results["a_name"] = get_subagent_name()
                results["a_depth"] = get_subagent_depth()
                results["a_is_sub"] = is_subagent()

        async def task_b():
            with subagent_context("task_b_agent"):
                await asyncio.sleep(0.01)
                results["b_name"] = get_subagent_name()
                results["b_depth"] = get_subagent_depth()
                results["b_is_sub"] = is_subagent()

        async def task_c():
            # Task without sub-agent context
            await asyncio.sleep(0.01)
            results["c_name"] = get_subagent_name()
            results["c_depth"] = get_subagent_depth()
            results["c_is_sub"] = is_subagent()

        # Run tasks concurrently
        await asyncio.gather(task_a(), task_b(), task_c())

        # Each task should have seen its own context
        assert results["a_name"] == "task_a_agent"
        assert results["a_depth"] == 1
        assert results["a_is_sub"] is True

        assert results["b_name"] == "task_b_agent"
        assert results["b_depth"] == 1
        assert results["b_is_sub"] is True

        assert results["c_name"] is None
        assert results["c_depth"] == 0
        assert results["c_is_sub"] is False

    @pytest.mark.asyncio
    async def test_context_restored_after_async_operation(self):
        """Test that context is properly maintained across async operations."""
        with subagent_context("async_agent"):
            assert get_subagent_name() == "async_agent"
            assert get_subagent_depth() == 1

            # Perform async operation
            await asyncio.sleep(0.001)

            # Context should still be maintained
            assert get_subagent_name() == "async_agent"
            assert get_subagent_depth() == 1

        # Context should be restored after exiting
        assert get_subagent_name() is None
        assert get_subagent_depth() == 0


class TestHelperFunctions:
    """Test individual helper functions."""

    def test_is_subagent_returns_bool(self):
        """Test that is_subagent returns a boolean."""
        assert isinstance(is_subagent(), bool)

        with subagent_context("test"):
            assert isinstance(is_subagent(), bool)

    def test_get_subagent_name_returns_correct_type(self):
        """Test that get_subagent_name returns str or None."""
        name = get_subagent_name()
        assert name is None or isinstance(name, str)

        with subagent_context("test_agent"):
            name = get_subagent_name()
            assert isinstance(name, str)

    def test_get_subagent_depth_returns_int(self):
        """Test that get_subagent_depth returns an integer."""
        depth = get_subagent_depth()
        assert isinstance(depth, int)
        assert depth >= 0

        with subagent_context("test"):
            depth = get_subagent_depth()
            assert isinstance(depth, int)
            assert depth > 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_agent_name(self):
        """Test context with empty string as agent name."""
        with subagent_context(""):
            assert is_subagent() is True
            assert get_subagent_name() == ""
            assert get_subagent_depth() == 1

    def test_special_characters_in_name(self):
        """Test context with special characters in agent name."""
        special_name = "agent-123_test.v2"
        with subagent_context(special_name):
            assert get_subagent_name() == special_name

    def test_multiple_sequential_contexts(self):
        """Test multiple sequential (non-nested) contexts."""
        for i in range(5):
            with subagent_context(f"agent_{i}"):
                assert get_subagent_name() == f"agent_{i}"
                assert get_subagent_depth() == 1

            # Should reset each time
            assert is_subagent() is False
            assert get_subagent_depth() == 0

    def test_deeply_nested_contexts(self):
        """Test very deep nesting of contexts."""
        max_depth = 10

        def recurse(depth):
            if depth > max_depth:
                assert get_subagent_depth() == max_depth
                return

            with subagent_context(f"depth_{depth}"):
                assert get_subagent_depth() == depth
                recurse(depth + 1)
                assert get_subagent_depth() == depth

        recurse(1)
        assert get_subagent_depth() == 0
