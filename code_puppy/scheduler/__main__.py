"""Entry point for running scheduler daemon directly.

Usage: python -m code_puppy.scheduler
"""

from code_puppy.scheduler.daemon import start_daemon

if __name__ == "__main__":
    start_daemon(foreground=True)
