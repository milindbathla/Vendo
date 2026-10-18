"""
Adaptive Business Profile and Fact Provenance Models
=====================================================
Represents dynamically learned business profiles for ANY MSME vertical.
Tracks fact confidence, status (confirmed, assumed, unknown, outdated),
provenance (user_stated, inferred, external_api, system_default),
and business-specific attributes.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import time
from typing import Any, Dict, List, Optional

from src.models.business import BusinessProfile


class FactStatus(str, Enum):
    CONFIRMED = "confirmed"    # Explicitly stated or verified by user
    ASSUMED = "assumed"        # Inferred by system with reasonable default
    UNKNOWN = "unknown"        # Required or relevant, but missing
    OUTDATED = "outdated"      # Previously confirmed, but superseded or flagged for review


class FactSource(str, Enum):
    USER_STATED = "user_stated"          # Direct user conversation
    INFERRED = "inferred"                # Inferred from context or domain archetype
    EXTERNAL_API = "external_api"        # Retrieved from Places, Zoho, etc.
    SYSTEM_DEFAULT = "system_default"    # Baseline platform fallback


@dataclass
class BusinessFact:
    """Atomic tracked piece of business information with full provenance."""
    key: str
    value: Any
    value_type: str = "str"  # "float", "int", "str", "list", "dict", "bool"
    status: FactStatus = FactStatus.UNKNOWN
    source: FactSource = FactSource.USER_STATED
    confidence: float = 1.0  # 0.0 to 1.0
    notes: str = ""
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    # In-memory structured correction history.  Persisted inside the notes column
    # as a JSON suffix so no schema migration is needed.
    correction_log: List[Dict[str, Any]] = field(default_factory=list)

    # Sentinel used to embed correction log in the notes column
    _LOG_SENTINEL: str = field(default="||HISTORY:", init=False, repr=False, compare=False)

    def record_correction(self, old_value: Any, old_notes: str, new_value: Any = None) -> None:
        """Appends an entry to the in-memory correction log."""
        val = new_value if new_value is not None else self.value
        self.correction_log.append({
            "old_value": old_value,
            "new_value": val,
            "replacement_value": val,
            "replaced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "old_notes": old_notes,
        })

    def encode_notes_with_history(self) -> str:
        """Returns the notes string with correction log embedded as JSON suffix."""
        base = self._split_notes()[0]
        if not self.correction_log:
            return base
        return base + "||HISTORY:" + json.dumps(self.correction_log)

    def _split_notes(self) -> tuple:
        """Splits raw notes into (human_part, log_list)."""
        sentinel = "||HISTORY:"
        if sentinel in self.notes:
            idx = self.notes.index(sentinel)
            human = self.notes[:idx]
            try:
                log = json.loads(self.notes[idx + len(sentinel):])
            except Exception:
                log = []
            return human, log
        return self.notes, []

    def __post_init__(self) -> None:
        """Deserialise correction_log from notes if loading from DB."""
        human, log = self._split_notes()
        if not self.correction_log and log:
            self.correction_log = log
        self.notes = human

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "value_type": self.value_type,
            "status": self.status.value if isinstance(self.status, FactStatus) else str(self.status),
            "source": self.source.value if isinstance(self.source, FactSource) else str(self.source),
            "confidence": self.confidence,
            "notes": self._split_notes()[0],  # expose only human-readable part
            "correction_log": self.correction_log,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BusinessFact":
        inst = cls(
            key=data["key"],
            value=data.get("value"),
            value_type=data.get("value_type", "str"),
            status=FactStatus(data.get("status", "unknown")),
            source=FactSource(data.get("source", "user_stated")),
            confidence=float(data.get("confidence", 1.0)),
            notes=data.get("notes", ""),
            updated_at=data.get("updated_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            correction_log=data.get("correction_log", []),
        )
        return inst


@dataclass
class AdaptiveBusinessProfile:
    """
    Extensible business profile that can represent ANY business vertical.
    Does not assume a specific recipe, menu, or fixed retail schema.
    """
    business_id: str
    display_name: str
    category: str  # e.g. "electronics_repair", "salon_services", "retail_kirana", "home_tiffin"
    description: str = ""
    city: str = "Kanpur"
    state: str = "Uttar Pradesh"
    currency: str = "INR"
    onboarding_completed: bool = False
    facts: Dict[str, BusinessFact] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    updated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def get_fact(self, key: str) -> Optional[BusinessFact]:
        return self.facts.get(key)

    def get_value(self, key: str, default: Any = None) -> Any:
        fact = self.facts.get(key)
        if fact is None or fact.status == FactStatus.UNKNOWN:
            return default
        return fact.value

    def is_confirmed(self, key: str) -> bool:
        fact = self.facts.get(key)
        return fact is not None and fact.status == FactStatus.CONFIRMED

    def set_fact(
        self,
        key: str,
        value: Any,
        status: FactStatus = FactStatus.CONFIRMED,
        source: FactSource = FactSource.USER_STATED,
        confidence: float = 1.0,
        notes: str = "",
    ) -> BusinessFact:
        val_type = type(value).__name__
        fact = BusinessFact(
            key=key,
            value=value,
            value_type=val_type,
            status=status,
            source=source,
            confidence=confidence,
            notes=notes,
            updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self.facts[key] = fact
        self.updated_at = fact.updated_at
        return fact

    def to_dict(self) -> Dict[str, Any]:
        return {
            "business_id": self.business_id,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "city": self.city,
            "state": self.state,
            "currency": self.currency,
            "onboarding_completed": self.onboarding_completed,
            "facts": {k: f.to_dict() for k, f in self.facts.items()},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdaptiveBusinessProfile":
        facts_dict = {}
        if "facts" in data and isinstance(data["facts"], dict):
            for k, f_data in data["facts"].items():
                facts_dict[k] = BusinessFact.from_dict(f_data)

        return cls(
            business_id=data["business_id"],
            display_name=data.get("display_name", data["business_id"]),
            category=data.get("category", "general_business"),
            description=data.get("description", ""),
            city=data.get("city", "Kanpur"),
            state=data.get("state", "Uttar Pradesh"),
            currency=data.get("currency", "INR"),
            onboarding_completed=bool(data.get("onboarding_completed", False)),
            facts=facts_dict,
            created_at=data.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            updated_at=data.get("updated_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        )

    def to_standard_business_profile(self) -> BusinessProfile:
        """
        Projects adaptive facts into the existing simulator's BusinessProfile
        interface, providing sensible domain-agnostic fallback defaults
        for missing fields while preserving confirmed facts.
        """
        selling_price = float(self.get_value("selling_price", 100.0))
        unit_cost = float(self.get_value("supplier_unit_cost", self.get_value("material_cost", 40.0)))
        capacity = float(self.get_value("daily_capacity", 30.0))
        starting_capital = float(self.get_value("cash_balance", self.get_value("starting_capital", 10000.0)))
        starting_inventory = float(self.get_value("current_inventory", self.get_value("starting_inventory", 20.0)))
        daily_fixed_cost = float(self.get_value("daily_fixed_cost", 200.0))
        base_demand = float(self.get_value("base_daily_demand", self.get_value("daily_customers", 15.0)))
        lead_time = int(self.get_value("procurement_lead_time_days", 1))

        return BusinessProfile(
            business_type=self.business_id,
            display_name=self.display_name,
            description=self.description,
            starting_capital=starting_capital,
            starting_inventory=starting_inventory,
            daily_capacity=capacity,
            supplier_unit_cost=unit_cost,
            bulk_order_threshold=float(self.get_value("bulk_order_threshold", 100.0)),
            bulk_discount=float(self.get_value("bulk_discount", 0.05)),
            procurement_lead_time_days=lead_time,
            min_order_quantity=float(self.get_value("min_order_quantity", 10.0)),
            selling_price=selling_price,
            daily_fixed_cost=daily_fixed_cost,
            variable_cost_per_unit=float(self.get_value("variable_cost_per_unit", 10.0)),
            delivery_cost_per_unit=float(self.get_value("delivery_cost_per_unit", 0.0)),
            platform_commission_rate=float(self.get_value("platform_commission_rate", 0.0)),
            base_daily_demand=base_demand,
            demand_variability=float(self.get_value("demand_variability", 0.15)),
            daily_marketing_spend=float(self.get_value("daily_marketing_spend", 50.0)),
            acquisition_cost_per_customer=float(self.get_value("acquisition_cost_per_customer", 100.0)),
            customer_conversion_rate=float(self.get_value("customer_conversion_rate", 0.20)),
            customer_retention_rate=float(self.get_value("customer_retention_rate", 0.85)),
            daily_repeat_order_probability=float(self.get_value("daily_repeat_order_probability", 0.30)),
            daily_wastage_rate=float(self.get_value("daily_wastage_rate", 0.02)),
            reorder_point=float(self.get_value("reorder_point", 20.0)),
            target_inventory=float(self.get_value("target_inventory", 50.0)),
            receivables_delay_days=int(self.get_value("receivables_delay_days", 0)),
        )
