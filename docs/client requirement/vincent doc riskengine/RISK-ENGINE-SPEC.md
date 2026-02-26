# Risk Engine Specification v1.2

**Purpose:** B2C Credit Scoring Engine for Leasing Applications
**Last Updated:** 2026-01-31
**Status:** Approved for Implementation
**Target Database:** `prod_dwh` (PostgreSQL)

---

## Quick Reference

| Parameter | Value |
|-----------|-------|
| Total Weights | 100% |
| Max Score | +53 points |
| Min Score | -75 points |
| GREEN (auto-approve) | ≥ 25 |
| YELLOW (standard review) | 10-24 |
| ORANGE (enhanced review) | 0-9 |
| RED (decline/escalate) | < 0 |

---

## Schema Reference

### Primary Tables

```sql
-- Core contract and party data
dwh.dim_contract        -- Contract dimension (SCD2)
dwh.dim_party           -- Customer/dealer dimension (SCD2)
dwh.dim_car             -- Vehicle dimension
dwh.dict_contract_status -- Status lookup
dwh.dict_country        -- Country lookup

-- Credit bureau data
ods.crif_score          -- CRIF scores
ods.contracts_sst       -- ZEK data (zek_code, zek_closing_reason, etc.)

-- For dealer analysis
dwh.fact_contract       -- Daily snapshots for historical default rates
```

### Key Joins

```sql
-- Contract to Customer
dim_contract.party_customer_orig_key = dim_party.party_orig_key
    AND dim_party.current_flg = 1

-- Contract to Dealer
dim_contract.party_dealer_orig_key = dim_party.party_orig_key
    AND dim_party.dealer_flg = 1
    AND dim_party.current_flg = 1

-- Contract to Vehicle
dim_contract.car_key = dim_car.car_key
    AND dim_car.current_flg = 1

-- Contract to ZEK (via ODS)
ods.contract.id = ods.contracts_sst.contract_id  -- UUID join

-- Party to CRIF
dim_party.party_orig_key_group = ods.crif_score.party_orig_key_group
```

---

## Column Mappings

| Scoring Factor | Source Table | Column(s) | Data Type | Notes |
|----------------|--------------|-----------|-----------|-------|
| DSCR | `dwh.dim_party` | `dscr` | numeric | NULL if not calculated |
| Vehicle Price | `dwh.dim_contract` | `vehicle_amt` | numeric | CHF, always populated |
| Down Payment | `dwh.dim_contract` | `downpayment_amt` | numeric | CHF |
| Down Payment % | *calculated* | `downpayment_amt / vehicle_amt * 100` | numeric | Handle div/0 |
| Nationality | `dwh.dim_party` | `nationality_key` | integer | FK to dict_country |
| Permit Type | `dwh.dim_party` | `cust_permit` | varchar | 'B', 'C', NULL, etc. |
| Customer Type | `dwh.dim_contract` | `cust_contract_type` | varchar | 'PRIVATE' for B2C |
| Birth Date | `dwh.dim_party` | `birth_dt` | date | For age calculation |
| Intrum Score | `dwh.dim_party` | `credit_score_intrum` | numeric | 0-5 scale |
| CRIF Score | `ods.crif_score` | `crif_score` | numeric | Also check decision |
| ZEK Profile | `ods.contracts_sst` | `zek_code`, `zek_closing_reason` | varchar | See ZEK logic below |
| Dealer ID | `dwh.dim_contract` | `party_dealer_orig_key` | integer | FK to dim_party |
| Contract Status | `dwh.dim_contract` | `contract_status_key` | integer | FK to dict |
| Write-off Date | `dwh.dim_contract` | `wo_dt` | date | NULL = no write-off |
| Delinquency | `dwh.dim_contract` | `del_id` | integer | 0=current, 4+=severe |
| DPD | `dwh.dim_contract` | `dpd` | integer | Days past due |

---

## Default Definition

For model validation and dealer risk calculation:

```sql
-- A contract is considered "defaulted" if:
CASE
    WHEN wo_dt IS NOT NULL THEN 1           -- Written off
    WHEN del_id >= 4 THEN 1                 -- 90+ DPD bucket
    WHEN dpd >= 90 THEN 1                   -- 90+ days past due
    ELSE 0
END AS is_default
```

---

## Scoring Functions (PostgreSQL)

### 1. DSCR Score (18% weight)

```sql
CREATE OR REPLACE FUNCTION score_dscr(p_dscr NUMERIC)
RETURNS INTEGER AS $$
BEGIN
    RETURN CASE
        WHEN p_dscr IS NULL THEN 0
        WHEN p_dscr < 2.0 THEN -15
        WHEN p_dscr < 3.0 THEN -10
        WHEN p_dscr < 4.0 THEN -5
        ELSE 5
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 2. Vehicle Price Score (15% weight)

```sql
CREATE OR REPLACE FUNCTION score_vehicle_price(p_price NUMERIC)
RETURNS INTEGER AS $$
BEGIN
    RETURN CASE
        WHEN p_price IS NULL THEN 0
        WHEN p_price < 65000 THEN 5      -- Low risk band (grouped)
        WHEN p_price < 75000 THEN 0
        WHEN p_price < 100000 THEN -5
        WHEN p_price < 150000 THEN -15   -- CRITICAL: 47% default rate
        ELSE -10
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 3. Nationality/Permit/Residence Score (15% weight)

```sql
CREATE OR REPLACE FUNCTION score_nationality_permit(
    p_nationality_key INTEGER,
    p_permit VARCHAR,
    p_residence_years NUMERIC,
    p_swiss_country_key INTEGER DEFAULT 756  -- ISO code for Switzerland
)
RETURNS INTEGER AS $$
BEGIN
    -- Swiss national
    IF p_nationality_key = p_swiss_country_key THEN
        RETURN 10;
    END IF;

    -- Unknown nationality
    IF p_nationality_key IS NULL THEN
        RETURN -8;
    END IF;

    -- C Permit (settled)
    IF UPPER(p_permit) = 'C' THEN
        RETURN CASE
            WHEN COALESCE(p_residence_years, 0) >= 3 THEN 8
            WHEN COALESCE(p_residence_years, 0) >= 1 THEN 5
            ELSE 2
        END;
    END IF;

    -- B Permit (temporary)
    IF UPPER(p_permit) = 'B' THEN
        RETURN CASE
            WHEN COALESCE(p_residence_years, 0) >= 3 THEN 0
            WHEN COALESCE(p_residence_years, 0) >= 1 THEN -5
            ELSE -10
        END;
    END IF;

    -- Other/unknown permit
    RETURN -5;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 4. Down Payment Score (5% weight)

```sql
CREATE OR REPLACE FUNCTION score_down_payment(
    p_down_payment_amt NUMERIC,
    p_vehicle_amt NUMERIC
)
RETURNS INTEGER AS $$
DECLARE
    v_pct NUMERIC;
BEGIN
    -- Handle edge cases
    IF p_vehicle_amt IS NULL OR p_vehicle_amt = 0 THEN
        RETURN 0;
    END IF;

    v_pct := COALESCE(p_down_payment_amt, 0) / p_vehicle_amt * 100;

    -- KEY: Only score when >= 11%
    RETURN CASE
        WHEN v_pct <= 10 THEN 0    -- NO protective value
        WHEN v_pct < 20 THEN 3
        ELSE 5
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 5. ZEK Score (10% weight)

```sql
CREATE OR REPLACE FUNCTION score_zek(
    p_zek_profile VARCHAR,  -- 'POSITIVE', 'NEGATIVE', NULL
    p_zek_decision VARCHAR  -- 'approve', 'manual_decision', 'reject', NULL
)
RETURNS INTEGER AS $$
DECLARE
    v_profile VARCHAR := UPPER(COALESCE(p_zek_profile, ''));
    v_decision VARCHAR := LOWER(COALESCE(p_zek_decision, ''));
BEGIN
    IF v_profile = '' THEN
        RETURN 0;  -- No ZEK data
    END IF;

    IF v_profile = 'POSITIVE' THEN
        RETURN CASE
            WHEN v_decision = 'approve' THEN 5
            ELSE 0  -- manual or reject with positive profile
        END;
    END IF;

    IF v_profile = 'NEGATIVE' THEN
        RETURN CASE
            WHEN v_decision = 'approve' THEN -5
            WHEN v_decision IN ('manual', 'manual_decision') THEN -10
            WHEN v_decision = 'reject' THEN -15
            ELSE -5
        END;
    END IF;

    RETURN 0;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 6. CRIF Score (7% weight)

```sql
CREATE OR REPLACE FUNCTION score_crif(p_crif_decision VARCHAR)
RETURNS INTEGER AS $$
BEGIN
    RETURN CASE UPPER(COALESCE(p_crif_decision, ''))
        WHEN 'GREEN' THEN 10
        WHEN 'YELLOW' THEN 0
        WHEN 'RED' THEN -15
        ELSE 0  -- No CRIF data
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 7. Intrum Score (5% weight)

```sql
CREATE OR REPLACE FUNCTION score_intrum(
    p_intrum_score NUMERIC,
    p_has_crif BOOLEAN DEFAULT FALSE
)
RETURNS INTEGER AS $$
BEGIN
    -- Skip if CRIF available (no double-counting)
    IF p_has_crif THEN
        RETURN 0;
    END IF;

    RETURN CASE
        WHEN p_intrum_score IS NULL THEN 0
        WHEN p_intrum_score >= 4 THEN 5
        WHEN p_intrum_score >= 1 THEN 0
        ELSE -10
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 8. Age Score (5% weight)

```sql
CREATE OR REPLACE FUNCTION score_age(p_birth_dt DATE)
RETURNS INTEGER AS $$
DECLARE
    v_age INTEGER;
BEGIN
    IF p_birth_dt IS NULL THEN
        RETURN 0;
    END IF;

    v_age := EXTRACT(YEAR FROM AGE(CURRENT_DATE, p_birth_dt));

    RETURN CASE
        WHEN v_age < 25 THEN -5
        WHEN v_age < 35 THEN 0
        WHEN v_age < 50 THEN 3
        WHEN v_age < 65 THEN 5
        ELSE 3
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 9. Dealer Risk Score (10% weight)

```sql
CREATE OR REPLACE FUNCTION score_dealer_risk(
    p_dealer_orig_key INTEGER,
    p_dealer_default_rate NUMERIC,
    p_dealer_name VARCHAR DEFAULT NULL
)
RETURNS INTEGER AS $$
BEGIN
    -- Tesla exception (hardcoded low risk)
    IF UPPER(COALESCE(p_dealer_name, '')) LIKE '%TESLA%' THEN
        RETURN 5;
    END IF;

    -- Known high-risk dealer (Cocelli)
    IF p_dealer_orig_key = 12345 THEN  -- Replace with actual key
        RETURN -15;
    END IF;

    RETURN CASE
        WHEN p_dealer_default_rate IS NULL THEN 0
        WHEN p_dealer_default_rate < 0.05 THEN 3
        WHEN p_dealer_default_rate < 0.10 THEN 0
        WHEN p_dealer_default_rate < 0.20 THEN -10
        ELSE -15
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### 10. Fraud Risk Score (10% weight)

```sql
CREATE OR REPLACE FUNCTION score_fraud_risk(
    p_dealer_fraud_cases INTEGER,
    p_dealer_name VARCHAR,
    p_dealer_age_months INTEGER,
    p_payslip_check VARCHAR  -- 'PASS', 'WARN', 'FAIL_SOFT', 'FAIL_HIGH_SUSPICION'
)
RETURNS INTEGER AS $$
DECLARE
    v_dealer_score INTEGER := 0;
    v_payslip_score INTEGER := 0;
BEGIN
    -- Dealer fraud component (5%)
    IF UPPER(COALESCE(p_dealer_name, '')) LIKE '%TESLA%' THEN
        v_dealer_score := 5;
    ELSIF COALESCE(p_dealer_fraud_cases, 0) = 0 THEN
        v_dealer_score := 3;
    ELSIF p_dealer_fraud_cases = 1 THEN
        v_dealer_score := 0;
    ELSE
        v_dealer_score := -10;
    END IF;

    -- New dealer penalty
    IF COALESCE(p_dealer_age_months, 999) < 6 THEN
        v_dealer_score := v_dealer_score - 3;
    END IF;

    -- Payslip verification component (5%)
    v_payslip_score := CASE UPPER(COALESCE(p_payslip_check, ''))
        WHEN 'PASS' THEN 5
        WHEN 'WARN' THEN 0
        WHEN 'FAIL_SOFT' THEN -5
        WHEN 'FAIL_HIGH_SUSPICION' THEN -15
        ELSE 0
    END;

    RETURN v_dealer_score + v_payslip_score;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

---

## Override Rules

```sql
CREATE OR REPLACE FUNCTION check_force_orange(
    p_vehicle_price NUMERIC,
    p_permit VARCHAR,
    p_nationality_key INTEGER,
    p_zek_profile VARCHAR,
    p_zek_decision VARCHAR,
    p_payslip_check VARCHAR,
    p_dealer_default_rate NUMERIC
)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN (
        -- High-value + B Permit
        (p_vehicle_price >= 80000 AND UPPER(COALESCE(p_permit, '')) = 'B')
        OR
        -- High-value + Unknown nationality
        (p_vehicle_price >= 80000 AND p_nationality_key IS NULL)
        OR
        -- ZEK NEGATIVE + Manual
        (UPPER(COALESCE(p_zek_profile, '')) = 'NEGATIVE'
         AND LOWER(COALESCE(p_zek_decision, '')) IN ('manual', 'manual_decision'))
        OR
        -- Payslip high suspicion
        (UPPER(COALESCE(p_payslip_check, '')) = 'FAIL_HIGH_SUSPICION')
        OR
        -- High-risk dealer
        (COALESCE(p_dealer_default_rate, 0) > 0.20)
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

---

## Complete Scoring Query

```sql
WITH contract_base AS (
    SELECT
        c.contract_orig_key,
        c.vehicle_amt,
        c.downpayment_amt,
        c.party_customer_orig_key,
        c.party_dealer_orig_key,
        p.dscr,
        p.nationality_key,
        p.cust_permit,
        p.birth_dt,
        p.credit_score_intrum,
        d.party_first_name || ' ' || d.party_last_name AS dealer_name
    FROM dwh.dim_contract c
    JOIN dwh.dim_party p
        ON c.party_customer_orig_key = p.party_orig_key
        AND p.current_flg = 1
    LEFT JOIN dwh.dim_party d
        ON c.party_dealer_orig_key = d.party_orig_key
        AND d.current_flg = 1
    WHERE c.current_flg = 1
      AND c.cust_contract_type = 'PRIVATE'
),

dealer_stats AS (
    SELECT
        party_dealer_orig_key,
        COUNT(*) AS total_contracts,
        SUM(CASE WHEN wo_dt IS NOT NULL OR del_id >= 4 THEN 1 ELSE 0 END) AS defaults,
        SUM(CASE WHEN wo_dt IS NOT NULL OR del_id >= 4 THEN 1 ELSE 0 END)::NUMERIC
            / NULLIF(COUNT(*), 0) AS default_rate
    FROM dwh.dim_contract
    WHERE current_flg = 1
      AND cust_contract_type = 'PRIVATE'
      AND activation_dt < CURRENT_DATE - INTERVAL '12 months'  -- Mature contracts only
    GROUP BY party_dealer_orig_key
),

zek_data AS (
    SELECT DISTINCT ON (contract_id)
        contract_id,
        CASE
            WHEN zek_closing_reason = 'REGULAR_PAYMENTS' THEN 'POSITIVE'
            WHEN zek_code IS NOT NULL THEN 'POSITIVE'  -- Has ZEK entry
            ELSE NULL
        END AS zek_profile,
        'approve' AS zek_decision  -- Derive from actual decision field
    FROM ods.contracts_sst
    WHERE zek_code IS NOT NULL
    ORDER BY contract_id, created_at DESC
),

crif_data AS (
    SELECT DISTINCT ON (party_orig_key_group)
        party_orig_key_group,
        CASE
            WHEN crif_score >= 700 THEN 'GREEN'
            WHEN crif_score >= 500 THEN 'YELLOW'
            ELSE 'RED'
        END AS crif_decision
    FROM ods.crif_score
    ORDER BY party_orig_key_group, api_call_dttm DESC
),

scores AS (
    SELECT
        cb.contract_orig_key,

        -- Individual scores
        score_dscr(cb.dscr) AS dscr_score,
        score_vehicle_price(cb.vehicle_amt) AS vehicle_price_score,
        score_nationality_permit(cb.nationality_key, cb.cust_permit, NULL) AS nationality_score,
        score_down_payment(cb.downpayment_amt, cb.vehicle_amt) AS down_payment_score,
        score_zek(zd.zek_profile, zd.zek_decision) AS zek_score,
        score_crif(cd.crif_decision) AS crif_score,
        score_intrum(cb.credit_score_intrum, cd.crif_decision IS NOT NULL) AS intrum_score,
        score_age(cb.birth_dt) AS age_score,
        score_dealer_risk(cb.party_dealer_orig_key, ds.default_rate, cb.dealer_name) AS dealer_risk_score,
        score_fraud_risk(NULL, cb.dealer_name, NULL, NULL) AS fraud_risk_score,

        -- Override check
        check_force_orange(
            cb.vehicle_amt,
            cb.cust_permit,
            cb.nationality_key,
            zd.zek_profile,
            zd.zek_decision,
            NULL,  -- payslip_check
            ds.default_rate
        ) AS force_orange,

        -- Raw data for debugging
        cb.vehicle_amt,
        cb.dscr,
        cb.cust_permit,
        cb.nationality_key,
        ds.default_rate AS dealer_default_rate

    FROM contract_base cb
    LEFT JOIN dealer_stats ds ON cb.party_dealer_orig_key = ds.party_dealer_orig_key
    LEFT JOIN zek_data zd ON cb.contract_orig_key::text = zd.contract_id::text
    LEFT JOIN crif_data cd ON cb.party_customer_orig_key = cd.party_orig_key_group
)

SELECT
    contract_orig_key,

    -- Component scores
    dscr_score,
    vehicle_price_score,
    nationality_score,
    down_payment_score,
    zek_score,
    crif_score,
    intrum_score,
    age_score,
    dealer_risk_score,
    fraud_risk_score,

    -- Total score
    (dscr_score + vehicle_price_score + nationality_score + down_payment_score +
     zek_score + crif_score + intrum_score + age_score +
     dealer_risk_score + fraud_risk_score) AS total_score,

    -- Decision tier
    CASE
        WHEN force_orange AND (dscr_score + vehicle_price_score + nationality_score +
             down_payment_score + zek_score + crif_score + intrum_score + age_score +
             dealer_risk_score + fraud_risk_score) >= 10 THEN 'ORANGE'
        WHEN (dscr_score + vehicle_price_score + nationality_score + down_payment_score +
              zek_score + crif_score + intrum_score + age_score +
              dealer_risk_score + fraud_risk_score) >= 25 THEN 'GREEN'
        WHEN (dscr_score + vehicle_price_score + nationality_score + down_payment_score +
              zek_score + crif_score + intrum_score + age_score +
              dealer_risk_score + fraud_risk_score) >= 10 THEN 'YELLOW'
        WHEN (dscr_score + vehicle_price_score + nationality_score + down_payment_score +
              zek_score + crif_score + intrum_score + age_score +
              dealer_risk_score + fraud_risk_score) >= 0 THEN 'ORANGE'
        ELSE 'RED'
    END AS decision_tier,

    force_orange,

    -- Debug columns
    vehicle_amt,
    dscr,
    cust_permit,
    dealer_default_rate

FROM scores;
```

---

## Dealer Default Rate Calculation

Pre-compute and store in a lookup table (refresh daily/weekly):

```sql
CREATE TABLE IF NOT EXISTS dwh.dealer_risk_metrics AS
SELECT
    d.party_orig_key AS dealer_orig_key,
    d.party_first_name || ' ' || COALESCE(d.party_last_name, '') AS dealer_name,
    COUNT(DISTINCT c.contract_orig_key) AS total_contracts,
    COUNT(DISTINCT c.contract_orig_key) FILTER (
        WHERE c.wo_dt IS NOT NULL OR c.del_id >= 4
    ) AS total_defaults,
    ROUND(
        COUNT(DISTINCT c.contract_orig_key) FILTER (WHERE c.wo_dt IS NOT NULL OR c.del_id >= 4)::NUMERIC /
        NULLIF(COUNT(DISTINCT c.contract_orig_key), 0),
        4
    ) AS default_rate,
    MIN(c.activation_dt) AS first_contract_dt,
    EXTRACT(MONTH FROM AGE(CURRENT_DATE, MIN(c.activation_dt))) AS dealer_age_months
FROM dwh.dim_party d
JOIN dwh.dim_contract c
    ON d.party_orig_key = c.party_dealer_orig_key
    AND c.current_flg = 1
    AND c.cust_contract_type = 'PRIVATE'
WHERE d.dealer_flg = 1
  AND d.current_flg = 1
GROUP BY d.party_orig_key, d.party_first_name, d.party_last_name
HAVING COUNT(DISTINCT c.contract_orig_key) >= 5;  -- Minimum volume threshold
```

---

## Validation Queries

### 1. Score Distribution Check

```sql
-- Verify score distribution matches expected ranges
SELECT
    decision_tier,
    COUNT(*) AS contracts,
    ROUND(AVG(total_score), 2) AS avg_score,
    MIN(total_score) AS min_score,
    MAX(total_score) AS max_score,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM scoring_results
GROUP BY decision_tier
ORDER BY
    CASE decision_tier
        WHEN 'GREEN' THEN 1
        WHEN 'YELLOW' THEN 2
        WHEN 'ORANGE' THEN 3
        ELSE 4
    END;
```

### 2. Default Rate by Tier (Backtesting)

```sql
-- Compare actual default rates by predicted tier
SELECT
    decision_tier,
    COUNT(*) AS contracts,
    SUM(is_default) AS defaults,
    ROUND(100.0 * SUM(is_default) / COUNT(*), 2) AS default_rate_pct
FROM scoring_results sr
JOIN (
    SELECT
        contract_orig_key,
        CASE WHEN wo_dt IS NOT NULL OR del_id >= 4 THEN 1 ELSE 0 END AS is_default
    FROM dwh.dim_contract
    WHERE current_flg = 1
      AND activation_dt < CURRENT_DATE - INTERVAL '12 months'
) d ON sr.contract_orig_key = d.contract_orig_key
GROUP BY decision_tier
ORDER BY default_rate_pct;
```

### 3. Factor Contribution Analysis

```sql
-- See which factors contribute most to score variance
SELECT
    'dscr_score' AS factor,
    AVG(dscr_score) AS avg_score,
    STDDEV(dscr_score) AS stddev,
    MIN(dscr_score) AS min_val,
    MAX(dscr_score) AS max_val
FROM scoring_results
UNION ALL
SELECT 'vehicle_price_score', AVG(vehicle_price_score), STDDEV(vehicle_price_score), MIN(vehicle_price_score), MAX(vehicle_price_score) FROM scoring_results
UNION ALL
SELECT 'nationality_score', AVG(nationality_score), STDDEV(nationality_score), MIN(nationality_score), MAX(nationality_score) FROM scoring_results
-- ... repeat for all factors
ORDER BY stddev DESC;
```

### 4. Override Rule Frequency

```sql
-- How often do override rules trigger?
SELECT
    force_orange,
    decision_tier AS original_tier,
    COUNT(*) AS contracts,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM scoring_results
GROUP BY force_orange, decision_tier
ORDER BY force_orange DESC, decision_tier;
```

---

## Data Quality Checks

```sql
-- Run before scoring to identify data issues
SELECT
    'NULL DSCR' AS check_name,
    COUNT(*) AS affected_contracts
FROM dwh.dim_contract c
JOIN dwh.dim_party p ON c.party_customer_orig_key = p.party_orig_key AND p.current_flg = 1
WHERE c.current_flg = 1
  AND c.cust_contract_type = 'PRIVATE'
  AND p.dscr IS NULL

UNION ALL

SELECT 'NULL vehicle_amt', COUNT(*)
FROM dwh.dim_contract
WHERE current_flg = 1 AND cust_contract_type = 'PRIVATE' AND vehicle_amt IS NULL

UNION ALL

SELECT 'NULL nationality', COUNT(*)
FROM dwh.dim_contract c
JOIN dwh.dim_party p ON c.party_customer_orig_key = p.party_orig_key AND p.current_flg = 1
WHERE c.current_flg = 1 AND c.cust_contract_type = 'PRIVATE' AND p.nationality_key IS NULL

UNION ALL

SELECT 'NULL birth_dt (cannot calc age)', COUNT(*)
FROM dwh.dim_contract c
JOIN dwh.dim_party p ON c.party_customer_orig_key = p.party_orig_key AND p.current_flg = 1
WHERE c.current_flg = 1 AND c.cust_contract_type = 'PRIVATE' AND p.birth_dt IS NULL

UNION ALL

SELECT 'Vehicle price > 150k (small sample)', COUNT(*)
FROM dwh.dim_contract
WHERE current_flg = 1 AND cust_contract_type = 'PRIVATE' AND vehicle_amt >= 150000;
```

---

## Performance Considerations

1. **Index Recommendations:**
```sql
CREATE INDEX IF NOT EXISTS idx_dim_contract_scoring
ON dwh.dim_contract (party_customer_orig_key, party_dealer_orig_key, current_flg, cust_contract_type);

CREATE INDEX IF NOT EXISTS idx_dim_party_scoring
ON dwh.dim_party (party_orig_key, current_flg);

CREATE INDEX IF NOT EXISTS idx_crif_score_lookup
ON ods.crif_score (party_orig_key_group, api_call_dttm DESC);
```

2. **Pre-compute dealer metrics** daily rather than calculating inline.

3. **Use materialized views** for scoring if real-time not required:
```sql
CREATE MATERIALIZED VIEW dwh.mv_contract_scores AS
-- (scoring query here)
WITH DATA;

CREATE UNIQUE INDEX ON dwh.mv_contract_scores (contract_orig_key);

-- Refresh daily
REFRESH MATERIALIZED VIEW CONCURRENTLY dwh.mv_contract_scores;
```

---

## Edge Cases & NULL Handling

| Scenario | Handling |
|----------|----------|
| DSCR = NULL | Score = 0 (neutral) |
| Vehicle price = NULL | Score = 0 (should not happen) |
| Down payment = NULL | Treat as 0% → Score = 0 |
| Nationality = NULL | Score = -8 (unknown penalty) |
| Permit = NULL | Use nationality-only logic |
| Birth date = NULL | Age score = 0 |
| Intrum = NULL | Score = 0 |
| CRIF = NULL | Use Intrum instead |
| ZEK = NULL | Score = 0 |
| Division by zero (down pmt %) | Return 0 |
| New dealer (< 5 contracts) | Exclude from dealer_risk_metrics, use score = 0 |

---

## Model Parameters (for config file)

```yaml
scoring_model:
  version: "1.2"
  effective_date: "2026-01-31"

  tier_thresholds:
    green: 25
    yellow: 10
    orange: 0
    # red: < 0

  weights:
    dscr: 0.18
    vehicle_price: 0.15
    nationality_permit: 0.15
    fraud_risk: 0.10
    dealer_risk: 0.10
    zek_profile: 0.10
    crif_score: 0.07
    down_payment: 0.05
    intrum_score: 0.05
    age: 0.05

  critical_thresholds:
    dscr_high_risk: 2.0
    vehicle_price_critical: 100000
    down_payment_minimum_effective: 11
    dealer_high_risk_rate: 0.20
    b_permit_high_value_vehicle: 80000

  known_entities:
    tesla_dealers: ["Tesla Switzerland", "Tesla Motors Switzerland"]
    high_risk_dealers: ["Cocelli Automobiles"]
    swiss_country_key: 756
```

---

## Contacts & References

| Resource | Location |
|----------|----------|
| Full validation report | `.planning/WEIGHT-VALIDATION-REPORT.md` |
| HTML executive summary | `.planning/SCORING-MODEL-EXECUTIVE-SUMMARY.html` |
| DWH schema reference | `/Claude/DWH_SCHEMA.md` |
| IV/WOE analysis data | `/tmp/iv_woe_data.csv` |
| ZEK profile data | `/tmp/zek_profile.csv` |

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-31 | Initial model |
| 1.1 | 2026-01-31 | Added fraud risk, nationality/permit |
| 1.2 | 2026-01-31 | Down payment threshold (≥11%), vehicle price 5-tier, ZEK forward-looking |
