import os
from typing import List, Set, Dict, Any
from pydantic_ai import RunContext

def register_puppy_file_size_checker(agent):
    @agent.tool
    def check_code_file_size(
        context: RunContext,
        root_dir: str = '.',
        included_extensions: List[str] = ['.py', '.js', '.ts', '.tsx', '.jsx'],
        excluded_dirs: List[str] = ['.git', '.venv', '__pycache__', '.pytest_cache'],
        warning_threshold: int = 500,
        fatal_threshold: int = 600
    ) -> Dict[str, Any]:
        """
        Scan code files for line count, barking if any reach the warning or fatal threshold.
        Returns lists of 'warners' (>warning_threshold) and 'offenders' (>=fatal_threshold).
        """
        warners = []
        offenders = []
        included_exts = set(map(str.lower, included_extensions))
        excluded_dirs_set = set(excluded_dirs)
        def should_check_file(file_path):
            _, ext = os.path.splitext(file_path)
            if ext.lower() not in included_exts:
                return False
            split_path = set(file_path.split(os.sep))
            if excluded_dirs_set & split_path:
                return False
            return True
        def get_code_files(root_dir: str):
            for dirpath, dirnames, filenames in os.walk(root_dir):
                dirnames[:] = [d for d in dirnames if d not in excluded_dirs_set]
                for filename in filenames:
                    rel_dir = os.path.relpath(dirpath, root_dir)
                    rel_file = os.path.join(rel_dir, filename) if rel_dir != '.' else filename
                    if should_check_file(rel_file):
                        yield os.path.join(dirpath, filename)
        def check_file_length(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return len(f.readlines())
            except Exception:
                return None
        for file_path in get_code_files(root_dir):
            count = check_file_length(file_path)
            if count is None:
                continue
            if count >= fatal_threshold:
                offenders.append({'file': file_path, 'lines': count})
            elif count >= warning_threshold:
                warners.append({'file': file_path, 'lines': count})
        return {
            'success': True,
            'warners': warners,
            'offenders': offenders,
            'summary': (
                f"{len(warners)} files approaching limit, "
                f"{len(offenders)} files exceeding {fatal_threshold} lines."
            )
        }
