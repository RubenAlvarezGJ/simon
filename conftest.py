"""Make the project root importable during tests.

This repository uses two import styles. Production modules import each other
fully qualified (``from src.cv_layer...``), while tests import via the package
name alone (``from cv_layer...``). Both must resolve in a single test run.

``pytest.ini``'s ``pythonpath = src`` covers the second style. Putting the
project root on ``sys.path`` here covers the first, so ``pytest`` and
``python -m pytest`` behave identically.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
