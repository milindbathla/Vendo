"""
Customer Acquisition Engine
Models multi-channel reach, conversion, diminishing returns, and acquisition costs.
"""
import math
import random
from typing import Dict, Any

class AcquisitionEngine:
    def __init__(self, rng: random.Random):
        self.rng = rng

    def calculate_new_customers(
        self,
        marketing_spend: float,
        base_cac: float,
        conversion_rate: float,
        saturation_spend_threshold: float = 1000.0,
    ) -> (int, float):
        """
        Calculates new customers acquired from daily marketing spend.
        Includes diminishing returns for high spend (logarithmic tail).
        Returns (new_customers, effective_cac).
        """
        if marketing_spend <= 0.0 or base_cac <= 0.0:
            return 0, 0.0

        # Model diminishing returns: beyond threshold, efficiency scales with square root
        if marketing_spend <= saturation_spend_threshold:
            effective_spend = marketing_spend
        else:
            excess = marketing_spend - saturation_spend_threshold
            effective_spend = saturation_spend_threshold + math.sqrt(excess * saturation_spend_threshold)

        # Potential prospects reached
        prospects = effective_spend / base_cac
        
        # Expected conversions today
        expected_conversions = prospects * conversion_rate
        
        # Stochastic integer realization: integer part + Bernoulli trial on fractional part
        int_part = int(expected_conversions)
        frac_part = expected_conversions - int_part
        bonus = 1 if self.rng.random() < frac_part else 0
        actual_conversions = int_part + bonus

        actual_conversions = max(0, actual_conversions)
        effective_cac = (marketing_spend / actual_conversions) if actual_conversions > 0 else marketing_spend

        return actual_conversions, effective_cac
