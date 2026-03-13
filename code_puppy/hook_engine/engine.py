"""
Main HookEngine orchestration class.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from .executor import execute_hooks_sequential, get_blocking_result
from .matcher import matches
from .models import (
    EventData,
    HookConfig,
    HookRegistry,
    ProcessEventResult,
)
from .registry import build_registry_from_config, get_registry_stats
from .validator import (
    format_validation_report,
    get_config_suggestions,
    validate_hooks_config,
)

logger = logging.getLogger(__name__)


class HookEngine:
    """
    Main hook engine for processing events and executing hooks.

    Coordinates all hook engine components:
    - Loads and validates configuration
    - Matches events against hook patterns
    - Executes hooks with timeout and error handling
    - Aggregates results and determines blocking status
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        strict_validation: bool = True,
        env_vars: Optional[Dict[str, str]] = None,
    ):
        self.env_vars = env_vars or {}
        self.strict_validation = strict_validation
        self._registry: Optional[HookRegistry] = None

        if config:
            self.load_config(config)
        else:
            self._registry = HookRegistry()

    def load_config(self, config: Dict[str, Any]) -> None:
        is_valid, errors = validate_hooks_config(config)

        if not is_valid:
            error_msg = format_validation_report(
                is_valid, errors, get_config_suggestions(config, errors)
            )
            if self.strict_validation:
                raise ValueError(f"Invalid hook configuration:\n{error_msg}")
            else:
                logger.warning(f"Hook configuration has errors:\n{error_msg}")

        try:
            self._registry = build_registry_from_config(config)
            logger.info(
                f"Loaded hook configuration: {self._registry.count_hooks()} total hooks"
            )
        except Exception as e:
            if self.strict_validation:
                raise ValueError(f"Failed to build hook registry: {e}") from e
            else:
                logger.error(f"Failed to build hook registry: {e}", exc_info=True)
                self._registry = HookRegistry()

    def reload_config(self, config: Dict[str, Any]) -> None:
        self.load_config(config)

    async def process_event(
        self,
        event_type: str,
        event_data: EventData,
        sequential: bool = True,
        stop_on_block: bool = True,
    ) -> ProcessEventResult:
        """Process an event through the hook engine."""
        start_time = time.perf_counter()

        if not self._registry:
            return ProcessEventResult(
                blocked=False, executed_hooks=0, results=[], total_duration_ms=0.0
            )

        all_hooks = self._registry.get_hooks_for_event(event_type)

        if not all_hooks:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return ProcessEventResult(
                blocked=False,
                executed_hooks=0,
                results=[],
                total_duration_ms=duration_ms,
            )

        matching_hooks = self._filter_hooks_by_matcher(
            all_hooks, event_data.tool_name, event_data.tool_args
        )

        if not matching_hooks:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return ProcessEventResult(
                blocked=False,
                executed_hooks=0,
                results=[],
                total_duration_ms=duration_ms,
            )

        logger.debug(
            f"Processing {event_type}: {len(matching_hooks)} matching hook(s) for tool '{event_data.tool_name}'"
        )

        if sequential:
            results = await execute_hooks_sequential(
                matching_hooks, event_data, self.env_vars, stop_on_block=stop_on_block
            )
        else:
            from .executor import execute_hooks_parallel

            results = await execute_hooks_parallel(
                matching_hooks, event_data, self.env_vars
            )

        for hook, result in zip(matching_hooks, results):
            if hook.once and result.success:
                self._registry.mark_hook_executed(hook.id)

        blocking_result = get_blocking_result(results)
        blocked = blocking_result is not None
        blocking_reason = None

        if blocked:
            blocking_reason = (
                f"Hook '{blocking_result.hook_command}' failed: "
                f"{blocking_result.error or blocking_result.stderr or 'blocked (no details provided)'}"
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        return ProcessEventResult(
            blocked=blocked,
            executed_hooks=len(results),
            results=results,
            blocking_reason=blocking_reason,
            total_duration_ms=duration_ms,
        )

    def _filter_hooks_by_matcher(
        self,
        hooks: List[HookConfig],
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> List[HookConfig]:
        matching_hooks = []
        for hook in hooks:
            try:
                if matches(hook.matcher, tool_name, tool_args):
                    matching_hooks.append(hook)
            except Exception as e:
                logger.error(
                    f"Error matching hook '{hook.matcher}': {e}", exc_info=True
                )
        return matching_hooks

    def get_stats(self) -> Dict[str, Any]:
        if not self._registry:
            return {"total_hooks": 0, "error": "No registry loaded"}
        return get_registry_stats(self._registry)

    def get_hooks_for_event(self, event_type: str) -> List[HookConfig]:
        if not self._registry:
            return []
        return self._registry.get_hooks_for_event(event_type)

    def count_hooks(self, event_type: Optional[str] = None) -> int:
        if not self._registry:
            return 0
        return self._registry.count_hooks(event_type)

    def reset_once_hooks(self) -> None:
        if self._registry:
            self._registry.reset_once_hooks()

    def add_hook(self, event_type: str, hook: HookConfig) -> None:
        if not self._registry:
            self._registry = HookRegistry()
        self._registry.add_hook(event_type, hook)

    def remove_hook(self, event_type: str, hook_id: str) -> bool:
        if not self._registry:
            return False
        return self._registry.remove_hook(event_type, hook_id)

    def set_env_vars(self, env_vars: Dict[str, str]) -> None:
        self.env_vars = env_vars

    def update_env_vars(self, env_vars: Dict[str, str]) -> None:
        self.env_vars.update(env_vars)

    @property
    def is_loaded(self) -> bool:
        return self._registry is not None

    @property
    def registry(self) -> Optional[HookRegistry]:
        return self._registry


def validate_config_file(config: Dict[str, Any]) -> str:
    is_valid, errors = validate_hooks_config(config)
    suggestions = get_config_suggestions(config, errors) if not is_valid else []
    return format_validation_report(is_valid, errors, suggestions)
