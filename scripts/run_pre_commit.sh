#!/usr/bin/env bash
#==========================================================================
# run_pre_commit.sh
#==========================================================================
# DESCRIPTION:
#   This script runs pre-commit hooks in a loop until they all pass,
#   handling cases where pre-commit fixes issues that reveal new issues.
#   It automatically handles iterative fixes (e.g., formatter fixes code
#   that then fails linting) and eliminates manual re-runs.
#
# USAGE:
#   ./scripts/run_pre_commit.sh
#
# OUTPUT:
#   - Progress updates with attempt numbers
#   - Pre-commit hook output for each attempt
#   - Success message when all hooks pass
#   - Clear indication of failures and retries
#
# USE CASES:
#   - Before committing changes to ensure all pre-commit hooks pass
#   - After making large code changes that might trigger multiple fixes
#   - When setting up pre-commit hooks for the first time on existing code
#   - As part of development workflow to maintain code quality
#
# HOW IT WORKS:
#   1. Runs 'uv --native-tls run pre-commit run --all-files'
#   2. If hooks fail (non-zero exit), waits 1 second and tries again
#   3. Continues looping until all hooks pass (exit code 0)
#   4. Provides helpful feedback and celebrates success
#==========================================================================

set -e  # Exit on any error except for our expected pre-commit failures

echo "🐶 Starting pre-commit loop - I'll keep running until everything is clean!"
echo "Running: uv --native-tls run pre-commit run --all-files"
echo ""

attempt=1

while true; do
    echo "🔄 Attempt #$attempt"

    # Run pre-commit and capture exit code
    set +e  # Temporarily disable exit on error
    uv --native-tls run pre-commit run --all-files
    exit_code=$?
    set -e  # Re-enable exit on error

    if [ $exit_code -eq 0 ]; then
        echo ""
        echo "✅ Success! Pre-commit passed on attempt #$attempt"
        echo "🎉 All hooks are happy now!"
        break
    else
        echo ""
        echo "❌ Pre-commit failed with exit code $exit_code on attempt #$attempt"
        echo "🔧 Don't worry, I'll try again! (This is normal when hooks fix issues)"
        echo ""
        ((attempt++))

        # Add a small delay to be nice
        sleep 1
    fi
done

echo "🐕 Woof! All done. Your code is squeaky clean!"
