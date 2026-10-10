"""Business Intel Agent package."""
import sys
from pathlib import Path

_agent_root = str(Path(__file__).resolve().parent.parent)
if _agent_root not in sys.path:
    sys.path.insert(0, _agent_root)

__version__ = "0.1.0"
