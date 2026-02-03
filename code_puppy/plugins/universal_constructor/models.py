"""Pydantic models for Universal Constructor tools and responses.

This module defines the data structures used throughout the UC plugin
for representing tool metadata, tool information, and operation responses.
"""

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ToolMeta(BaseModel):
    """Metadata for a UC tool.

    This is the structure expected in the TOOL_META dictionary
    at the top of each tool file.
    """

    name: str = Field(..., description="Human-readable tool name")
    namespace: str = Field(
        default="", description="Namespace for the tool (from subdirectory path)"
    )
    description: str = Field(..., description="What the tool does")
    enabled: bool = Field(default=True, description="Whether the tool is active")
    version: str = Field(default="1.0.0", description="Semantic version of the tool")
    author: str = Field(default="", description="Tool author or creator")
    created_at: Optional[str] = Field(
        default=None, description="When the tool was created (ISO format string)"
    )

    model_config = {"extra": "allow"}  # Allow additional metadata fields


class UCToolInfo(BaseModel):
    """Full information about a UC tool.

    Combines metadata with runtime information like function signature
    and source file location.
    """

    meta: ToolMeta = Field(..., description="Tool metadata")
    signature: str = Field(..., description="Function signature string")
    source_path: str = Field(..., description="Path to the tool source file")
    function_name: str = Field(default="", description="Name of the callable function")
    docstring: Optional[str] = Field(default=None, description="Function docstring")

    model_config = {"arbitrary_types_allowed": True}

    @property
    def full_name(self) -> str:
        """Get the fully qualified tool name including namespace."""
        if self.meta.namespace:
            return f"{self.meta.namespace}.{self.meta.name}"
        return self.meta.name


# Response models for UC operations


class UCListOutput(BaseModel):
    """Response model for listing UC tools."""

    tools: List[UCToolInfo] = Field(
        default_factory=list, description="List of available tools"
    )
    total_count: int = Field(default=0, description="Total number of tools")
    enabled_count: int = Field(default=0, description="Number of enabled tools")
    error: Optional[str] = Field(default=None, description="Error message if any")

    model_config = {"arbitrary_types_allowed": True}


class UCCallOutput(BaseModel):
    """Response model for calling a UC tool."""

    success: bool = Field(..., description="Whether the call succeeded")
    tool_name: str = Field(..., description="Name of the tool that was called")
    result: Any = Field(default=None, description="Return value from the tool")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    execution_time: Optional[float] = Field(
        default=None, description="Execution time in seconds"
    )
    source_preview: Optional[str] = Field(
        default=None, description="Preview of the tool's source code that was executed"
    )


class UCCreateOutput(BaseModel):
    """Response model for creating a UC tool."""

    success: bool = Field(..., description="Whether creation succeeded")
    tool_name: str = Field(default="", description="Name of the created tool")
    source_path: Optional[str] = Field(
        default=None, description="Path where tool was saved"
    )
    preview: Optional[str] = Field(
        default=None, description="Preview of the first 10 lines of source code"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
    validation_warnings: List[str] = Field(
        default_factory=list, description="Non-fatal validation warnings"
    )

    model_config = {"arbitrary_types_allowed": True}


class UCUpdateOutput(BaseModel):
    """Response model for updating a UC tool."""

    success: bool = Field(..., description="Whether update succeeded")
    tool_name: str = Field(default="", description="Name of the updated tool")
    source_path: Optional[str] = Field(
        default=None, description="Path to the updated tool"
    )
    preview: Optional[str] = Field(
        default=None, description="Preview of the first 10 lines of updated source code"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
    changes_applied: List[str] = Field(
        default_factory=list, description="List of changes that were applied"
    )

    model_config = {"arbitrary_types_allowed": True}


class UCInfoOutput(BaseModel):
    """Response model for getting info about a specific UC tool."""

    success: bool = Field(..., description="Whether lookup succeeded")
    tool: Optional[UCToolInfo] = Field(
        default=None, description="Tool information if found"
    )
    source_code: Optional[str] = Field(
        default=None, description="Source code of the tool"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")

    model_config = {"arbitrary_types_allowed": True}
