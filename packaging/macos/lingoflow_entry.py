"""PyInstaller entrypoint for the macOS app bundle."""

import sys
from pathlib import Path


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-check":
        from lingoflow.diagnostics import run

        run(Path(sys.argv[2]).resolve())
    else:
        from lingoflow.app import main

        main()
