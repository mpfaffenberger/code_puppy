"""Models for structured planning and task management."""

from typing import List, Optional
from pydantic import BaseModel


class Subtask(BaseModel):
    """A subtask within a plan step."""
    name: str
    description: Optional[str] = None


class PlanStep(BaseModel):
    """A single step in a structured plan."""
    number: int
    name: str
    description: str
    estimated_time: str
    subtasks: List[Subtask]


class Plan(BaseModel):
    """A complete structured plan for a task."""
    task: str
    overview: str
    steps: List[PlanStep]
    reasoning: str
    total_estimated_time: str
    recommendations: List[str]
