#!/usr/bin/env bash
# pretty_path.sh - Display PATH environment variable in a readable format

# Print header
echo "=== PATH Environment Variable ==="
echo "Directories listed in order, duplicates marked"

# Initialize an array to track seen directories
declare -A seen_dirs

# Counter for position in PATH
count=1

# Process each directory in PATH
echo -e "\nPATH entries:"
IFS=':' read -ra path_dirs <<< "$PATH"
for dir in "${path_dirs[@]}"; do
  # Check if we've seen this directory before
  if [[ -n "${seen_dirs[$dir]}" ]]; then
    echo "  $count: $dir (duplicate, first seen at position ${seen_dirs[$dir]})"
  else
    echo "  $count: $dir"
    # Record the position where we first saw this directory
    seen_dirs[$dir]=$count
  fi
  ((count++))
done

# Print summary statistics
echo -e "\n=== Summary ==="
echo "Total PATH entries: ${#path_dirs[@]}"
echo "Unique directories: ${#seen_dirs[@]}"
echo "Duplicate entries: $((${#path_dirs[@]} - ${#seen_dirs[@]}))"

# Check for non-existent directories
echo -e "\n=== Path Validation ==="
for dir in "${!seen_dirs[@]}"; do
  if [[ ! -d "$dir" ]]; then
    echo "WARNING: Directory does not exist: $dir"
  fi
done

# Executable check - find the first directory containing common executables
echo -e "\n=== Common Executables Location ==="
common_exes=("python" "pip" "node" "npm" "git" "uv")
for exe in "${common_exes[@]}"; do
  path_to_exe=$(which "$exe" 2>/dev/null)
  if [[ -n "$path_to_exe" ]]; then
    echo "$exe: $path_to_exe"
  else
    echo "$exe: Not found in PATH"
  fi
done
