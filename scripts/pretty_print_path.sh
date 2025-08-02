#!/usr/bin/env bash
#==========================================================================
# pretty_print_path.sh
#==========================================================================
# DESCRIPTION:
#   This script displays the PATH environment variable in a readable format,
#   making it easier to debug PATH-related issues. It shows all directories
#   in PATH with their position, highlights duplicates, validates directory
#   existence, and locates common executables.
#
# USAGE:
#   ./scripts/pretty_print_path.sh
#
# OUTPUT:
#   - A numbered list of all PATH entries
#   - Duplicate entries with their first occurrence position
#   - Summary statistics (total, unique, duplicates)
#   - Warnings for non-existent directories
#   - Locations of common executables (python, pip, node, npm, git, uv)
#
# USE CASES:
#   - When troubleshooting environment setup issues
#   - When suspecting PATH conflicts or incorrect ordering
#   - To verify which versions of tools are being used
#   - During development environment configuration
#==========================================================================

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
common_exes=("python" "pip" "node" "npm" "pnpm" "bun" "git" "uv" "poetry")
for exe in "${common_exes[@]}"; do
  path_to_exe=$(which "$exe" 2>/dev/null)
  if [[ -n "$path_to_exe" ]]; then
    echo "$exe: $path_to_exe"
  else
    echo "$exe: Not found in PATH"
  fi
done
