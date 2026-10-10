# Confidence Computation Specification

In **Alexa Business Autopilot**, confidence scores are mathematically computed by tools rather than guessed or fabricated by LLMs. Every result envelope returned to the orchestrator carries a `confidence` value in the range `[0.0, 1.0]`.

---

## 1. Mathematical Formulation

Let $C$ denote the computed confidence score. Computation starts at baseline 1.0 and applies multiplicative penalty factors based on data coverage, forecast uncertainty, memory conflicts, and sample size:

$$
C = \text{clamp}\Big( 1.0 \times F_{\text{coverage}} \times F_{\text{forecast}} \times F_{\text{conflict}} \times F_{\text{sample}}, \; 0.0, \; 1.0 \Big)
$$

### 1.1 Factors & Multipliers

1. **Baseline**: Starts at `1.0`.
2. **Data Coverage Factor ($F_{\text{coverage}}$)**:
   $$
   F_{\text{coverage}} = \frac{N_{\text{days\_with\_data}}}{N_{\text{days\_requested}}}
   $$
   If a tool requests a 30-day window but only 27 days have recorded entries in `daily_metrics`, $F_{\text{coverage}} = 27 / 30 = 0.90$.
3. **Forecast Confidence Factor ($F_{\text{forecast}}$)**:
   - If statistical forecast models are used (such as in `get_business_overview` for tomorrow's demand or `forecast_demand`), $F_{\text{forecast}} = \min(C_{\text{forecast}})$.
   - When no forecasts are used, $F_{\text{forecast}} = 1.0$.
   - Note: If forecasts are used, the envelope `source` is set to `"estimate"`.
4. **Memory Conflict Penalty ($F_{\text{conflict}}$)**:
   - If the query resolution touches a key in `business_memory` with an active conflict between verified records and owner verbal statements (e.g. `supplier.gupta.oil_price_per_l`), apply penalty:
   $$
   F_{\text{conflict}} = 0.80
   $$
   - Otherwise, $F_{\text{conflict}} = 1.0$.
5. **Small Sample Size Penalty ($F_{\text{sample}}$)**:
   - If the sample size is less than 7 days (e.g. 1-day or 3-day query window), statistical variance is elevated:
   $$
   F_{\text{sample}} = 0.70
   $$
   - For windows $\ge 7$ days, $F_{\text{sample}} = 1.0$.

---

## 2. Origin Attribution (`source`)

Every tool response envelope specifies a discrete `source`:
- `"db"`: Direct retrieval or arithmetic aggregation of verified ledger, catalog, stock, or order records.
- `"estimate"`: Involves statistical projections, forecasting bands, or heuristic extrapolations.
- `"simulated"`: Involves simulated actors, specifically **QuickKart Now (`SUP-04`)** where `is_simulated = 1`. Whenever simulated catalog data or emergency delivery pricing is used, `source` is set to `"simulated"`, and a clear explanatory warning is appended to `warnings`.

---

## 3. Implementation Function

The standard Python implementation used across `business_intel` tools is:

```python
def compute_confidence(
    data_days: int,
    requested_days: int,
    forecast_confidence: Optional[float] = None,
    has_memory_conflict: bool = False,
    is_simulated: bool = False,
) -> Tuple[float, str]:
    coverage = min(1.0, max(0.0, data_days / max(1, requested_days)))
    conf = 1.0 * coverage
    
    source = "db"
    if forecast_confidence is not None:
        conf *= min(1.0, max(0.0, forecast_confidence))
        source = "estimate"
        
    if has_memory_conflict:
        conf *= 0.80
        
    if requested_days < 7:
        conf *= 0.70
        
    if is_simulated:
        source = "simulated"
        
    conf = max(0.0, min(1.0, round(conf, 2)))
    return conf, source
```

