"""Models for structured thinking and analysis."""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class AnalysisPoint(BaseModel):
    """A single point of analysis with importance level."""
    point: str
    rationale: Optional[str] = None
    importance: str = Field(..., description="High, Medium, or Low importance")


class ThoughtAnalysis(BaseModel):
    """Structured analysis with strengths, challenges, and insights."""
    strengths: List[AnalysisPoint]
    challenges: List[AnalysisPoint]
    insights: List[AnalysisPoint]
    reflection: str = Field(..., description="Overall reflection on the topic")
    

class Recommendation(BaseModel):
    """A recommendation with priority and effort level."""
    action: str
    benefit: str
    effort: str = Field(..., description="High, Medium, or Low effort required")
    priority: str = Field(..., description="High, Medium, or Low priority")


class ThinkingOutput(BaseModel):
    """Complete structured thinking output."""
    topic: str
    timestamp: datetime = Field(default_factory=datetime.now)
    analysis: ThoughtAnalysis
    recommendations: List[Recommendation]
    context_analysis: Optional[str] = None
