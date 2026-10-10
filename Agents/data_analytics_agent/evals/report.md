# Evaluation Report: Business Intel Agent

- **Date:** 2026-10-10
- **Archetype:** Maa Ki Rasoi Cloud Kitchen, Kanpur
- **Scenarios Evaluated:** 27
- **Passed:** 27/27 (100.0%)
- **Average Latency:** 2.0 ms
- **Speech Word Limit Compliance (<= 45 words):** 100%
- **Ungrounded Numeric Hallucinations:** 0.0%

## Summary Results Table

| ID | Category | Question | Latency (ms) | Status | Tools / Referral |
|---|---|---|---|---|---|
| `CONTEXT-01` | `context` | Give me my morning briefing. | 3.99 | ✅ PASS | get_business_overview |
| `CONTEXT-02` | `context` | What is my current cash position and headroom? | 2.21 | ✅ PASS | get_business_overview |
| `CONTEXT-03` | `context` | How many tiffin orders are confirmed for tomorrow? | 1.92 | ✅ PASS | get_business_overview |
| `CONTEXT-04` | `context` | Do we have any inventory shortage risks for tomorrow's prep? | 2.01 | ✅ PASS | get_business_overview |
| `CONTEXT-05` | `context` | What recent changes happened with suppliers or customers in the last 7 days? | 1.22 | ✅ PASS | get_recent_business_changes |
| `CONTEXT-06` | `context` | Show me recent operational changes over the past 30 days. | 1.16 | ✅ PASS | get_recent_business_changes |
| `CONTEXT-07` | `context` | What policies and facts do we have stored in business memory? | 1.23 | ✅ PASS | get_business_memory |
| `CONTEXT-08` | `context` | Remember that our kitchen opening time is strictly 6:00 AM. | 0.97 | ✅ PASS | write_business_memory |
| `CONTEXT-09` | `context` | Remember that refined oil from Gupta Traders is Rs 130 per liter. | 0.89 | ✅ PASS | write_business_memory |
| `CONTEXT-10` | `context` | Check if there are any memory conflicts on supplier rates. | 0.88 | ✅ PASS | get_business_memory |
| `ANALYTICS-01` | `analytics` | How did the kitchen perform over the last 30 days? | 1.82 | ✅ PASS | analyze_business_performance |
| `ANALYTICS-02` | `analytics` | What were yesterday's sales and revenue numbers? | 1.27 | ✅ PASS | analyze_business_performance |
| `ANALYTICS-03` | `analytics` | How did we perform last week? | 1.64 | ✅ PASS | analyze_business_performance |
| `ANALYTICS-04` | `analytics` | What is our month-to-date business performance? | 2.64 | ✅ PASS | analyze_business_performance |
| `ANALYTICS-05` | `analytics` | What are our unit economics and contribution margin for the Standard Veg Tiffin? | 1.55 | ✅ PASS | analyze_product_profitability |
| `ANALYTICS-06` | `analytics` | What is our daily breakeven volume in meals? | 1.34 | ✅ PASS | analyze_product_profitability |
| `ANALYTICS-07` | `analytics` | Analyze our supplier price trends and inflation over the last 90 days. | 1.85 | ✅ PASS | analyze_cost_trends |
| `ANALYTICS-08` | `analytics` | Generate an executive brief report for the last 30 days. | 5.46 | ✅ PASS | generate_business_report |
| `HINGLISH-01` | `context` | Aaj ka cash balance aur kal ka load kya hai? | 7.69 | ✅ PASS | get_business_overview |
| `HINGLISH-02` | `context` | Pichhle 7 din me kya kya changes huye kitchen me? | 2.91 | ✅ PASS | get_recent_business_changes |
| `HINGLISH-03` | `analytics` | Pichhle mahine ka profit aur margin kaisa raha? | 4.42 | ✅ PASS | analyze_business_performance |
| `BOTH-01` | `both` | How did my week go and what operational issues came up? | 3.66 | ✅ PASS | analyze_business_performance, get_recent_business_changes |
| `OOS-PROCUREMENT` | `out_of_scope` | Can I afford to buy 50kg basmati rice from Sharma Traders right now? | 0.17 | ✅ PASS | Out of Scope Referral |
| `OOS-CAPACITY` | `out_of_scope` | Can I take 50 more orders tomorrow afternoon for a corporate lunch? | 0.14 | ✅ PASS | Out of Scope Referral |
| `OOS-DOCUMENT` | `out_of_scope` | Verify this bill from Gupta Traders. Is this invoice authentic? | 0.12 | ✅ PASS | Out of Scope Referral |
| `OOS-GROWTH` | `out_of_scope` | How do I get more customers using Instagram ads and pamphlets in Kakadeo? | 0.12 | ✅ PASS | Out of Scope Referral |
| `OOS-EXECUTION` | `out_of_scope` | Pay Sharma ₹5000 right now and place the order for oil. | 0.12 | ✅ PASS | Out of Scope Referral |

## Spoken Sample Verifications

### `CONTEXT-01`: "Give me my morning briefing."
- **Voice Output:** Cash is Rs 12000. Tomorrow has 20 confirmed tiffins with 14 free afternoon slots. You are short on Tiffin container 750ml and Refined sunflower oil, and cash headroom is Rs 1900.
- **Word Count:** 31 words

### `CONTEXT-02`: "What is my current cash position and headroom?"
- **Voice Output:** Cash is Rs 12000. Tomorrow has 20 confirmed tiffins with 14 free afternoon slots. You are short on Tiffin container 750ml and Refined sunflower oil, and cash headroom is Rs 1900.
- **Word Count:** 31 words

### `CONTEXT-03`: "How many tiffin orders are confirmed for tomorrow?"
- **Voice Output:** Cash is Rs 12000. Tomorrow has 20 confirmed tiffins with 14 free afternoon slots. You are short on Tiffin container 750ml and Refined sunflower oil, and cash headroom is Rs 1900.
- **Word Count:** 31 words

### `CONTEXT-04`: "Do we have any inventory shortage risks for tomorrow's prep?"
- **Voice Output:** Cash is Rs 12000. Tomorrow has 20 confirmed tiffins with 14 free afternoon slots. You are short on Tiffin container 750ml and Refined sunflower oil, and cash headroom is Rs 1900.
- **Word Count:** 31 words

### `CONTEXT-05`: "What recent changes happened with suppliers or customers in the last 7 days?"
- **Voice Output:** Found 45 recent changes since 2026-10-03. Top notices include Customer Update: Manish Rathore: bhaiya sabzi me mirchi thodi kam rakha karo.
- **Word Count:** 21 words

### `CONTEXT-06`: "Show me recent operational changes over the past 30 days."
- **Voice Output:** Found 45 recent changes since 2026-10-03. Top notices include Customer Update: Manish Rathore: bhaiya sabzi me mirchi thodi kam rakha karo.
- **Word Count:** 21 words

### `CONTEXT-07`: "What policies and facts do we have stored in business memory?"
- **Voice Output:** Retrieved 6 memory facts with 2 active conflict(s).
- **Word Count:** 8 words

### `CONTEXT-08`: "Remember that our kitchen opening time is strictly 6:00 AM."
- **Voice Output:** Got it, recorded policy.owner_note as our kitchen opening time is strictly 6:00 am. from your statement.
- **Word Count:** 16 words

### `CONTEXT-09`: "Remember that refined oil from Gupta Traders is Rs 130 per liter."
- **Voice Output:** Got it, recorded policy.owner_note as refined oil from gupta traders is rs 130 per liter. from your statement.
- **Word Count:** 18 words

### `CONTEXT-10`: "Check if there are any memory conflicts on supplier rates."
- **Voice Output:** Retrieved 6 memory facts with 2 active conflict(s).
- **Word Count:** 8 words
