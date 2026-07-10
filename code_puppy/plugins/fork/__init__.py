"""Fork plugin.

``/fork [@agent] <prompt>`` spawns a sub-agent as a background asyncio
task -- usable at the idle prompt or mid-run -- and reports the result
when it lands. ``/forks`` lists fork status; ``/fork cancel <id>`` stops
a running fork.
"""
