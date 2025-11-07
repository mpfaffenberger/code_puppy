"""GUI-Cub workflow executor - Execute YAML workflows with chaining support."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class WorkflowExecutionError(Exception):
    """Raised when workflow execution fails."""

    pass


class WorkflowExecutionResult(BaseModel):
    """Structured result from workflow execution."""

    workflow: str = Field(..., description="Workflow name")
    status: str = Field(..., description="success, failure, or partial")
    execution_time: float = Field(..., description="Total execution time in seconds")
    parameters_used: Dict[str, Any] = Field(
        default_factory=dict, description="Parameters passed to workflow"
    )
    outputs: Dict[str, Any] = Field(
        default_factory=dict, description="Extracted output data"
    )
    steps_executed: int = Field(
        default=0, description="Number of steps successfully executed"
    )
    steps_skipped: int = Field(
        default=0, description="Number of steps skipped (conditional)"
    )
    errors: List[str] = Field(default_factory=list, description="Error messages if any")
    screenshots: List[str] = Field(
        default_factory=list, description="Paths to screenshots taken"
    )
