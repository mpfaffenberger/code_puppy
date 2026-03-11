"""PuppyTales tools for saving and managing Code Puppy success stories.

These tools help the puppy-tales agent collect and persist user stories
about their Code Puppy wins to ~/.code_puppy/stories/.
"""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

import httpx
from pydantic import BaseModel, Field


# =============================================================================
# Story Schema (consistent for database storage)
# =============================================================================


class PuppyTalesStory(BaseModel):
    """A Code Puppy success story with consistent schema for DB storage."""

    # Identifiers
    story_id: str = Field(description="Unique story ID (e.g., PUPPY-2026-XXXX)")
    slug: str = Field(description="URL-safe slug derived from project name")

    # Story content
    project_name: str = Field(description="Short project name (3-5 words)")
    project_purpose: str = Field(
        description="The business problem, goal, or insight they wanted to achieve"
    )
    problem_solved: str = Field(description="What problem Code Puppy helped solve")
    before_code_puppy: str = Field(description="How the task was done before")
    after_code_puppy: str = Field(description="How the task is done now")
    time_saved: str = Field(description="Estimated time savings")
    lessons_learned: str = Field(description="Tips and advice for others")
    category: Literal[
        "reports & dashboards",
        "data cleanup",
        "process automation",
        "email & communication",
        "document creation",
        "research & analysis",
        "training & learning",
        "scheduling & planning",
        "agent",
        "webapp",
        "other",
    ] = Field(description="Story category")

    # Project metrics (optional, collected during exploration)
    project_type: Optional[str] = Field(
        default=None, description="Detected project type (e.g., Python, JavaScript)"
    )
    lines_of_code: Optional[int] = Field(
        default=None, description="Approximate lines of code"
    )
    git_commits: Optional[int] = Field(
        default=None, description="Number of git commits"
    )
    estimated_dev_hours: Optional[float] = Field(
        default=None, description="Estimated development hours from git analysis"
    )
    complexity: Optional[Literal["simple", "medium", "complex"]] = Field(
        default=None, description="Project complexity assessment"
    )

    # Metadata
    submitted_at: str = Field(description="ISO 8601 timestamp of submission")
    submitted_by: Optional[str] = Field(
        default=None, description="User ID if available"
    )

    # Author profile
    author_name: Optional[str] = Field(
        default=None, description="Author's name (e.g., 'Mary')"
    )
    author_role: Optional[str] = Field(
        default=None, description="Author's role (e.g., 'Fork Lift Operator')"
    )
    author_department: Optional[str] = Field(
        default=None, description="Department or area (e.g., 'Stores', 'Tech', 'Supply Chain')"
    )
    author_location: Optional[str] = Field(
        default=None, description="Store number or location (e.g., 'Store #1234', 'Bentonville HO')"
    )
    collaborators: Optional[List[str]] = Field(
        default=None,
        description="List of collaborators who helped (names, for credit and reach analysis)",
    )
    success: Optional[str] = Field(
        default=None,
        description="What success looks like for this project - the vision or measurable outcome"
    )

    # Agent analysis
    guessed_category: Optional[str] = Field(
        default=None, description="Category the agent guessed before user confirmed"
    )
    generated_story: Optional[str] = Field(
        default=None,
        description="8-sentence story about the project for the Puppy Tales website",
    )


class PuppyTalesSaveOutput(BaseModel):
    """Result of saving a story."""

    success: bool = Field(description="Whether the save succeeded")
    story_id: Optional[str] = Field(default=None, description="Assigned story ID")
    file_path: Optional[str] = Field(
        default=None, description="Path where story was saved"
    )
    message: Optional[str] = Field(default=None, description="Human-readable result")
    error: Optional[str] = Field(default=None, description="Error if save failed")


class PuppyTalesListOutput(BaseModel):
    """Result of listing saved stories."""

    success: bool
    stories: List[dict] = Field(default_factory=list)
    count: int = 0
    error: Optional[str] = None


# =============================================================================
# Helpers
# =============================================================================


def _get_system_username() -> Optional[str]:
    """Get the current system username (works on Mac, Linux, Windows)."""
    try:
        # Try os.getlogin() first (most reliable)
        return os.getlogin()
    except OSError:
        pass

    # Fallback to environment variables
    # Unix/Mac: USER, Linux: LOGNAME, Windows: USERNAME
    for var in ["USER", "LOGNAME", "USERNAME"]:
        username = os.environ.get(var)
        if username:
            return username

    return None


def _get_stories_dir() -> Path:
    """Get the stories directory, creating it if needed."""
    stories_dir = Path.home() / ".code_puppy" / "stories"
    stories_dir.mkdir(parents=True, exist_ok=True)
    return stories_dir


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    # Lowercase and replace spaces/special chars with hyphens
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)  # Collapse multiple hyphens
    slug = slug.strip("-")  # Remove leading/trailing hyphens
    return slug[:50] if slug else "untitled"


def _generate_story_id() -> str:
    """Generate a unique story ID like PUPPY-2026-XXXX."""
    year = datetime.now(timezone.utc).year
    unique_part = uuid.uuid4().hex[:4].upper()
    return f"PUPPY-{year}-{unique_part}"


def _get_api_url() -> str:
    """Get the Puppy Tales API URL.
    
    Priority:
    1. PUPPY_TALES_API_URL environment variable (explicit override)
    2. Local dev server at http://127.0.0.1:8000 (if reachable)
    3. Production URL https://puppy.walmart.com
    """
    # Allow explicit override via environment variable
    if env_url := os.environ.get("PUPPY_TALES_API_URL"):
        return env_url
    
    # Check if local dev server is running
    local_url = "http://127.0.0.1:8000/api/puppy-tales"
    prod_url = "https://puppy.walmart.com/api/puppy-tales"
    
    try:
        with httpx.Client(timeout=1.0) as client:
            # Quick health check on local server
            response = client.get("http://127.0.0.1:8000/api/health", follow_redirects=True)
            if response.status_code == 200:
                return local_url
    except Exception:
        pass  # Local server not available, use production
    
    return prod_url


def _get_auth_token() -> str | None:
    """Get the puppy-token for API auth if available."""
    # Try to get from config or environment
    try:
        from code_puppy.config import get_value
        token = get_value("puppy_token")
        return token or os.environ.get("PUPPY_TOKEN")
    except Exception:
        return os.environ.get("PUPPY_TOKEN")


def _submit_to_api_sync(story_data: dict) -> tuple[bool, str]:
    """Submit story to the Puppy Tales API (synchronous).
    
    Args:
        story_data: The story dict to submit
        
    Returns:
        Tuple of (success, message)
    """
    # Stops tests from pushing to prod puppy pages
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False, "Skipped API submission (test environment)"

    api_url = _get_api_url()
    token = _get_auth_token()
    
    if not token:
        return False, "No puppy-token available for API submission"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(api_url, json=story_data, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                return True, data.get("message", "Story submitted to API!")
            else:
                return False, f"API returned {response.status_code}: {response.text}"
    except Exception as e:
        return False, f"API submission failed: {e}"


# =============================================================================
# Core Functions
# =============================================================================


def puppy_tales_save_story(
    project_name: str,
    project_purpose: str,
    problem_solved: str,
    before_code_puppy: str,
    after_code_puppy: str,
    time_saved: str,
    lessons_learned: str,
    category: str,
    project_type: Optional[str] = None,
    lines_of_code: Optional[int] = None,
    git_commits: Optional[int] = None,
    estimated_dev_hours: Optional[float] = None,
    complexity: Optional[str] = None,
    author_name: Optional[str] = None,
    author_role: Optional[str] = None,
    author_department: Optional[str] = None,
    author_location: Optional[str] = None,
    collaborators: Optional[List[str]] = None,
    success: Optional[str] = None,
    guessed_category: Optional[str] = None,
    generated_story: Optional[str] = None,
) -> PuppyTalesSaveOutput:
    """Save a Code Puppy success story to local storage."""
    try:
        # Generate identifiers
        story_id = _generate_story_id()
        slug = _slugify(project_name)

        # Normalize category
        valid_categories = [
            "reports & dashboards",
            "data cleanup",
            "process automation",
            "email & communication",
            "document creation",
            "research & analysis",
            "training & learning",
            "scheduling & planning",
            "other",
        ]
        category_lower = category.lower().strip()
        if category_lower not in valid_categories:
            category_lower = "other"

        # Normalize complexity
        valid_complexity = ["simple", "medium", "complex"]
        complexity_normalized = None
        if complexity:
            complexity_lower = complexity.lower().strip()
            if complexity_lower in valid_complexity:
                complexity_normalized = complexity_lower

        # Build the story object
        story = PuppyTalesStory(
            story_id=story_id,
            slug=slug,
            project_name=project_name.strip(),
            project_purpose=project_purpose.strip(),
            problem_solved=problem_solved.strip(),
            before_code_puppy=before_code_puppy.strip(),
            after_code_puppy=after_code_puppy.strip(),
            time_saved=time_saved.strip(),
            lessons_learned=lessons_learned.strip(),
            category=category_lower,  # type: ignore
            project_type=project_type.strip() if project_type else None,
            lines_of_code=lines_of_code,
            git_commits=git_commits,
            estimated_dev_hours=estimated_dev_hours,
            complexity=complexity_normalized,  # type: ignore
            submitted_at=datetime.now(timezone.utc).isoformat(),
            submitted_by=_get_system_username(),  # Auto-captured from system
            author_name=author_name.strip() if author_name else None,
            author_role=author_role.strip() if author_role else None,
            author_department=author_department.strip() if author_department else None,
            author_location=author_location.strip() if author_location else None,
            collaborators=[c.strip() for c in collaborators if c.strip()] if collaborators else None,
            success=success.strip() if success else None,
            guessed_category=guessed_category.strip().lower() if guessed_category else None,
            generated_story=generated_story.strip() if generated_story else None,
        )

        # Save to file
        stories_dir = _get_stories_dir()
        file_name = f"{slug}-{story_id.split('-')[-1].lower()}.json"
        file_path = stories_dir / file_name

        file_path.write_text(
            json.dumps(story.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Try to submit to API (graceful failure - local save is primary)
        api_success, api_message = _submit_to_api_sync(story.model_dump())

        return PuppyTalesSaveOutput(
            success=True,
            story_id=story_id,
            file_path=str(file_path),
            message=f"Story '{project_name}' saved successfully!" + (
                " 🌐 Submitted to Puppy Tales!" if api_success else f" (Local only: {api_message})"
            ),
        )

    except Exception as exc:
        return PuppyTalesSaveOutput(
            success=False,
            error=f"Failed to save story: {exc}",
        )


def puppy_tales_list_stories() -> PuppyTalesListOutput:
    """List all saved stories from local storage."""
    try:
        stories_dir = _get_stories_dir()
        stories = []

        for file_path in sorted(stories_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                stories.append(data)
            except (json.JSONDecodeError, IOError):
                continue  # Skip malformed files

        return PuppyTalesListOutput(
            success=True,
            stories=stories,
            count=len(stories),
        )

    except Exception as exc:
        return PuppyTalesListOutput(
            success=False,
            error=f"Failed to list stories: {exc}",
        )


# =============================================================================
# Tool Registration Functions
# =============================================================================


def register_puppy_tales_save_story(agent):
    """Register the puppy_tales_save_story tool with an agent."""
    from pydantic_ai import RunContext

    @agent.tool
    def puppy_tales_save_story_tool(
        context: RunContext,
        project_name: str,
        project_purpose: str,
        problem_solved: str,
        before_code_puppy: str,
        after_code_puppy: str,
        time_saved: str,
        lessons_learned: str,
        category: str,
        project_type: str = "",
        lines_of_code: int = 0,
        git_commits: int = 0,
        estimated_dev_hours: float = 0,
        complexity: str = "",
        author_name: str = "",
        author_role: str = "",
        author_department: str = "",
        author_location: str = "",
        collaborators: str = "",
        success: str = "",  # What success looks like for this project
        guessed_category: str = "",
        generated_story: str = "",
    ) -> PuppyTalesSaveOutput:
        """Save a Code Puppy success story to local storage.

        Call this tool ONLY after collecting all required information
        from the user and getting their confirmation.

        Args:
            context: Run context (injected automatically).
            project_name: Short project name (3-5 words).
            project_purpose: The business problem, goal, or insight they wanted.
            problem_solved: What problem Code Puppy helped solve.
            before_code_puppy: How the task was done before.
            after_code_puppy: How the task is done now with Code Puppy.
            time_saved: Estimated time savings (e.g., "2 hours per week").
            lessons_learned: Tips and advice for others.
            category: One of: reports & dashboards, data cleanup,
                      process automation, email & communication,
                      document creation, research & analysis,
                      training & learning, scheduling & planning, other.
            project_type: Detected project type (e.g., "Python", "JavaScript").
            lines_of_code: Approximate lines of code in the project.
            git_commits: Number of git commits in the project.
            estimated_dev_hours: Estimated development hours from git analysis.
            complexity: Project complexity: "simple", "medium", or "complex".
            author_name: Author's first name (e.g., "Mary").
            author_role: Author's job role (e.g., "Fork Lift Operator").
            author_department: Department (e.g., "Stores", "Tech", "Supply Chain").
            author_location: Store number or location (e.g., "Store #1234").
            collaborators: Comma-separated list of collaborator names.
            success: What success looks like for this project.
            guessed_category: The category YOU guessed before asking the user.
            generated_story: An 8-sentence story about the project for the website.

        Returns:
            PuppyTalesSaveOutput with story_id and file path on success.
        """
        return puppy_tales_save_story(
            project_name=project_name,
            project_purpose=project_purpose,
            problem_solved=problem_solved,
            before_code_puppy=before_code_puppy,
            after_code_puppy=after_code_puppy,
            time_saved=time_saved,
            lessons_learned=lessons_learned,
            category=category,
            project_type=project_type if project_type else None,
            lines_of_code=lines_of_code if lines_of_code else None,
            git_commits=git_commits if git_commits else None,
            estimated_dev_hours=estimated_dev_hours if estimated_dev_hours else None,
            complexity=complexity if complexity else None,
            author_name=author_name if author_name else None,
            author_role=author_role if author_role else None,
            author_department=author_department if author_department else None,
            author_location=author_location if author_location else None,
            collaborators=collaborators.split(",") if collaborators else None,
            success=success if success else None,
            guessed_category=guessed_category if guessed_category else None,
            generated_story=generated_story if generated_story else None,
        )


def register_puppy_tales_list_stories(agent):
    """Register the puppy_tales_list_stories tool with an agent."""
    from pydantic_ai import RunContext

    @agent.tool
    def puppy_tales_list_stories_tool(
        context: RunContext,
    ) -> PuppyTalesListOutput:
        """List all Code Puppy success stories saved locally.

        Args:
            context: Run context (injected automatically).

        Returns:
            PuppyTalesListOutput with list of saved stories.
        """
        return puppy_tales_list_stories()
