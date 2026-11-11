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
- "The OTP issue is still not fixed. I am moving my salary account." (R0431, score 5, 2026-09, Credit Card)
- "Couldn't get into my account for two days after the update." (R0456, score 5, 2026-09, Credit Card)
- "Locked out of my account three times this week. Login with OTP is broken." (R0428, score 5, 2026-09, Savings Account)
- Root-cause hypothesis: Recent app update deployment introduced critical login and OTP delivery failures, locking users out and driving massive detractor volume in September.

## 3. How much money is at risk?
- Revenue at risk: ₹37.98 lakh of ₹304.43 lakh total revenue (12.5%)
- Where it sits: Wealth=31.51 lakh (83.0% of risk, NPS +1.0)
- Loud is not expensive: loudest complaint call_centre_service (61 customers, 4.73 lakh at risk) vs most expensive complaint fees_charges (24 customers, 10.66 lakh at risk). Loud is not expensive: false - The most frequent complaint is call centre service, but the most expensive complaint in terms of revenue at risk is fees and charges.
- Risk verdict: AMBER

## 4. What do we fix first?
| Rank | By NPS points (all months) | By rupees saved (all months) |
|---|---|---|
| 1 | login_otp_failure - +7.5 NPS points | fees_charges - ₹6.4 lakh saved |
| 2 | fees_charges - +4.0 NPS points | login_otp_failure - ₹2.36 lakh saved |
| 3 | app_performance - +3.5 NPS points | call_centre_service - ₹1.01 lakh saved |
- Recommendation: login_otp_failure - +7.5 NPS points, 2.36 lakh saved, owner: Digital / App team; second track: fees_charges - 6.4 lakh saved, +4.0 NPS points, owner: Wealth product team. Rankings agree: false, and the loudest problem (call centre service) is not the most expensive (fees_charges).

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
| Revenue risk | AMBER | Total revenue at risk is ₹37.98 lakh (12.5% of total revenue) |
| Overall | RED | worst of the two |

## DATA CAVEATS
- Churn assumptions: churn rates promoter 3%, passive 10%, detractor 25% (illustrative); fixed detractor becomes a passive.
- Low samples: Call Centre (channel, 2026-09, n=26, +15.4 ±31.4)
- Score/comment mismatches: 9 score/comment mismatches (R0003, R0136, R0191, R0195, R0243, R0262, R0273, R0362, R0554); ALTERNATIVE_NPS overall: as recorded +18.5, if reversed +21.5, if excluded +20.3; ALTERNATIVE_NPS 2026-09: as recorded -6.5, if reversed -5.5, if excluded -6.0 (scores not changed).
- Themes come from keyword rules; customer feedback is categorized using automated keyword rules.