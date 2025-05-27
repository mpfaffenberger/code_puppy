from pydantic import BaseModel
from typing import Optional, List


class CodeSnippet(BaseModel):
    """Model representing a code snippet with explanation."""

    language: str
    code: str
    explanation: Optional[str] = None
    imports: Optional[List[str]] = None


class CodeResponse(BaseModel):
    """Model representing a response with code snippets and explanation."""

    snippets: List[CodeSnippet]
    overall_explanation: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
