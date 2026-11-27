"""Preview the splash scenes: ``python -m code_puppy.splash [SCENE ...]``."""

from __future__ import annotations

import argparse
import time

from code_puppy.splash import SCENES, Splash


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m code_puppy.splash", description=__doc__
    )
    parser.add_argument("scenes", nargs="*", metavar="SCENE", help=", ".join(SCENES))
    parser.add_argument("--seconds", type=float, default=5.0)
    args = parser.parse_args(argv)
    # Not `choices=`: on Python 3.11 argparse checks the empty default of
    # `nargs="*"` against the choices too, and refuses a bare preview.
    unknown = sorted(set(args.scenes) - set(SCENES))
    if unknown:
        parser.error(
            f"unknown scene {', '.join(unknown)}; pick from {', '.join(SCENES)}"
        )
    for name in args.scenes or SCENES:
        splash = Splash(scene=SCENES[name])
        splash.start()
        try:
            time.sleep(args.seconds)
        finally:
            splash.stop()
        print(name)


if __name__ == "__main__":
    main()
