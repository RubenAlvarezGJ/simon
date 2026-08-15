"""Make the project root importable during tests.

Production code imports as ``from src.cv_layer...`` while ``pytest.ini`` sets
``pythonpath = src`` for ``from cv_layer...`` imports. CLAUDE.md requires both
styles keep working; this bridges them so a bare ``pytest`` run behaves the same
as ``python -m pytest``.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
