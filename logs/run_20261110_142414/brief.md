# NPS Brief - Future with Shivank Bank
ALERT LEVEL: RED

## 1. How bad is it?
- Overall NPS: +18.5 (±6.6, n=600; promoters 268, passives 175, detractors 157)
- Monthly trend:
  - 2026-07: +32.0 (±10.6, n=200)
  - 2026-08: +30.0 (±10.9, n=200)
  - 2026-09: -6.5 (±11.8, n=200)
- Mobile App (channel): +12.3 across all months vs -33.6 in 2026-09
- Health verdict: RED because 2026-09 NPS -6.5 is below 0, month-on-month change -36.5 is at or below -20

## 2. Why did it happen?
- login_otp_failure - mentions by month: 2026-07=1, 2026-08=2, 2026-09=48
- NPS -87.5 for customers mentioning it (n=48) vs +19.1 for everyone else (n=152)
- R0431: "The OTP issue is still not fixed. I am moving my salary account." (score 5, 2026-09, Credit Card)
- R0456: "Couldn't get into my account for two days after the update." (score 5, 2026-09, Credit Card)
- R0428: "Locked out of my account three times this week. Login with OTP is broken." (score 5, 2026-09, Savings Account)
- Root-cause hypothesis (hypothesis): App update regression causing authentication blockages - evidence: login_otp_failure, 45 mentions overall (48 in September), R0431

## 3. How much money is at risk?
- Revenue at risk: ₹37.98 lakh of ₹304.43 lakh total revenue (12.5%)
- Where it sits: Wealth=31.51 lakh (83.0% of risk, NPS +1.0)
- Loud is not expensive: loudest complaint call_centre_service (61 customers, 4.73 lakh at risk) vs most expensive fees_charges (24 customers, 10.66 lakh at risk). Loud equals expensive: false - The most frequent complaint by customer count is call centre issues, whereas the highest financial risk stems from fees and charges.
- Risk verdict: AMBER

## 4. What do we fix first?
| Rank | By NPS points (all months) | By rupees saved (all months) |
|---|---|---|
| 1 | login_otp_failure +7.5 | fees_charges ₹6.4 lakh |
| 2 | fees_charges +4.0 | login_otp_failure ₹2.36 lakh |
| 3 | app_performance +3.5 | call_centre_service ₹1.01 lakh |
- Recommendation: login_otp_failure - why (+7.5 NPS points, 2.36 lakh saved, 45 detractors fixed), owner Digital / App team + fees_charges - why (6.4 lakh saved, +4.0 NPS points, 24 detractors fixed), owner Wealth product team. Fix rankings differ: loudest/most frequent in NPS points is login_otp_failure, while rupees saved is led by fees_charges.

## 5. Who do we call back this week?
| # | Customer | Product | Score | ₹ lakh at risk | Why |
|---|---|---|---|---|---|
| 1 | R0471 | Wealth | score 4 | 1.12 lakh | "The fee structure is confusing and nobody could explain it to me." |
| 2 | R0479 | Wealth | score 5 | 0.85 lakh | "Why am I paying so much every quarter for advice I never get?" |
| 3 | R0457 | Wealth | score 5 | 0.81 lakh | "The OTP issue is still not fixed. I am moving my salary account." |
| 4 | R0543 | Wealth | score 6 | 0.69 lakh | "The app keeps asking for a code that never comes." |
| 5 | R0570 | Wealth | score 5 | 0.61 lakh | "Hidden costs in the portfolio statement. Fees are much higher than other banks." |

## 6. Alert table
| Dimension | Verdict | Evidence |
|---|---|---|
| NPS health | RED | 2026-09 NPS -6.5 is below 0, month-on-month change -36.5 is at or below -20 |
| Revenue risk | AMBER | Total revenue at risk: ₹37.98 lakh of 304.43 lakh total revenue (12.5%) |
| Overall | RED | worst of the two |

## DATA CAVEATS
- Churn assumptions: churn rates promoter 3%, passive 10%, detractor 25% (illustrative); a fixed detractor becomes a passive; churn rates {'promoter': 0.03, 'passive': 0.1, 'detractor': 0.25}
- Low samples: Call Centre (channel, 2026-09, n=26, +15.4 ±31.4)
- Score/comment mismatches: 9 score/comment mismatches (R0003, R0136, R0191, R0195, R0243, R0262, R0273, R0362, R0554); NPS as recorded +18.5, if reversed +21.5, if excluded +20.3 (scores not changed)
- Themes come from keyword rules; TOP_DETRACTOR_THEMES, TOP_PASSIVE_THEMES, TOP_PROMOTER_THEMES derived via keyword matching.