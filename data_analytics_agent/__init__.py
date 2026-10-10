"""Data Analytics Agent (Business Intel Agent) package."""
import sys
from pathlib import Path

_agent_root = str(Path(__file__).resolve().parent)
if _agent_root not in sys.path:
    sys.path.insert(0, _agent_root)

from business_intel.agents.business_intel_agent import BusinessIntelAgent
from business_intel.specialist import BusinessIntelSpecialistAgent

__all__ = ["BusinessIntelAgent", "BusinessIntelSpecialistAgent"]
__version__ = "0.1.0"
