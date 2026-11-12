"""Headless single-turn CorvinOS runner for benchmark harnesses (Harbor adapter side)."""
from __future__ import annotations

__version__ = "0.1.0"

# Exit-code contract with the Harbor adapter. A gate refusal (2) is a REAL result:
# it is never mapped to 0 and never retried.
EXIT_COMPLETED = 0
EXIT_REFUSED = 2
EXIT_ENGINE_ERROR = 3
EXIT_TIMEOUT = 4
EXIT_USAGE = 64
