"""Steer/queue plugin.

Mid-run submissions now QUEUE by default (run as the next turn); this
plugin provides the escape hatches and the management UI:

* ``/steer <text>`` -- inject guidance mid-turn (the old default).
* ``/queue`` -- TUI to view / add / edit / delete queued prompts,
  available at idle and mid-run alike.
* ``(N queued)`` -- live count on the bottom bar's status row.
"""
