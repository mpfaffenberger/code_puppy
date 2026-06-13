"""Paw-sign plugin.

Appends a playful puppy-themed signature to commit messages that
code-puppy composes, so the audience knows the commit came from a very
good boy. Intercepts ``git commit -m`` shell commands via the
``pre_tool_call`` hook and tacks on an extra ``-m`` paragraph.
"""
