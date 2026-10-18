"""
Adaptive Business Onboarding Engine
====================================
Extracts, structures, and refines business facts from natural-language
conversations. Tracks provenance, flags missing critical facts, asks targeted
follow-ups, and allows safe corrections without silently hallucinating values.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from src.models.adaptive_profile import (
    AdaptiveBusinessProfile,
    BusinessFact,
    FactStatus,
    FactSource,
)

logger = logging.getLogger(__name__)

# Business domain archetypes and their relevant fact requirements
CATEGORY_KEYWORDS = {
    "mechanical_repair": [
        "bike", "two-wheeler", "motorcycle", "scooter", "car", "automobile", "auto",
        "vehicle", "engine", "tuning", "garage", "mechanic", "puncture", "tyre", "tire",
        "servicing", "two wheeler", "four wheeler", "bikes"
    ],
    "small_fabrication": [
        "fabrication", "welding", "welder", "metal", "iron", "grill", "gate",
        "railing", "sheet metal", "manufacturing", "workshop", "lathe", "machining",
        "steel work"
    ],
    "clothing_retail": [
        "clothing", "clothes", "apparel", "garments", "shirts", "jeans", "pants",
        "trousers", "sarees", "dress", "textile", "readymade", "fashion wear"
    ],
    "tailoring_boutique": [
        "tailor", "tailoring", "boutique", "stitching", "alteration", "dressmaker",
        "embroidery", "custom stitching"
    ],
    "electronics_repair": [
        "electronics", "mobile", "phone", "smartphone", "laptop", "computer",
        "screen", "battery", "service center", "gadget", "tablet", "circuit",
        "motherboard", "headphone"
    ],
    "salon_service": [
        "salon", "beauty", "haircut", "facial", "spa", "makeup", "parlour",
        "grooming", "barber", "hairstyling", "massage"
    ],
    "home_bakery": [
        "bakery", "cake", "pastry", "cookies", "baking", "confectionery",
        "dessert", "pastries", "baker", "cupcake"
    ],
    "home_tiffin": [
        "tiffin", "meal", "dabba", "catering", "lunchbox", "food delivery",
        "cook", "mess", "canteen", "thali", "home-cooked"
    ],
    "retail_kirana": [
        "kirana", "grocery", "groceries", "provisions", "fmcg", "supermarket",
        "dry ration", "general store"
    ],
}

# Critical vs optional facts per business goal
CORE_FACT_DESCRIPTIONS = {
    "selling_price": "Average price or service fee charged to customers (in Rs)",
    "unit_material_cost": "Direct material, wholesale, or consumables cost per unit/job (in Rs)",
    "daily_capacity": "Maximum number of orders, clients, or jobs you can fulfill in a day",
    "cash_balance": "Current liquid cash or bank balance (in Rs)",
    "safety_reserve": "Minimum cash reserve you must never spend (in Rs)",
    "daily_fixed_cost": "Daily overhead like rent, electricity, and salaries (in Rs)",
    "current_inventory": "Current available inventory, units, or consumable kits in stock",
}


class AdaptiveBusinessOnboarder:
    """
    Stateful conversational onboarding manager that extracts business attributes,
    tracks fact certainty, and formulates targeted follow-up questions.
    """

    def __init__(
        self,
        profile: Optional[AdaptiveBusinessProfile] = None,
        business_id_hint: Optional[str] = None,
    ):
        self.profile = profile
        self._business_id_hint = business_id_hint

    def create_or_resume_profile(
        self,
        business_id: str,
        display_name: str,
        category: str = "general_business",
        description: str = "",
    ) -> AdaptiveBusinessProfile:
        """Initializes or resumes an adaptive business profile."""
        if self.profile and self.profile.business_id == business_id:
            return self.profile

        self.profile = AdaptiveBusinessProfile(
            business_id=business_id,
            display_name=display_name,
            category=category,
            description=description,
        )
        return self.profile

    def process_utterance(self, text: str) -> Dict[str, Any]:
        """
        Processes a user's statement to extract facts, handle corrections,
        and generate contextual questions or confirmations.
        """
        if not self.profile:
            # Use caller-supplied ID hint when available; otherwise generate one from time
            biz_id = self._business_id_hint or ("biz_" + str(int(time.time()))[-6:])
            self.profile = AdaptiveBusinessProfile(
                business_id=biz_id,
                display_name="My Business",
                category="general_business",
            )

        text_lower = text.lower()
        extracted_facts: List[Dict[str, Any]] = []
        corrections: List[Dict[str, Any]] = []

        # 1. Detect Category if not confirmed
        if not self.profile.is_confirmed("category") or self.profile.category == "general_business":
            detected_cat = self._detect_category(text_lower)
            if detected_cat:
                self.profile.category = detected_cat
                fact = self.profile.set_fact(
                    "category",
                    detected_cat,
                    status=FactStatus.CONFIRMED,
                    source=FactSource.USER_STATED,
                    notes=f"Detected from user input: '{text[:60]}...'",
                )
                extracted_facts.append(fact.to_dict())

        # 2. Extract Business Name / Display Name
        name_match = re.search(r"(?:i run|i own|my shop is|name is|called)\s+([A-Za-z0-9\s'&]+?)(?:\s+in|\s+at|\.|\,|$)", text, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip()
            if len(name) > 2 and name.lower() not in ("a", "the", "my business"):
                self.profile.display_name = name
                fact = self.profile.set_fact("display_name", name, status=FactStatus.CONFIRMED, notes="User stated name")
                extracted_facts.append(fact.to_dict())

        # 3. Detect Corrections
        is_correction = any(w in text_lower for w in [
            "actually", "correction", "change that to", "not", "update my", "instead of",
            "change to", "correct that to", "updated", "change price to", "corrected"
        ])

        # 4. Extract Financial & Operational Numbers using Regex
        extracted_numeric = self._extract_numeric_facts(text)
        for key, val, notes in extracted_numeric:
            old_fact = self.profile.get_fact(key)
            if old_fact and old_fact.value != val and is_correction:
                # Carry forward existing audit log and append new entry
                prior_log = list(old_fact.correction_log)
                old_fact.status = FactStatus.OUTDATED
                new_fact = self.profile.set_fact(
                    key,
                    val,
                    status=FactStatus.CONFIRMED,
                    source=FactSource.USER_STATED,
                    notes=f"Corrected from {old_fact.value}. {notes}",
                )
                # Restore carried-forward history then record this correction
                new_fact.correction_log = prior_log
                new_fact.record_correction(old_value=old_fact.value, old_notes=old_fact.notes, new_value=val)
                corrections.append({"key": key, "old_value": old_fact.value, "new_value": val})
                extracted_facts.append(new_fact.to_dict())
            else:
                new_fact = self.profile.set_fact(
                    key,
                    val,
                    status=FactStatus.CONFIRMED,
                    source=FactSource.USER_STATED,
                    notes=notes,
                )
                extracted_facts.append(new_fact.to_dict())

        # 5. Extract Products / Services
        products = self._extract_products(text)
        if products:
            fact = self.profile.set_fact(
                "products_and_services",
                products,
                status=FactStatus.CONFIRMED,
                source=FactSource.USER_STATED,
                notes="Items or services offered",
            )
            extracted_facts.append(fact.to_dict())

        # 6. Analyze Missing Information
        missing_critical, missing_optional = self.get_missing_facts()

        # 7. Formulate Follow-up Question
        next_question = self._generate_next_question(missing_critical)

        # Update profile onboarding status
        if not missing_critical:
            self.profile.onboarding_completed = True

        return {
            "business_id": self.profile.business_id,
            "display_name": self.profile.display_name,
            "category": self.profile.category,
            "extracted_facts": extracted_facts,
            "corrections": corrections,
            "missing_critical_facts": missing_critical,
            "missing_optional_facts": missing_optional,
            "onboarding_completed": self.profile.onboarding_completed,
            "next_question": next_question,
            "reply": self._generate_conversational_reply(extracted_facts, corrections, next_question),
        }

    def get_missing_facts(self) -> Tuple[List[str], List[str]]:
        """
        Determines which facts are missing based on business category.
        Never hallucinates defaults as confirmed.
        """
        critical_keys = ["selling_price", "unit_material_cost", "daily_capacity"]
        optional_keys = ["cash_balance", "safety_reserve", "daily_fixed_cost", "current_inventory"]

        missing_critical = [k for k in critical_keys if not self.profile.is_confirmed(k)]
        missing_optional = [k for k in optional_keys if not self.profile.is_confirmed(k)]

        return missing_critical, missing_optional

    def _detect_category(self, text: str) -> Optional[str]:
        # Precedence order: specific crafts/services first, general retail last
        precedence = [
            "mechanical_repair",
            "small_fabrication",
            "clothing_retail",
            "tailoring_boutique",
            "electronics_repair",
            "salon_service",
            "home_bakery",
            "home_tiffin",
            "retail_kirana",
        ]
        scores: Dict[str, int] = {cat: 0 for cat in precedence}
        for cat in precedence:
            for kw in CATEGORY_KEYWORDS.get(cat, []):
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, text, re.IGNORECASE):
                    scores[cat] += 1

        best_cat = None
        best_score = 0
        for cat in precedence:
            if scores[cat] > best_score:
                best_score = scores[cat]
                best_cat = cat
        return best_cat

    def _extract_numeric_facts(self, text: str) -> List[Tuple[str, float, str]]:
        """Extracts key financial and operational metrics without ambiguity."""
        results: List[Tuple[str, float, str]] = []

        # 1. Material / wholesale / parts / ingredient cost (extracted first to establish cost spans)
        cost_patterns = [
            # Noun phrase + cost + Rs N + per unit
            r"[\w]+(?:\s+and\s+[\w]+)*\s+(?:costs?|cost\s+is)\s*(?:around|about)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+(?:job|repair|service|client|unit|item|meal|tiffin|garment|suit|piece|cake|bike|shirt|dress|order)|each)?",
            # Specific material keywords
            r"(?:spare\s+parts?|parts?|consumables?|cosmetics?|materials?|ingredients?|supplies?|fabric|raw\s+materials?|lubricants?|cosmetic\s+consumables?)\s*(?:costs?|cost\s+is|is|of)?\s*(?:around|about)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",
            # costing / costs N per unit
            r"(?:costing|costs?)\s*(?:around|about)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+(?:job|repair|service|client|unit|item|meal|tiffin|garment|suit|piece|cake|bike|shirt|dress|order)|each)",
            # wholesale cost / wholesale price
            r"(?:wholesale\s+cost|wholesale\s+price|wholesale)\s*(?:is|of)?\s*(?:around|about)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",
            # cost is / cost of
            r"(?:cost\s+is|cost\s+of)\s*(?:around|about)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",
        ]
        cost_spans: List[Tuple[int, int]] = []
        for pat in cost_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                cost_spans.append((m.start(), m.end()))
                cleaned = m.group(1).replace(",", "")
                results.append(("unit_material_cost", float(cleaned), "Direct material / wholesale / parts cost per unit"))
                break

        # 2. Selling price / fee (never extract from within cost spans or cost clauses)
        price_patterns = [
            r"(?<!wholesale\s)(?<!material\s)(?<!purchase\s)(?<!buying\s)\b(?:selling\s+price|average\s+price|servicing\s+charge|repair\s+charge|service\s+charge|service\s+fee|service\s+bill|ticket\s+price|fee|charge|price|rate|ticket)\s*(?:is|of|was)?\s*(?:around|about|actually|now|approx|approximately)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",
            r"(?:sells?|selling)\s+(?:(?:each|every|our|the|all|these)?\s*[\w\s]{0,25}?\s+)?(?:for|at)?\s*(?:around|about|actually|now|approx|approximately)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",
            r"(?:charge|charging|bills?|billing)\s+(?:(?:each|every|our|the|all|these)?\s*[\w\s]{0,25}?\s+)?(?:for|at)?\s*(?:around|about|actually|now|approx|approximately)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",
            r"(?:services?|servicing|repairs?|repairing|alters?|altering|stitch(?:es|ing)?)\s+(?:(?:each|every|our|the|all|these)?\s*[\w\s]{1,25}?\s+)(?:for|at)\s*(?:around|about|actually|now|approx|approximately)?\s*(?:rs\.?|inr)\s*([\d,]+(?:\.\d+)?)",
            r"(?:each|every)\s+(?:tiffin|meal|box|garment|shirt|suit|item|repair|service|cake|unit)\s+(?:sells?\s+(?:for|at)?|is|charges?)\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",
            r"(?:garments?|shirts?|suits?|items?|meals?|tiffins?|cakes?|repairs?|services?)\s+(?:for|at)\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",
            r"(?<!cost\s)(?<!costs\s)(?<!costing\s)(?:rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+(?:job|repair|service|client|order|unit|item|meal|meal\s+box|dabba|tiffin|garment|shirt|suit|piece|bike|cake|customer)|each)",
        ]
        for pat in price_patterns:
            found_price = False
            for m in re.finditer(pat, text, re.IGNORECASE):
                m_start, m_end = m.start(), m.end()
                # Exclude if overlapping with any detected cost span
                if any(not (m_end <= cs[0] or m_start >= cs[1]) for cs in cost_spans):
                    continue
                # Exclude if preceded in clause by explicit cost indicators (within same sentence/clause)
                last_boundary = max(text.rfind(".", 0, m_start), text.rfind(";", 0, m_start), text.rfind("\n", 0, m_start))
                clause_prefix = text[max(0, last_boundary + 1, m_start - 30):m_start].lower()
                if any(w in clause_prefix for w in ["cost", "costs", "material", "wholesale", "parts", "consumable", "ingredient"]):
                    continue
                cleaned = m.group(1).replace(",", "")
                results.append(("selling_price", float(cleaned), "Selling price / fee per unit"))
                found_price = True
                break
            if found_price:
                break

        # 3. Daily capacity (distinct from item inventory stock)
        capacity_patterns = [
            r"(?:daily\s+capacity|capacity)\s*(?:is|of)?\s*(?:handling|making|producing|delivering|doing|serving|stitching|repairing|preparing)?\s*(?:up to|at most|max)?\s*(\d+)\s*(?:jobs|repairs|clients|customers|orders|chairs|units|items|meals|tiffins|garments|suits|dresses|cakes|bikes|motorcycles|pieces|services)?",
            r"(?:can\s+)?(?:handle|do|serve|complete|deliver|stitch|bake|cook|produce|make|repair|service|prepare|alter)\s*(?:up to|at most|max|around)?\s*(\d+)\s*(?:[\w\s]{0,20}?)(?:jobs|repairs|clients|customers|orders|chairs|units|items|meals|tiffins|garments|suits|dresses|clothes|shirts|cakes|bikes|motorcycles|pieces)",
            r"(\d+)\s*(?:[\w\s]{0,20}?)(?:jobs|repairs|clients|customers|orders|units|meals|tiffins|garments|suits|dresses|cakes|bikes|motorcycles|pieces|chairs)\s*(?:per day|a day|daily)",
            r"(?:can\s+)?(?:service|repair|handle|prepare)\s*(\d+)\s*(?:[\w\s]{0,15}?)(?:per day|a day|daily)",
        ]
        for pat in capacity_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                results.append(("daily_capacity", float(m.group(1)), "Daily operational capacity"))
                break

        # 4. Liquid cash balance
        cash_patterns = [
            r"(?:cash\s+in\s+hand|cash\s+balance|liquid\s+cash|funds|bank\s+balance)(?:\s+in\s+[a-zA-Z\s]+)?\s*(?:is|of|at)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",
            r"(?:have|got)\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(?:in cash|in bank|cash|in the bank|in hand)",
            r"(?:rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(?:cash in hand|in liquid cash|cash balance|in cash|cash)",
        ]
        for pat in cash_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                cleaned = m.group(1).replace(",", "")
                results.append(("cash_balance", float(cleaned), "Available liquid cash balance"))
                break

        # 5. Safety reserve
        reserve_patterns = [
            r"(?:keep a|maintain a|keep aside|reserve of|buffer of)\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(?:safety buffer|safety reserve|reserve|buffer|emergency fund)",
            r"(?:safety\s+reserve|safety\s+buffer|reserve\s+buffer|emergency\s+fund|safety\s+margin|minimum\s+reserve|reserve)\s*(?:of|is)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",
            r"(?:rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(?:safety reserve|safety buffer|emergency fund|reserve|buffer)",
        ]
        for pat in reserve_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                cleaned = m.group(1).replace(",", "")
                results.append(("safety_reserve", float(cleaned), "Safety reserve buffer"))
                break

        # 6. Daily and monthly fixed cost / rent / overhead
        month_patterns = [
            r"(?:monthly\s+(?:rent(?:\s*(?:and|,)\s*[a-zA-Z\s]+)?|expenses?|overhead|fixed\s+cost|fixed\s+overhead|fixed\s+expenses?|bills?))\s*(?:is|are|of)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)",
            r"(?:rent(?:\s*(?:and|,)\s*[a-zA-Z\s]+)?|overhead|fixed\s+cost|fixed\s+overhead|fixed\s+expenses?|expenses?|bills?)\s*(?:is|are|of)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+month|a\s+month|monthly|\/\s*month)",
        ]
        m_month = None
        for pat in month_patterns:
            m_month = re.search(pat, text, re.IGNORECASE)
            if m_month:
                break
        if m_month:
            cleaned = m_month.group(1).replace(",", "")
            monthly_val = float(cleaned)
            daily_equiv = round(monthly_val / 30.0, 2)
            results.append(("monthly_fixed_cost", monthly_val, f"Monthly fixed overhead Rs.{cleaned}/month"))
            results.append(("daily_fixed_cost", daily_equiv, f"Daily fixed overhead derived from Rs.{cleaned}/month"))
        else:
            fixed_patterns = [
                r"(?:daily\s+overhead|daily\s+rent|shop\s+rent|rent|fixed\s+cost|fixed\s+expenses?|fixed\s+overhead|overhead|expenses?)\s*(?:is|are|of)?\s*(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(?:per day|daily|a day)",
                r"(?:rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(?:per day|daily)\s*(?:in rent|rent|overhead|fixed cost|fixed expenses?|fixed overhead)",
            ]
            for pat in fixed_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    cleaned = m.group(1).replace(",", "")
                    results.append(("daily_fixed_cost", float(cleaned), "Daily fixed overhead / rent"))
                    break

        # 7. Current inventory in stock (item units, NOT customer capacity)
        inv_patterns = [
            r"(?:stock|inventory)\s*(?:is|of|:)?\s*(\d+)\s*(?:[\w]+)?",
            # Handles: '40 garments in stock', '8 spare oil filters', '50 packets of detergent in stock'
            r"(\d+)\s*(?:[\w\s]{0,20}?)\s*(?:in stock|on hand|on inventory|in inventory)",
            r"(?:have|got|have got)\s*(\d+)\s*(?:[\w\s]{0,20}?)\s*(?:in stock|on hand|in inventory)",
        ]
        for pat in inv_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                results.append(("current_inventory", float(m.group(1)), "Current inventory in stock"))
                break

        return results

    def _extract_products(self, text: str) -> List[str]:
        m = re.search(r"(?:we offer|we repair|we sell|products include|services include)\s+([^.]+)", text, re.IGNORECASE)
        if m:
            raw = m.group(1)
            items = re.split(r",|\band\b", raw)
            return [it.strip() for it in items if len(it.strip()) > 2]
        return []

    def _generate_next_question(self, missing_critical: List[str]) -> Optional[str]:
        if not missing_critical:
            # Check optional if critical are done
            missing_opt = [k for k in ["cash_balance", "daily_fixed_cost"] if not self.profile.is_confirmed(k)]
            if missing_opt:
                k = missing_opt[0]
                if k == "cash_balance":
                    return "How much liquid cash or bank balance is currently available to run daily operations?"
                elif k == "daily_fixed_cost":
                    return "What are your approximate daily fixed expenses (like shop rent, power, or daily salaries)?"
            return None

        # Prioritize missing critical in order: price -> cost -> capacity
        target = missing_critical[0]
        if target == "selling_price":
            return f"What is your typical selling price or service fee charged to a customer?"
        elif target == "unit_material_cost":
            return f"What is your direct cost for materials, spare parts, or consumables per unit or service?"
        elif target == "daily_capacity":
            return f"What is the maximum number of orders, clients, or jobs you can realistically handle in a single day?"
        return None

    def _generate_conversational_reply(
        self,
        extracted: List[Dict[str, Any]],
        corrections: List[Dict[str, Any]],
        next_q: Optional[str],
    ) -> str:
        parts: List[str] = []

        if corrections:
            for c in corrections:
                parts.append(f"Updated {c['key'].replace('_', ' ')} from Rs.{c['old_value']} to Rs.{c['new_value']}.")

        if extracted and not corrections:
            facts_summary = ", ".join(f"{f['key'].replace('_', ' ')}: {f['value']}" for f in extracted if f['key'] != 'category')
            if facts_summary:
                parts.append(f"Noted: {facts_summary}.")
            if any(f['key'] == 'category' for f in extracted):
                parts.append(f"Categorized as {self.profile.category.replace('_', ' ').title()}.")

        if next_q:
            parts.append(next_q)
        else:
            parts.append("Your business profile has all core details! You can now ask me to analyze profitability, evaluate opportunities, check suppliers, or scout local competitors.")

        return " ".join(parts)
