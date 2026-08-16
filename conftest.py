"""Make the project root importable during tests.

``pytest.ini``'s ``pythonpath = src`` covers modules under ``src/``, but
``server.py`` lives at the project root, so tests that import it need the root
on ``sys.path`` as well. Doing it here rather than in ``pytest.ini`` keeps it
working from a clean checkout, since ``pytest.ini`` is not tracked.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
