"""Destructive command guard plugin.

Intercepts potentially-destructive shell commands and prompts the user for
approval before allowing them through. Always active, pure regex, no LLM calls.

Covers:
- Unix/Linux: rm -rf /, rm -rf ~, rm -rf /*, rm -rf ~/*
- Cross-platform (git, docker, npm/yarn, twine, SQL clients):
  git push --mirror, git clean -fd, git reset --hard, git checkout/restore .,
  DROP via SQL client, docker prune, npm/yarn publish, twine upload
- Windows PowerShell: Remove-Item -Recurse -Force, Format-Volume, Clear-Disk,
  Remove-ItemProperty, Clear-RecycleBin, irm | iex (remote code execution)
- Windows CMD: rd /s /q, del /s system files, format, diskpart, bcdedit, reg delete
"""
