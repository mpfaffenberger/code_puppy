import fnmatch
import hashlib
import os
import time
from pathlib import Path
from typing import Optional, Tuple

from rapidfuzz.distance import JaroWinkler
from rich.console import Console

# Import our queue-based console system
try:
    from code_puppy.messaging import get_queue_console

    # Use queue console by default, but allow fallback
    NO_COLOR = bool(int(os.environ.get("CODE_PUPPY_NO_COLOR", "0")))
    _rich_console = Console(no_color=NO_COLOR)
    console = get_queue_console()
    # Set the fallback console for compatibility
    console.fallback_console = _rich_console
except ImportError:
    # Fallback to regular Rich console if messaging system not available
    NO_COLOR = bool(int(os.environ.get("CODE_PUPPY_NO_COLOR", "0")))
    console = Console(no_color=NO_COLOR)


# -------------------
# Shared ignore patterns/helpers
# -------------------
IGNORE_PATTERNS = [
    # Version control
    "**/.git/**",
    "**/.git",
    ".git/**",
    ".git",
    "**/.svn/**",
    "**/.hg/**",
    "**/.bzr/**",
    # Node.js / JavaScript / TypeScript
    "**/node_modules/**",
    "**/node_modules/**/*.js",
    "node_modules/**",
    "node_modules",
    "**/npm-debug.log*",
    "**/yarn-debug.log*",
    "**/yarn-error.log*",
    "**/pnpm-debug.log*",
    "**/.npm/**",
    "**/.yarn/**",
    "**/.pnpm-store/**",
    "**/coverage/**",
    "**/.nyc_output/**",
    "**/dist/**",
    "**/dist",
    "**/build/**",
    "**/build",
    "**/.next/**",
    "**/.nuxt/**",
    "**/out/**",
    "**/.cache/**",
    "**/.parcel-cache/**",
    "**/.vite/**",
    "**/storybook-static/**",
    "**/*.tsbuildinfo/**",
    # Python
    "**/__pycache__/**",
    "**/__pycache__",
    "__pycache__/**",
    "__pycache__",
    "**/*.pyc",
    "**/*.pyo",
    "**/*.pyd",
    "**/.pytest_cache/**",
    "**/.mypy_cache/**",
    "**/.coverage",
    "**/htmlcov/**",
    "**/.tox/**",
    "**/.nox/**",
    "**/site-packages/**",
    "**/.venv/**",
    "**/.venv",
    "**/venv/**",
    "**/venv",
    "**/env/**",
    "**/ENV/**",
    "**/.env",
    "**/pip-wheel-metadata/**",
    "**/*.egg-info/**",
    "**/dist/**",
    "**/wheels/**",
    "**/pytest-reports/**",
    # Java (Maven, Gradle, SBT)
    "**/target/**",
    "**/target",
    "**/build/**",
    "**/build",
    "**/.gradle/**",
    "**/gradle-app.setting",
    "**/*.class",
    "**/*.jar",
    "**/*.war",
    "**/*.ear",
    "**/*.nar",
    "**/hs_err_pid*",
    "**/.classpath",
    "**/.project",
    "**/.settings/**",
    "**/bin/**",
    "**/project/target/**",
    "**/project/project/**",
    # Go
    "**/vendor/**",
    "**/*.exe",
    "**/*.exe~",
    "**/*.dll",
    "**/*.so",
    "**/*.dylib",
    "**/*.test",
    "**/*.out",
    "**/go.work",
    "**/go.work.sum",
    # Rust
    "**/target/**",
    "**/Cargo.lock",
    "**/*.pdb",
    # Ruby
    "**/vendor/**",
    "**/.bundle/**",
    "**/Gemfile.lock",
    "**/*.gem",
    "**/.rvm/**",
    "**/.rbenv/**",
    "**/coverage/**",
    "**/.yardoc/**",
    "**/doc/**",
    "**/rdoc/**",
    "**/.sass-cache/**",
    "**/.jekyll-cache/**",
    "**/_site/**",
    # PHP
    "**/vendor/**",
    "**/composer.lock",
    "**/.phpunit.result.cache",
    "**/storage/logs/**",
    "**/storage/framework/cache/**",
    "**/storage/framework/sessions/**",
    "**/storage/framework/testing/**",
    "**/storage/framework/views/**",
    "**/bootstrap/cache/**",
    # .NET / C#
    "**/bin/**",
    "**/obj/**",
    "**/packages/**",
    "**/*.cache",
    "**/*.dll",
    "**/*.exe",
    "**/*.pdb",
    "**/*.user",
    "**/*.suo",
    "**/.vs/**",
    "**/TestResults/**",
    "**/BenchmarkDotNet.Artifacts/**",
    # C/C++
    "**/*.o",
    "**/*.obj",
    "**/*.so",
    "**/*.dll",
    "**/*.a",
    "**/*.lib",
    "**/*.dylib",
    "**/*.exe",
    "**/CMakeFiles/**",
    "**/CMakeCache.txt",
    "**/cmake_install.cmake",
    "**/Makefile",
    "**/compile_commands.json",
    "**/.deps/**",
    "**/.libs/**",
    "**/autom4te.cache/**",
    # Perl
    "**/blib/**",
    "**/_build/**",
    "**/Build",
    "**/Build.bat",
    "**/*.tmp",
    "**/*.bak",
    "**/*.old",
    "**/Makefile.old",
    "**/MANIFEST.bak",
    "**/META.yml",
    "**/META.json",
    "**/MYMETA.*",
    "**/.prove",
    # Scala
    "**/target/**",
    "**/project/target/**",
    "**/project/project/**",
    "**/.bloop/**",
    "**/.metals/**",
    "**/.ammonite/**",
    "**/*.class",
    # Elixir
    "**/_build/**",
    "**/deps/**",
    "**/*.beam",
    "**/.fetch",
    "**/erl_crash.dump",
    "**/*.ez",
    "**/doc/**",
    "**/.elixir_ls/**",
    # Swift
    "**/.build/**",
    "**/Packages/**",
    "**/*.xcodeproj/**",
    "**/*.xcworkspace/**",
    "**/DerivedData/**",
    "**/xcuserdata/**",
    "**/*.dSYM/**",
    # Kotlin
    "**/build/**",
    "**/.gradle/**",
    "**/*.class",
    "**/*.jar",
    "**/*.kotlin_module",
    # Clojure
    "**/target/**",
    "**/.lein-**",
    "**/.nrepl-port",
    "**/pom.xml.asc",
    "**/*.jar",
    "**/*.class",
    # Dart/Flutter
    "**/.dart_tool/**",
    "**/build/**",
    "**/.packages",
    "**/pubspec.lock",
    "**/*.g.dart",
    "**/*.freezed.dart",
    "**/*.gr.dart",
    # Haskell
    "**/dist/**",
    "**/dist-newstyle/**",
    "**/.stack-work/**",
    "**/*.hi",
    "**/*.o",
    "**/*.prof",
    "**/*.aux",
    "**/*.hp",
    "**/*.eventlog",
    "**/*.tix",
    # Erlang
    "**/ebin/**",
    "**/rel/**",
    "**/deps/**",
    "**/*.beam",
    "**/*.boot",
    "**/*.plt",
    "**/erl_crash.dump",
    # Common cache and temp directories
    "**/.cache/**",
    "**/cache/**",
    "**/tmp/**",
    "**/temp/**",
    "**/.tmp/**",
    "**/.temp/**",
    "**/logs/**",
    "**/*.log",
    "**/*.log.*",
    # IDE and editor files
    "**/.idea/**",
    "**/.idea",
    "**/.vscode/**",
    "**/.vscode",
    "**/*.swp",
    "**/*.swo",
    "**/*~",
    "**/.#*",
    "**/#*#",
    "**/.emacs.d/auto-save-list/**",
    "**/.vim/**",
    "**/.netrwhist",
    "**/Session.vim",
    "**/.sublime-project",
    "**/.sublime-workspace",
    # OS-specific files
    "**/.DS_Store",
    ".DS_Store",
    "**/Thumbs.db",
    "**/Desktop.ini",
    "**/.directory",
    "**/*.lnk",
    # Common artifacts
    "**/*.orig",
    "**/*.rej",
    "**/*.patch",
    "**/*.diff",
    "**/.*.orig",
    "**/.*.rej",
    # Backup files
    "**/*~",
    "**/*.bak",
    "**/*.backup",
    "**/*.old",
    "**/*.save",
    # Hidden files (but be careful with this one)
    "**/.*",  # Commented out as it might be too aggressive
    # Binary image formats
    "**/*.png",
    "**/*.jpg",
    "**/*.jpeg",
    "**/*.gif",
    "**/*.bmp",
    "**/*.tiff",
    "**/*.tif",
    "**/*.webp",
    "**/*.ico",
    "**/*.svg",
    # Binary document formats
    "**/*.pdf",
    "**/*.doc",
    "**/*.docx",
    "**/*.xls",
    "**/*.xlsx",
    "**/*.ppt",
    "**/*.pptx",
    # Archive formats
    "**/*.zip",
    "**/*.tar",
    "**/*.gz",
    "**/*.bz2",
    "**/*.xz",
    "**/*.rar",
    "**/*.7z",
    # Media files
    "**/*.mp3",
    "**/*.mp4",
    "**/*.avi",
    "**/*.mov",
    "**/*.wmv",
    "**/*.flv",
    "**/*.wav",
    "**/*.ogg",
    # Font files
    "**/*.ttf",
    "**/*.otf",
    "**/*.woff",
    "**/*.woff2",
    "**/*.eot",
    # Other binary formats
    "**/*.bin",
    "**/*.dat",
    "**/*.db",
    "**/*.sqlite",
    "**/*.sqlite3",
]


def should_ignore_path(path: str) -> bool:
    """Return True if *path* matches any pattern in IGNORE_PATTERNS."""
    # Convert path to Path object for better pattern matching
    path_obj = Path(path)

    for pattern in IGNORE_PATTERNS:
        # Try pathlib's match method which handles ** patterns properly
        try:
            if path_obj.match(pattern):
                return True
        except ValueError:
            # If pathlib can't handle the pattern, fall back to fnmatch
            if fnmatch.fnmatch(path, pattern):
                return True

        # Additional check: if pattern contains **, try matching against
        # different parts of the path to handle edge cases
        if "**" in pattern:
            # Convert pattern to handle different path representations
            simplified_pattern = pattern.replace("**/", "").replace("/**", "")

            # Check if any part of the path matches the simplified pattern
            path_parts = path_obj.parts
            for i in range(len(path_parts)):
                subpath = Path(*path_parts[i:])
                if fnmatch.fnmatch(str(subpath), simplified_pattern):
                    return True
                # Also check individual parts
                if fnmatch.fnmatch(path_parts[i], simplified_pattern):
                    return True

    return False


def _find_best_window(
    haystack_lines: list[str],
    needle: str,
) -> Tuple[Optional[Tuple[int, int]], float]:
    """
    Return (start, end) indices of the window with the highest
    Jaro-Winkler similarity to `needle`, along with that score.
    If nothing clears JW_THRESHOLD, return (None, score).
    """
    needle = needle.rstrip("\n")
    needle_lines = needle.splitlines()
    win_size = len(needle_lines)
    best_score = 0.0
    best_span: Optional[Tuple[int, int]] = None
    best_window = ""
    # Pre-join the needle once; join windows on the fly
    for i in range(len(haystack_lines) - win_size + 1):
        window = "\n".join(haystack_lines[i : i + win_size])
        score = JaroWinkler.normalized_similarity(window, needle)
        if score > best_score:
            best_score = score
            best_span = (i, i + win_size)
            best_window = window

    console.log(f"Best span: {best_span}")
    console.log(f"Best window: {best_window}")
    console.log(f"Best score: {best_score}")
    return best_span, best_score


def generate_group_id(tool_name: str, extra_context: str = "") -> str:
    """Generate a unique group_id for tool output grouping.

    Args:
        tool_name: Name of the tool (e.g., 'list_files', 'edit_file')
        extra_context: Optional extra context to make group_id more unique

    Returns:
        A string in format: tool_name_hash
    """
    # Create a unique identifier using timestamp, context, and a random component
    import random

    timestamp = str(int(time.time() * 1000000))  # microseconds for more uniqueness
    random_component = random.randint(1000, 9999)  # Add randomness
    context_string = f"{tool_name}_{timestamp}_{random_component}_{extra_context}"

    # Generate a short hash
    hash_obj = hashlib.md5(context_string.encode())
    short_hash = hash_obj.hexdigest()[:8]

    return f"{tool_name}_{short_hash}"
