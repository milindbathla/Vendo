"""
Models package for Small Business Simulator
"""
from src.models.business import BusinessProfile
from src.models.customer import CustomerState, ChannelConfig
from src.models.inventory import InventoryState, PendingDelivery
from src.models.simulation import DailyMetric, SimulationResult

from src.models.adaptive_profile import (
    AdaptiveBusinessProfile,
    BusinessFact,
    FactStatus,
    FactSource,
)

__all__ = [
    "BusinessProfile",
    "CustomerState",
    "ChannelConfig",
    "InventoryState",
    "PendingDelivery",
    "DailyMetric",
    "SimulationResult",
    "AdaptiveBusinessProfile",
    "BusinessFact",
    "FactStatus",
    "FactSource",
    "EmailAddress",
    "EmailAttachment",
    "InboundEmail",
    "IngestionStatus",
    "TaskState",
    "ActionType",
    "PolicyDecision",
    "ActionProposal",
    "OperationalTask",
    "compute_payload_hash",
]

from src.models.email import (
    EmailAddress,
    EmailAttachment,
    InboundEmail,
    IngestionStatus,
)
from src.models.task import (
    TaskState,
    ActionType,
    PolicyDecision,
    ActionProposal,
    OperationalTask,
    compute_payload_hash,
)
