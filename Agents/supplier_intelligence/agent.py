"""
Supplier Intelligence Agent
============================
Evaluates suppliers and maintains supplier relationships for Indian
micro-enterprises. Provides profiling, comparison, history tracking,
evaluation scoring, and record updates.

Tools provided:
  - get_supplier_profile()       → Full profile for a specific supplier
  - compare_suppliers()          → Side-by-side comparison of two suppliers
  - get_supplier_history()       → Past transaction history with a supplier
  - evaluate_supplier()          → Score a supplier across quality/cost/speed
  - update_supplier_record()     → Persist updated supplier info or rating

Design follows the same dataclass + class pattern as SupplierCatalogueSimulator.
All data is deterministic / in-memory for hackathon demonstration purposes.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime


SIMULATION_NOTICE = (
    "Supplier Intelligence Agent — deterministic in-memory data. "
    "For hackathon demonstration only. Not connected to live supplier APIs."
)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class SupplierProfile:
    """Complete profile for a known supplier."""
    supplier_id: str
    name: str
    type: str                       # wholesale / express / local
    location: str
    contact_person: str
    contact_phone: str
    categories: List[str]           # ingredient categories supplied
    min_order_value: float          # Rs
    avg_lead_time_days: float
    payment_terms: str              # e.g. "COD", "Net-7", "Credit-14"
    rating: float                   # 0–5 composite score
    is_verified: bool
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supplier_id": self.supplier_id,
            "name": self.name,
            "type": self.type,
            "location": self.location,
            "contact_person": self.contact_person,
            "contact_phone": self.contact_phone,
            "categories": self.categories,
            "min_order_value": self.min_order_value,
            "avg_lead_time_days": self.avg_lead_time_days,
            "payment_terms": self.payment_terms,
            "rating": self.rating,
            "is_verified": self.is_verified,
            "notes": self.notes,
        }


@dataclass
class SupplierHistoryRecord:
    """Single past transaction with a supplier."""
    transaction_id: str
    supplier_id: str
    date: str                       # ISO-8601 date string
    items_ordered: Dict[str, float] # ingredient -> qty ordered
    total_amount: float             # Rs
    actual_lead_time_days: float
    quality_rating: float           # 0–5
    quantity_accuracy: float        # 0–1 (1 = exactly as ordered)
    delivery_on_time: bool
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "supplier_id": self.supplier_id,
            "date": self.date,
            "items_ordered": self.items_ordered,
            "total_amount": round(self.total_amount, 2),
            "actual_lead_time_days": self.actual_lead_time_days,
            "quality_rating": self.quality_rating,
            "quantity_accuracy": self.quantity_accuracy,
            "delivery_on_time": self.delivery_on_time,
            "notes": self.notes,
        }


@dataclass
class SupplierEvaluation:
    """Composite evaluation score for a supplier."""
    supplier_id: str
    supplier_name: str
    quality_score: float        # 0–10
    cost_score: float           # 0–10 (lower cost = higher score)
    speed_score: float          # 0–10 (faster = higher score)
    reliability_score: float    # 0–10 (on-time rate + qty accuracy)
    relationship_score: float   # 0–10 (tenure + repeat business)
    composite_score: float      # Weighted average 0–10
    recommendation: str         # "preferred", "acceptable", "review", "avoid"
    insights: List[str]
    simulation_notice: str = SIMULATION_NOTICE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "scores": {
                "quality": round(self.quality_score, 2),
                "cost": round(self.cost_score, 2),
                "speed": round(self.speed_score, 2),
                "reliability": round(self.reliability_score, 2),
                "relationship": round(self.relationship_score, 2),
                "composite": round(self.composite_score, 2),
            },
            "recommendation": self.recommendation,
            "insights": self.insights,
            "simulation_notice": self.simulation_notice,
        }


@dataclass
class SupplierComparison:
    """Head-to-head comparison of two suppliers."""
    supplier_a: SupplierProfile
    supplier_b: SupplierProfile
    evaluation_a: SupplierEvaluation
    evaluation_b: SupplierEvaluation
    winner: str                    # supplier_id of recommended choice
    winner_reason: str
    cost_difference_pct: float     # % cheaper for a standard basket
    speed_difference_days: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supplier_a": self.supplier_a.to_dict(),
            "supplier_b": self.supplier_b.to_dict(),
            "evaluation_a": self.evaluation_a.to_dict(),
            "evaluation_b": self.evaluation_b.to_dict(),
            "winner_supplier_id": self.winner,
            "winner_reason": self.winner_reason,
            "cost_difference_pct": round(self.cost_difference_pct, 2),
            "speed_difference_days": round(self.speed_difference_days, 2),
            "simulation_notice": SIMULATION_NOTICE,
        }


# ---------------------------------------------------------------------------
# Supplier Intelligence Agent
# ---------------------------------------------------------------------------

class SupplierIntelligenceAgent:
    """
    Evaluates suppliers and maintains supplier relationships.

    Deterministic supplier profiles and transaction history are seeded
    in-memory for hackathon demonstration purposes.
    """

    # ------------------------------------------------------------------
    # Seeded supplier directory
    # ------------------------------------------------------------------
    _SUPPLIER_DIRECTORY: Dict[str, SupplierProfile] = {
        "wholesale_mandi": SupplierProfile(
            supplier_id="wholesale_mandi",
            name="Metro Wholesale Mandi",
            type="wholesale",
            location="Azadpur Mandi, Delhi",
            contact_person="Ramesh Gupta",
            contact_phone="+91-98101-23456",
            categories=["rice", "dal", "cooking_oil", "spices", "containers"],
            min_order_value=500.0,
            avg_lead_time_days=1.0,
            payment_terms="COD",
            rating=4.2,
            is_verified=True,
            notes="Reliable bulk supplier. Best rates above Rs 1000 order.",
        ),
        "kirana_express": SupplierProfile(
            supplier_id="kirana_express",
            name="Local Kirana Express (Rapid 2-Hour)",
            type="express",
            location="Lajpat Nagar, Delhi",
            contact_person="Sunita Mehta",
            contact_phone="+91-99871-65432",
            categories=["rice", "dal", "cooking_oil", "containers", "vegetables"],
            min_order_value=100.0,
            avg_lead_time_days=0.08,  # ~2 hours
            payment_terms="COD",
            rating=3.9,
            is_verified=True,
            notes="Premium pricing but fast. Use for emergency restocking only.",
        ),
        "agro_fresh_farms": SupplierProfile(
            supplier_id="agro_fresh_farms",
            name="AgroFresh Farms Direct",
            type="local",
            location="Ghaziabad, UP",
            contact_person="Deepak Yadav",
            contact_phone="+91-93456-78901",
            categories=["vegetables", "fruits", "dairy"],
            min_order_value=300.0,
            avg_lead_time_days=1.5,
            payment_terms="Net-7",
            rating=4.5,
            is_verified=True,
            notes="Best quality fresh produce. Requires minimum 1-day advance booking.",
        ),
    }

    # ------------------------------------------------------------------
    # Seeded transaction history
    # ------------------------------------------------------------------
    _TRANSACTION_HISTORY: Dict[str, List[SupplierHistoryRecord]] = {
        "wholesale_mandi": [
            SupplierHistoryRecord(
                transaction_id="TXN-WM-001",
                supplier_id="wholesale_mandi",
                date="2026-09-20",
                items_ordered={"rice": 30.0, "dal": 10.0, "cooking_oil": 8.0},
                total_amount=2740.0,
                actual_lead_time_days=1.0,
                quality_rating=4.0,
                quantity_accuracy=1.0,
                delivery_on_time=True,
                notes="Order fulfilled on schedule.",
            ),
            SupplierHistoryRecord(
                transaction_id="TXN-WM-002",
                supplier_id="wholesale_mandi",
                date="2026-09-28",
                items_ordered={"rice": 20.0, "containers": 100.0},
                total_amount=1440.0,
                actual_lead_time_days=1.2,
                quality_rating=4.2,
                quantity_accuracy=0.98,
                delivery_on_time=True,
                notes="Minor quantity shortfall on containers (2 units missing).",
            ),
            SupplierHistoryRecord(
                transaction_id="TXN-WM-003",
                supplier_id="wholesale_mandi",
                date="2026-10-05",
                items_ordered={"rice": 25.0, "dal": 15.0},
                total_amount=2850.0,
                actual_lead_time_days=1.0,
                quality_rating=4.5,
                quantity_accuracy=1.0,
                delivery_on_time=True,
                notes="Premium quality batch.",
            ),
        ],
        "kirana_express": [
            SupplierHistoryRecord(
                transaction_id="TXN-KE-001",
                supplier_id="kirana_express",
                date="2026-09-22",
                items_ordered={"cooking_oil": 5.0, "dal": 3.0},
                total_amount=1110.0,
                actual_lead_time_days=0.1,
                quality_rating=3.8,
                quantity_accuracy=1.0,
                delivery_on_time=True,
                notes="Emergency restock. Delivered in 2.5 hours.",
            ),
            SupplierHistoryRecord(
                transaction_id="TXN-KE-002",
                supplier_id="kirana_express",
                date="2026-10-01",
                items_ordered={"rice": 5.0, "containers": 50.0},
                total_amount=635.0,
                actual_lead_time_days=0.12,
                quality_rating=3.9,
                quantity_accuracy=1.0,
                delivery_on_time=True,
                notes="Fast delivery as usual.",
            ),
        ],
        "agro_fresh_farms": [
            SupplierHistoryRecord(
                transaction_id="TXN-AF-001",
                supplier_id="agro_fresh_farms",
                date="2026-09-25",
                items_ordered={"vegetables": 15.0, "dairy": 10.0},
                total_amount=875.0,
                actual_lead_time_days=1.5,
                quality_rating=4.7,
                quantity_accuracy=1.0,
                delivery_on_time=True,
                notes="Very fresh produce. Great quality.",
            ),
        ],
    }

    def __init__(self):
        # Mutable copy so update_supplier_record() can persist changes in-session
        self._profiles: Dict[str, SupplierProfile] = dict(self._SUPPLIER_DIRECTORY)
        self._history: Dict[str, List[SupplierHistoryRecord]] = {
            k: list(v) for k, v in self._TRANSACTION_HISTORY.items()
        }

    # ------------------------------------------------------------------
    # Tool 1: get_supplier_profile
    # ------------------------------------------------------------------
    def get_supplier_profile(self, supplier_id: str) -> Dict[str, Any]:
        """
        Returns the full profile for a specific supplier.

        Args:
            supplier_id: One of 'wholesale_mandi', 'kirana_express', 'agro_fresh_farms'

        Returns:
            Dict with supplier profile fields and simulation notice.

        Raises:
            ValueError: If supplier_id is unknown.
        """
        profile = self._profiles.get(supplier_id)
        if not profile:
            available = list(self._profiles.keys())
            raise ValueError(
                f"Unknown supplier '{supplier_id}'. Available: {available}"
            )
        return {
            **profile.to_dict(),
            "simulation_notice": SIMULATION_NOTICE,
        }

    # ------------------------------------------------------------------
    # Tool 2: compare_suppliers
    # ------------------------------------------------------------------
    def compare_suppliers(
        self,
        supplier_id_a: str,
        supplier_id_b: str,
    ) -> Dict[str, Any]:
        """
        Side-by-side comparison of two suppliers across price, speed,
        quality, and reliability. Returns a recommendation.

        Args:
            supplier_id_a: First supplier ID.
            supplier_id_b: Second supplier ID.

        Returns:
            SupplierComparison dict with scores, winner, and rationale.
        """
        eval_a = self.evaluate_supplier(supplier_id_a)
        eval_b = self.evaluate_supplier(supplier_id_b)

        prof_a = self._profiles[supplier_id_a]
        prof_b = self._profiles[supplier_id_b]

        score_a = eval_a["scores"]["composite"]
        score_b = eval_b["scores"]["composite"]

        cost_diff_pct = round(
            ((prof_b.min_order_value - prof_a.min_order_value) / max(prof_a.min_order_value, 1)) * 100,
            2,
        )
        speed_diff = round(prof_b.avg_lead_time_days - prof_a.avg_lead_time_days, 2)

        if score_a >= score_b:
            winner = supplier_id_a
            winner_reason = (
                f"{prof_a.name} scores higher overall ({score_a:.1f} vs {score_b:.1f}). "
                f"Preferred for regular procurement."
            )
        else:
            winner = supplier_id_b
            winner_reason = (
                f"{prof_b.name} scores higher overall ({score_b:.1f} vs {score_a:.1f}). "
                f"Preferred for regular procurement."
            )

        return {
            "supplier_a": prof_a.to_dict(),
            "supplier_b": prof_b.to_dict(),
            "evaluation_a": eval_a,
            "evaluation_b": eval_b,
            "winner_supplier_id": winner,
            "winner_reason": winner_reason,
            "cost_difference_pct": cost_diff_pct,
            "speed_difference_days": speed_diff,
            "simulation_notice": SIMULATION_NOTICE,
        }

    # ------------------------------------------------------------------
    # Tool 3: get_supplier_history
    # ------------------------------------------------------------------
    def get_supplier_history(
        self,
        supplier_id: str,
        last_n: int = 10,
    ) -> Dict[str, Any]:
        """
        Returns past transaction records with a supplier.

        Args:
            supplier_id: Supplier whose history to retrieve.
            last_n:      Maximum number of recent records to return (default 10).

        Returns:
            Dict with list of transaction records and summary statistics.

        Raises:
            ValueError: If supplier_id is unknown.
        """
        if supplier_id not in self._profiles:
            raise ValueError(
                f"Unknown supplier '{supplier_id}'. Available: {list(self._profiles.keys())}"
            )

        records = self._history.get(supplier_id, [])
        recent = records[-last_n:] if len(records) > last_n else records

        total_spend = sum(r.total_amount for r in recent)
        avg_quality = (
            sum(r.quality_rating for r in recent) / len(recent) if recent else 0.0
        )
        on_time_rate = (
            sum(1 for r in recent if r.delivery_on_time) / len(recent) if recent else 0.0
        )
        avg_lead_time = (
            sum(r.actual_lead_time_days for r in recent) / len(recent) if recent else 0.0
        )

        return {
            "supplier_id": supplier_id,
            "supplier_name": self._profiles[supplier_id].name,
            "total_transactions": len(records),
            "showing_last": len(recent),
            "summary": {
                "total_spend_rs": round(total_spend, 2),
                "avg_quality_rating": round(avg_quality, 2),
                "on_time_delivery_rate": round(on_time_rate, 3),
                "avg_actual_lead_time_days": round(avg_lead_time, 2),
            },
            "transactions": [r.to_dict() for r in recent],
            "simulation_notice": SIMULATION_NOTICE,
        }

    # ------------------------------------------------------------------
    # Tool 4: evaluate_supplier
    # ------------------------------------------------------------------
    def evaluate_supplier(self, supplier_id: str) -> Dict[str, Any]:
        """
        Scores a supplier across five dimensions:
          quality, cost, speed, reliability, relationship.

        Weights:
          quality=25%, cost=25%, speed=20%, reliability=20%, relationship=10%

        Args:
            supplier_id: Supplier to evaluate.

        Returns:
            SupplierEvaluation dict with dimension scores, composite,
            recommendation label, and actionable insights.

        Raises:
            ValueError: If supplier_id is unknown.
        """
        if supplier_id not in self._profiles:
            raise ValueError(
                f"Unknown supplier '{supplier_id}'. Available: {list(self._profiles.keys())}"
            )

        profile = self._profiles[supplier_id]
        history = self._history.get(supplier_id, [])

        # --- Quality Score (0–10) ---
        if history:
            avg_q = sum(r.quality_rating for r in history) / len(history)
            quality_score = (avg_q / 5.0) * 10.0
        else:
            quality_score = profile.rating * 2.0  # fallback to profile rating

        # --- Cost Score (0–10): lower min_order_value = better score ---
        # Benchmark: wholesale_mandi min=500, kirana_express min=100, agro=300
        # Normalise against max known (500) — lower is better
        max_mov = 500.0
        cost_score = max(0.0, (1.0 - (profile.min_order_value / max_mov)) * 10.0)
        # Also factor in type: wholesale generally cheaper per-unit
        if profile.type == "wholesale":
            cost_score = min(10.0, cost_score + 2.0)

        # --- Speed Score (0–10): faster lead time = higher score ---
        max_lead = 2.0  # days (worst case in catalogue)
        speed_score = max(0.0, (1.0 - (profile.avg_lead_time_days / max_lead)) * 10.0)

        # --- Reliability Score (0–10) ---
        if history:
            on_time_rate = sum(1 for r in history if r.delivery_on_time) / len(history)
            avg_qty_acc = sum(r.quantity_accuracy for r in history) / len(history)
            reliability_score = ((on_time_rate + avg_qty_acc) / 2.0) * 10.0
        else:
            reliability_score = profile.rating * 2.0

        # --- Relationship Score (0–10): more transactions = stronger ---
        txn_count = len(history)
        relationship_score = min(10.0, txn_count * 2.0)  # cap at 5 transactions

        # --- Composite Score (weighted average) ---
        composite = (
            quality_score * 0.25
            + cost_score * 0.25
            + speed_score * 0.20
            + reliability_score * 0.20
            + relationship_score * 0.10
        )

        # --- Recommendation Label ---
        if composite >= 7.5:
            recommendation = "preferred"
        elif composite >= 5.5:
            recommendation = "acceptable"
        elif composite >= 3.5:
            recommendation = "review"
        else:
            recommendation = "avoid"

        # --- Actionable Insights ---
        insights: List[str] = []
        if quality_score < 6.0:
            insights.append("Quality ratings are below average — consider quality checks on next order.")
        if cost_score < 5.0:
            insights.append("Pricing is above market average — negotiate or source alternative.")
        if speed_score < 5.0:
            insights.append("Lead times are long — plan procurement 2+ days in advance.")
        if reliability_score < 7.0:
            insights.append("Delivery reliability needs improvement — add buffer stock when ordering.")
        if relationship_score < 4.0:
            insights.append("Low transaction history — build relationship through consistent orders.")
        if not insights:
            insights.append("Supplier performing well across all dimensions.")
        if profile.type == "express":
            insights.append("Express supplier — use for emergency restocking only due to premium pricing.")

        return SupplierEvaluation(
            supplier_id=supplier_id,
            supplier_name=profile.name,
            quality_score=quality_score,
            cost_score=cost_score,
            speed_score=speed_score,
            reliability_score=reliability_score,
            relationship_score=relationship_score,
            composite_score=composite,
            recommendation=recommendation,
            insights=insights,
        ).to_dict()

    # ------------------------------------------------------------------
    # Tool 5: update_supplier_record
    # ------------------------------------------------------------------
    def update_supplier_record(
        self,
        supplier_id: str,
        new_rating: Optional[float] = None,
        new_notes: Optional[str] = None,
        new_contact_phone: Optional[str] = None,
        new_payment_terms: Optional[str] = None,
        append_transaction: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Persists updated supplier information or appends a new transaction
        record to the in-session supplier directory.

        Args:
            supplier_id:         Supplier to update.
            new_rating:          Updated composite rating (0–5).
            new_notes:           Updated free-text notes.
            new_contact_phone:   Updated contact phone number.
            new_payment_terms:   Updated payment terms string.
            append_transaction:  Dict matching SupplierHistoryRecord fields
                                 to append a new transaction.

        Returns:
            Updated supplier profile dict plus a changelog of changes made.

        Raises:
            ValueError: If supplier_id is unknown or rating is out of range.
        """
        if supplier_id not in self._profiles:
            raise ValueError(
                f"Unknown supplier '{supplier_id}'. Available: {list(self._profiles.keys())}"
            )

        profile = self._profiles[supplier_id]
        changelog: List[str] = []

        if new_rating is not None:
            if not (0.0 <= new_rating <= 5.0):
                raise ValueError("Rating must be between 0.0 and 5.0.")
            old = profile.rating
            profile.rating = new_rating
            changelog.append(f"rating updated: {old} → {new_rating}")

        if new_notes is not None:
            profile.notes = new_notes
            changelog.append("notes updated.")

        if new_contact_phone is not None:
            profile.contact_phone = new_contact_phone
            changelog.append(f"contact_phone updated to {new_contact_phone}.")

        if new_payment_terms is not None:
            profile.payment_terms = new_payment_terms
            changelog.append(f"payment_terms updated to '{new_payment_terms}'.")

        if append_transaction is not None:
            txn_id = append_transaction.get(
                "transaction_id",
                f"TXN-{supplier_id[:2].upper()}-{len(self._history.get(supplier_id, [])) + 1:03d}",
            )
            record = SupplierHistoryRecord(
                transaction_id=txn_id,
                supplier_id=supplier_id,
                date=append_transaction.get("date", datetime.utcnow().strftime("%Y-%m-%d")),
                items_ordered=append_transaction.get("items_ordered", {}),
                total_amount=float(append_transaction.get("total_amount", 0.0)),
                actual_lead_time_days=float(append_transaction.get("actual_lead_time_days", profile.avg_lead_time_days)),
                quality_rating=float(append_transaction.get("quality_rating", profile.rating)),
                quantity_accuracy=float(append_transaction.get("quantity_accuracy", 1.0)),
                delivery_on_time=bool(append_transaction.get("delivery_on_time", True)),
                notes=append_transaction.get("notes", ""),
            )
            if supplier_id not in self._history:
                self._history[supplier_id] = []
            self._history[supplier_id].append(record)
            changelog.append(f"Transaction '{txn_id}' appended to history.")

        return {
            "updated_profile": profile.to_dict(),
            "changelog": changelog,
            "simulation_notice": SIMULATION_NOTICE,
        }
