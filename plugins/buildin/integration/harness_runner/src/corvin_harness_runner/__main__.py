from __future__ import annotations

import os
import sys

from .runner import main

if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # os._exit: a non-daemon thread of the adapter must never keep a finished run alive.
    os._exit(code)
