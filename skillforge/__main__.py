"""`python3 -m skillforge <command>`."""

from __future__ import annotations

import sys

USAGE = """skillforge <command> [options]

  build      generate one pack per persona, and one per (vertical, persona)
  validate   run every gate against the source and the built packs
  install    install a built pack into Claude Code, Codex or Kiro
  update     rebuild and reapply the selection recorded by install
  sync-harness  synchronize the repository authoring skill for all three coding harnesses
  version    print the version

  python3 -m skillforge sync-harness
  python3 -m skillforge build --all --vertical all
  python3 -m skillforge validate
  python3 -m skillforge install --persona analyst --vertical pci-dss
  python3 -m skillforge update
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    command, rest = args[0], args[1:]
    if command == "build":
        from .build import main as run
    elif command == "validate":
        from .validate import main as run
    elif command == "install":
        from .install import main as run
    elif command == "update":
        from .update import main as run
    elif command == "sync-harness":
        from .harness import main as run
    elif command == "version":
        from . import __version__
        print(__version__)
        return 0
    else:
        print(f"unknown command {command!r}\n\n{USAGE}", file=sys.stderr)
        return 2
    return run(rest)


if __name__ == "__main__":
    raise SystemExit(main())
