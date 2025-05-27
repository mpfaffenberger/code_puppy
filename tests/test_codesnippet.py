import pytest
from code_agent.models.codesnippet import CodeSnippet, CodeResponse

# Test CodeSnippet and CodeResponse data handling
def test_code_snippet_creation():
    """Test creating a code snippet model."""
    snippet = CodeSnippet(language='python', code='print("hello")', explanation='Prints hello world')
    assert snippet.language == 'python'
    assert snippet.code == 'print("hello")'
    assert snippet.explanation == 'Prints hello world'


def test_code_response_creation():
    """Test creating a code response model."""
    snippet = CodeSnippet(language='python', code='print("hello")')
    response = CodeResponse(snippets=[snippet], overall_explanation='A simple test')
    assert response.overall_explanation == 'A simple test'
    assert response.snippets[0].language == 'python'
