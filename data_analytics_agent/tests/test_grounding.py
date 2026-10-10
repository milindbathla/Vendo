"""Test grounding verifier and numeric hallucination detection."""
import pytest
from business_intel.grounding import extract_numbers, verify_grounding


def test_number_extraction_formats():
    text = "We earned ₹12,000, margin was 17.3%, volume 639, approx Rs 55.3k, ARR 1.89 lakh, target 1.5 crore."
    nums = extract_numbers(text)
    extracted_vals = [n.value for n in nums]

    assert 12000.0 in extracted_vals
    assert 17.3 in extracted_vals
    assert 639.0 in extracted_vals
    assert 55300.0 in extracted_vals
    assert 189000.0 in extracted_vals
    assert 15000000.0 in extracted_vals


def test_grounding_verification_pass():
    data = {
        "cash_balance": 12000,
        "revenue": 55320,
        "margin": 0.173,
        "tiffins": 639,
    }
    speech = "Cash is Rs 12000. Net margin was 17% on 639 tiffins with approx 55.3k revenue."
    is_grounded, ungrounded = verify_grounding(speech, data)
    assert is_grounded is True
    assert len(ungrounded) == 0


def test_grounding_catches_hallucination():
    data = {
        "cash_balance": 12000,
        "revenue": 55320,
    }
    # 75000 and 42% are fabricated
    hallucinated_speech = "Cash is Rs 12000, but next week we project ₹75,000 with a 42% profit rate."
    is_grounded, ungrounded = verify_grounding(hallucinated_speech, data)
    assert is_grounded is False
    assert any("75" in u for u in ungrounded)
    assert any("42" in u for u in ungrounded)

