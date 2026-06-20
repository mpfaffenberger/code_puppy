"""Status line plugin — a customizable bottom status line for Mist.

Mirrors Claude Code's ``statusLine`` feature: you configure a shell command;
Mist feeds it JSON session data on stdin; whatever the command prints to
stdout becomes your status line (ANSI colors supported).

Configure with the ``/statusline`` command or directly via ``/set``:

    /set statusline_enabled=true
    /set statusline_command=~/.mist/statusline.sh

The command runs throttled in a background thread, so it never blocks the
prompt. Run ``/statusline json`` to see every field your script receives.
"""
