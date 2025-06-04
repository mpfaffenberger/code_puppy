import os

EXCLUDED_DIRS = {'.git', '.venv', '__pycache__', '.pytest_cache'}
INCLUDED_EXTENSIONS = {'.py', '.js', '.ts', '.tsx', '.jsx'}
LINE_LIMIT = 600
WARNING_THRESHOLD = 500  # When to start yappin'
FATAL_THRESHOLD = 600    # When puppy howls


def should_check_file(file_path):
    _, ext = os.path.splitext(file_path)
    if ext.lower() not in INCLUDED_EXTENSIONS:
        return False
    split_path = set(file_path.split(os.sep))
    if EXCLUDED_DIRS & split_path:
        return False
    return True

def get_code_files(root_dir='.'):    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Don't descend into excluded dirs
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for filename in filenames:
            rel_dir = os.path.relpath(dirpath, root_dir)
            rel_file = os.path.join(rel_dir, filename) if rel_dir != '.' else filename
            if should_check_file(rel_file):
                yield os.path.join(dirpath, filename)

def check_file_length(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            line_count = len(lines)
            return line_count
    except (UnicodeDecodeError, OSError) as e:
        print(f"(Skipping unreadable file) {file_path}: {e}")
        return None

def main():
    offenders = []
    warners = []
    print(f"\n🐶 Code Puppy File Size Checker (Zen Approved)\n{'=' * 40}")
    for file_path in get_code_files('.'):
        count = check_file_length(file_path)
        if count is None:
            continue
        if count >= FATAL_THRESHOLD:
            offenders.append((file_path, count))
        elif count >= WARNING_THRESHOLD:
            warners.append((file_path, count))
    if warners:
        print("\n⚠️  Warning! These files are getting a little chonky (over 500 lines):")
        for file_path, count in warners:
            print(f"  🐾 {file_path} — {count} lines")
    if offenders:
        print("\n🚨 PUPPY HOWL! Files over 600 lines found:")
        for file_path, count in offenders:
            print(f"  🐶 {file_path} — {count} lines (SPLIT ME!!!)")
    if not (warners or offenders):
        print("\n✨ All code files are fit, healthy, and zen!")

if __name__ == '__main__':
    main()
