# Risk Engine Spec Fact-Check (DB vs Client Spec)

**Purpose:** Cross-check `vincent doc riskengine` / RISK-ENGINE-SPEC.md against actual `prod_dwh` data.  
**Date:** 2026-02-26  
**DB:** prod_dwh (PostgreSQL), current snapshot.

---

## 1. Schema & Column Mappings

### ✅ Matches (spec is correct)

| Spec claim | DB reality |
|------------|------------|
| `dwh.dim_contract` exists | ✅ Table exists |
| `dwh.dim_party` exists | ✅ Table exists |
| `dwh.dim_car` exists | ✅ Table exists |
| `dwh.dict_contract_status`, `dwh.dict_country` exist | ✅ |
| `ods.crif_score` exists | ✅ Table exists |
| `vehicle_amt`, `downpayment_amt`, `party_customer_orig_key`, `party_dealer_orig_key` in dim_contract | ✅ Columns present |
| `contract_status_key`, `wo_dt`, `del_id`, `dpd`, `cust_contract_type` in dim_contract | ✅ |
| `dscr`, `nationality_key`, `cust_permit`, `birth_dt`, `credit_score_intrum` in dim_party | ✅ |
| `party_orig_key_group`, `crif_score`, `api_call_dttm` in ods.crif_score | ✅ |
| `zek_code`, `zek_closing_reason` in ods.contracts_sst | ✅ |

### ❌ Spec errors or missing sources

| Spec claim | DB reality | Action |
|------------|------------|--------|
| Join ZEK: `ods.contract.id = ods.contracts_sst.contract_id` | No `ods.contract` in list; `contracts_sst` has no `contract_id`. Join that works: **`dwh.dim_contract.contract_orig_key = ods.contracts_sst.crm_representation_id`** | Fix spec: use `contracts_sst.crm_representation_id` and correct table name. |
| CRIF: "Also check decision" / `score_crif(p_crif_decision)` with 'GREEN'/'YELLOW'/'RED' | **No `crif_decision` column** in `ods.crif_score`. Only `crif_score` (numeric). Decision must be **derived** (e.g. ≥700 GREEN, ≥500 YELLOW, else RED). | Implement decision in code/query from `crif_score`; spec should say so. |
| `score_nationality_permit(..., p_residence_years, ...)` | **No `residence_years` (or equivalent) in `dwh.dim_party`.** Closest: `registration_dt` (integer). Spec logic cannot be implemented as written. | Clarify with client: source for residence years or drop from spec. |
| Intrum "0-5 scale" | Data has **-3 to 6** (including negatives and 6). | Extend spec: allow negative and 6, or document mapping. |
| `dict_country` for nationality lookup | Spec references "ISO code for Switzerland" (756). Table has `country_iso_code_2`, `country_iso_code_3` (e.g. CH), not 756. Key 168 is likely CH (1570 rows). **-1** used for unknown (545 rows). | Confirm Swiss key (168 vs 756); treat -1 as unknown. |

---

## 2. Default Definition

Spec: default = `wo_dt IS NOT NULL OR del_id >= 4 OR dpd >= 90`.

| Check | Result |
|-------|--------|
| `wo_dt`, `del_id`, `dpd` columns exist | ✅ |
| Current contracts (current_flg=1) | 3,930 |
| Contracts with wo_dt set | 0 |
| Contracts with del_id >= 4 | 401 |
| Contracts with dpd >= 90 | 290 |
| Contracts satisfying at least one default condition | 414 |

**Conclusion:** Definition is implementable and consistent with data. No fact-check issue.

---

## 3. DSCR

| Spec | DB |
|------|-----|
| DSCR in `dwh.dim_party.dscr`, NULL if not calculated | For **PRIVATE** contracts joined to party: **0 nulls** in sample (2,651 rows). Min -3.71, max 1272.51, avg 15.44. |

**Conclusion:** DSCR is populated for B2C in this slice. Spec’s "NULL if not calculated" is valid; current data has no nulls in this join.

---

## 4. Vehicle Price

| Spec | DB |
|------|-----|
| `vehicle_amt` in dim_contract, CHF | ✅ Present. For PRIVATE: min 11,900, max 330,000, avg 61,451. |
| Critical band 100k–150k "47% default rate" | Not validated (would need default rate by vehicle_amt band). |
| Bands <65k, <75k, <100k, <150k, else | 13 contracts ≥150k, 156 ≥80k. Data supports bands. |

**Conclusion:** Column and ranges are fine. Spec’s 47% default rate is a claim to validate separately with default flags.

---

## 5. CRIF

| Spec | DB |
|------|-----|
| GREEN ≥700, YELLOW 350–<500, RED <350; score_crif(decision) | `ods.crif_score`: only **numeric** `crif_score`. No decision column. |
| Sample (crif_score not null): n=546 | Min 250, max **578**, avg 468. **No score ≥700** (0 rows). 175 in 500–578, 371 <500. |

**Conclusion:**  
- Spec’s "GREEN" band (≥700) **does not appear in current data**; almost all scores are YELLOW or RED.  
- Decision must be derived from `crif_score`; spec should not refer to a stored "decision" field.

---

## 6. Intrum

| Spec | DB |
|------|-----|
| `credit_score_intrum` in dim_party, "0-5 scale" | ✅ Column exists. For PRIVATE: values **-3, -2, -1, 0, 1, 2, 3, 4, 5, 6** (e.g. 957 zeros, 767 fives). |
| score_intrum: ≥4 → 5, ≥1 → 0, else -10 | Negatives (-3 to -1) and 6 need a rule. |

**Conclusion:** Spec’s scale is "0-5"; data has negatives and 6. Extend spec or document mapping.

---

## 7. Permit / Nationality

| Spec | DB |
|------|-----|
| `cust_permit` 'B', 'C', NULL, etc. | ✅ B=454, C=542, NULL=1637, Diplomat=17, L=1. |
| Swiss nationality_key (e.g. 756) | No 756 in sample. **168** = 1570 rows (likely CH). **-1** = 545 (unknown). |

**Conclusion:** Permit distribution supports spec. Confirm Swiss key (168 vs 756) and that -1 = unknown.

---

## 8. Down Payment %

| Spec | DB |
|------|-----|
| Down payment % = downpayment_amt / vehicle_amt * 100 | ✅ Computable. |
| "Only score when ≥11%" | Many contracts 0–10%; 11%+ has meaningful volume (e.g. 43 at 11%). |

**Conclusion:** Spec rule is implementable and data has both sides of 11%.

---

## 9. ZEK

| Spec | DB |
|------|-----|
| ZEK profile 'POSITIVE'/'NEGATIVE' and decision 'approve'/'manual_decision'/'reject' | **Not stored as such.** Only `zek_code` (opaque codes) and `zek_closing_reason`. |
| zek_closing_reason = 'REGULAR_PAYMENTS' → POSITIVE | Only **6** rows with REGULAR_PAYMENTS; **22,174** null/blank. |

**Conclusion:** Spec’s ZEK logic assumes derived POSITIVE/NEGATIVE and decision. Current schema has no such columns; only 6 rows match the only spec-derived rule. **ZEK logic in spec is not implementable as-is** without a clear mapping from `zek_code` / `zek_closing_reason` to profile and decision.

---

## 10. Fraud Risk / Payslip

Spec: `score_fraud_risk(..., p_payslip_check VARCHAR)` with 'PASS'/'WARN'/'FAIL_SOFT'/'FAIL_HIGH_SUSPICION'.  
No `payslip_check` (or equivalent) column found in `dwh.dim_party` or `dwh.dim_contract` in the columns listed. **Source for payslip outcome not identified in current DWH.** Needs clarification.

---

## 11. Dealer Default Rate

Spec: pre-compute dealer default rate; use in score_dealer_risk and check_force_orange (e.g. >0.20).  
Dealer keys and contract counts exist (`party_dealer_orig_key`, default definition). Dealer default rate is **computable** from dim_contract + default definition. No discrepancy.

---

## Summary: What to Change or Clarify

1. **Fix ZEK/contract join:** Use `contracts_sst.crm_representation_id` and correct table name; document that `contract_id` does not exist.
2. **CRIF:** State that decision is **derived** from `crif_score` (no decision column); note that GREEN (≥700) is absent in current data.
3. **Residence years:** No source in dim_party; remove from spec or get source (e.g. from another system).
4. **Intrum:** Extend scale to include negative and 6, or define mapping.
5. **Nationality:** Confirm Swiss key (168 vs 756) and that -1 = unknown.
6. **ZEK:** Define mapping from `zek_code` / `zek_closing_reason` to POSITIVE/NEGATIVE and approve/manual/reject, or accept that ZEK scoring will cover a small subset until mapping exists.
7. **Fraud/payslip:** Identify table/column for payslip check result before implementing score_fraud_risk.

---

*Fact-check based on queries run 2026-02-26 against prod_dwh. Re-run after schema or ETL changes.*
