# Funnel Analytics - Business Specifications

**Purpose:** Enable visibility into where leasing applications drop off and why, so sales and underwriting can collaborate to improve conversion rates.

**Prepared by:** Vincent Van Seumeren
**Date:** 2026-02-01

---

## 1. Executive Summary

### Problem Statement

LeaseTeq processes thousands of leasing applications annually, but lacks visibility into:
- Where in the process applications get stuck or lost
- Why applications fail (rejection reasons buried in free-text notes)
- Whether delays are caused by customers or underwriters
- How B2C (private) and B2B (business) applications differ in conversion

### Solution

A funnel analytics data layer that:
- Tracks applications through 9 defined stages from submission to funding
- Surfaces rejection and drop-off reasons from existing notes data
- Distinguishes customer-pending vs underwriter-pending delays
- Segments all metrics by B2C/B2B for meaningful comparison
- Delivers pre-aggregated metrics for PowerBI dashboard consumption

### Core Value

**Transparency into funnel conversion rates and loss reasons so sales and underwriting can collaborate to increase the percentage of applications that become financed leases.**

---

## 2. Business Context

### Application Journey

1. **Dealer submits application** with car details (vehicle, financing amount, customer info)
2. **Customer receives UAJ link** (User Application Journey) via email
3. **Customer completes UAJ** on LeaseTeq website (personal data, income verification, KYC)
4. **Application enters underwriting** for manual review
5. **Approval or rejection** decision made
6. **Post-approval**: Asset delivery + funding = financed lease

### Customer Types

| Type | Identifier | Volume | Typical Cycle |
|------|------------|--------|---------------|
| **B2C (Private)** | `request_type = 'PRIVATE'` | ~70% | Days to weeks |
| **B2B (Business)** | `request_type = 'BUSINESS'` | ~30% | Weeks to months |

**Key differences:**
- B2C: Payslip review for income verification
- B2B: Balance sheet and P&L review for company financials
- B2B has longer cycles due to more documentation requirements

### Geographic Scope

- **Primary market:** Switzerland (CH)
- **Future expansion:** Austria (AT) - separate dashboard scope
- **Out of scope:** Germany (DE)

---

## 3. Funnel Stage Definitions

The funnel has **9 stages**: 1 pre-funnel, 4 operational, and 4 outcome stages.

### Pre-Funnel Stage

| Stage | Name | Description |
|-------|------|-------------|
| 0 | **Pre-Submission** | Application created but customer hasn't completed data entry |

### Operational Stages (Where Work Happens)

| Stage | Name | Description | What Happens Here |
|-------|------|-------------|-------------------|
| 1 | **Automated Checks** | System-driven verification | Age check, Credit Scoring (Intrum/CRIF), AML, KDF |
| 2 | **KYC + Signing** | Identity verification and contract signing | KYC initiation, IdNow check, QES (Qualified Electronic Signature) |
| 3 | **Underwriting Review** | Manual document and credit review | Document review, Pre-UNW check, underwriter decision |
| 4 | **Activation & Funding** | Final activation and payment | Contract Activation, Funds confirmation |

### Outcome Stages (Terminal States)

| Stage | Name | Description | Business Meaning |
|-------|------|-------------|------------------|
| 5 | **Funded** | Successfully completed | Application converted to financed lease |
| 6 | **Auto-Rejected** | System rejected | Failed automated credit/AML checks (e.g., Intrum score too low) |
| 7 | **Manual-Rejected** | Underwriter rejected | Manually declined after document review |
| 8 | **Customer Drop-off** | Customer abandoned | Customer stopped responding or withdrew |

### Stage Mapping Rules

**Status-based outcomes:**
- `FUNDS_CONFIRMED` → Funded (Stage 5)
- `DECLINED` → Auto-Rejected (Stage 6)
- `REJECTED` → Manual-Rejected (Stage 7)
- `ARCHIVED` → Customer Drop-off (Stage 8)

**Step-based stage assignment:**
- ~78 high-volume flowapp steps are mapped to operational stages 1-4
- Notification steps (emails, partner updates) do NOT advance funnel stage
- Post-funnel steps (contract modifications, terminations) are excluded from funnel analytics

---

## 4. Key Business Metrics

### Conversion Metrics

| Metric | Definition | Business Question |
|--------|------------|-------------------|
| **Stage-to-Final Conversion** | % of applications at stage X that eventually reach Funded | "Of applications that start Underwriting Review, what % get funded?" |
| **Post-Approval Conversion** | % of Approved applications that reach Funded | "How many customers accept after we approve?" |
| **Overall Funnel Conversion** | % of Submitted applications that reach Funded | "What's our end-to-end conversion rate?" |

### Volume Metrics

| Metric | Definition | Business Question |
|--------|------------|-------------------|
| **Current Volume by Stage** | Count of active applications at each stage | "How many applications are in Underwriting Review right now?" |
| **Exit Branch Counts** | Count of applications by outcome type | "How many did we auto-reject vs manual-reject vs customer drop-off?" |

### Time Metrics

| Metric | Definition | Business Question |
|--------|------------|-------------------|
| **Time in Stage** | Days from entering stage to exiting | "How long do applications sit in KYC + Signing?" |
| **Stuck Threshold (P75)** | 75th percentile duration - baseline for "slow" | "What's normal processing time?" |
| **Critical Threshold (P90)** | 90th percentile duration - flags for attention | "When should we escalate?" |

### Loss Metrics

| Metric | Definition | Business Question |
|--------|------------|-------------------|
| **Rejection Rate by Type** | Auto-reject vs Manual-reject counts | "Are we losing more to credit checks or underwriting decisions?" |
| **Top Rejection Reasons** | Extracted phrases from rejection notes | "Why are we rejecting applications?" |
| **Drop-off by Stage** | Where customer abandonment occurs | "Where are customers giving up?" |
| **Post-Approval Drop-offs** | Approved but not funded | "Why do approved customers walk away?" |

### Dealer Metrics

| Metric | Definition | Business Question |
|--------|------------|-------------------|
| **Dealer Conversion Rate** | Funded / Submitted by dealer | "Which dealers send us quality applications?" |
| **Dealer Volume** | Application count by dealer | "Who are our highest-volume partners?" |
| **Dealer Funded Volume** | Total financing amount by dealer | "Who drives the most revenue?" |

---

## 5. B2C vs B2B Segmentation

### Implementation Approach

- **One unified funnel** with customer type as filter (not separate funnels)
- All metrics available with B2C/B2B breakdown
- Side-by-side comparison is primary view
- Combined totals also available

### Why Segmentation Matters

| Aspect | B2C | B2B | Implication |
|--------|-----|-----|-------------|
| Conversion rate | Higher (~60-70%) | Lower (~40-50%) | Don't mix in averages |
| Cycle time | Days | Weeks/months | Different "stuck" thresholds needed |
| Drop-off reasons | Income verification, KYC issues | Documentation complexity | Different intervention strategies |
| Volume | ~70% of applications | ~30% of applications | B2C dominates aggregate metrics |

### Identification

```sql
-- B2C (Private customers)
WHERE request_type = 'PRIVATE'

-- B2B (Business customers)
WHERE request_type = 'BUSINESS'
```

---

## 6. Loss Analysis Specifications

### Three Categories of Loss

| Category | Status | Cause | Dashboard Label |
|----------|--------|-------|-----------------|
| **Auto-Rejected** | `DECLINED` | System rejected due to credit bureau data (Intrum, CRIF) | "Auto-rejected" |
| **Manual-Rejected** | `REJECTED` | Underwriter manually declined after review | "Manual-rejected" |
| **Customer Drop-off** | `ARCHIVED` | Customer abandoned (no response, withdrew, etc.) | "Customer Drop-off" |

### Rejection Reason Extraction

Rejection reasons are extracted from free-text notes using phrase pattern matching:

**Sample phrase patterns (bilingual EN/DE):**
- "insufficient income" / "ungenügendes Einkommen"
- "negative credit" / "negative Bonität"
- "missing documents" / "fehlende Unterlagen"
- "employment verification failed" / "Beschäftigungsnachweis fehlgeschlagen"
- "debt-to-income ratio" / "Schulden-Einkommens-Verhältnis"
- "AML/KYC failed" / "AML/KYC fehlgeschlagen"
- "test application" / "Testantrag"

**Coverage expectation:** 60-80% of rejections will match known phrases. "Unknown" category tracks gaps for pattern additions.

### Responsibility Attribution (Stuck Applications)

For applications that are stuck (exceeding P75 duration), determine who is responsible:

| Responsible Party | Logic | Example |
|-------------------|-------|---------|
| **Customer** | In stages where customer action is required | Waiting for KYC completion, document upload |
| **Underwriter** | In stages where internal action is required | Document review pending, decision pending |
| **Unknown** | Cannot determine from available data | System issues, unclear ownership |

**Stage-based rules (~70-80% accuracy):**
- Stage 2 (KYC + Signing) → Customer responsibility
- Stage 3 (Underwriting Review) → Underwriter responsibility
- Stage 1, 4 → Context-dependent

### Post-Approval Drop-offs

Special attention for applications that were **approved but not funded**:

- These represent high-value losses (we said yes, customer said no)
- Potential insights: pricing issues, competitor wins, customer circumstances changed
- Separate view surfaces these ~100+ cases for review

---

## 7. Time Period Support

### Dashboard Time Horizons

| Horizon | Use Case |
|---------|----------|
| **7 days** | Operational monitoring, immediate issues |
| **30 days** | Monthly review, trend identification |
| **90 days** | Quarterly analysis, pattern recognition |
| **YTD** | Year-to-date performance |
| **12 months rolling** | Full historical context |

### Cohort Analysis

Track applications by submission week:
- "Of 100 applications submitted in Week 1, how many funded by Week 4?"
- Enables conversion rate trending over time
- Weekly grain for trend analysis

---

## 8. Key Business Decisions

Decisions made during development with rationale:

| Decision | Rationale |
|----------|-----------|
| **Stage-to-final conversion (not stage-to-next)** | More actionable: "45% of Underwriting Review apps get funded" vs "85% move to next stage" |
| **One unified funnel with B2C/B2B filter** | Simpler architecture, enables comparison, matches how team thinks |
| **Accumulating snapshot grain** | One row per application with milestone dates - ideal for PowerBI |
| **P75/P90 for stuck thresholds** | Data-driven thresholds from actual completion times, not arbitrary SLAs |
| **Phrase extraction (not raw notes)** | Privacy-safe, actionable categories vs exposing free-text |
| **ARCHIVED = Customer Drop-off** | Business label clearer than technical status name |
| **DECLINED = Auto-rejected** | Distinguishes system decisions from underwriter decisions |
| **Minimum 5 applications for dealer rankings** | Avoids distortion from low-sample dealers |

---

## 9. Data Sources

### Source Tables (Read-Only)

| Table | Purpose |
|-------|---------|
| `ods.contract` | Master application record (status, request_type, dates, dealer) |
| `ods.contract_status_history_sst` | Status change events with timestamps |
| `ods.contract_flowapp_steps_sst` | Step completion events with timestamps |
| `ods.contract_notes_sst` | Free-text notes (rejection reasons, drop-off context) |

### Key Fields

| Field | Table | Business Meaning |
|-------|-------|------------------|
| `representation_id` | contract | Unique application identifier |
| `request_type` | contract | 'PRIVATE' (B2C) or 'BUSINESS' (B2B) |
| `status` | contract | Current application status |
| `submission_date` | contract | When application was submitted |
| `oem_partner_id` | contract | Submitting dealer identifier |
| `step` | flowapp_steps_sst | Completed workflow step name |
| `created_at` | status_history_sst | When status changed |
| `content` | notes_sst | Free-text note content |

---

## 10. PowerBI Dashboards

### Four Dashboard Views

| Dashboard | View Name | Primary Users | Key Questions Answered |
|-----------|-----------|---------------|------------------------|
| **Executive** | `v_powerbi_funnel_executive` | Management | Overall conversion, trends, B2C vs B2B comparison |
| **Operations** | `v_powerbi_funnel_operations` | Operations team | Current volume, stuck apps, exit branches |
| **Loss Analysis** | `v_powerbi_loss_analysis` | Underwriting, Sales | Why are we losing applications? |
| **Dealer Performance** | `v_powerbi_dealer_performance` | Sales, Partner management | Top 10 dealers, conversion by dealer |

### Report Types per Dashboard

**Executive Dashboard:**
- Conversion rate by time horizon (7d, 30d, 90d, YTD)
- B2C vs B2B comparison

**Operations Dashboard:**
- Current Volume (applications by stage)
- Exit Branches (outcomes by type)
- Stuck Applications (exceeding thresholds)

**Loss Analysis Dashboard:**
- Rejection Analysis (auto vs manual, top reasons)
- Drop-off Analysis (by stage, responsibility)
- Stuck Responsibility (customer vs underwriter pending)
- Post-Approval Drop-offs

**Dealer Dashboard:**
- Top 10 by Funded Volume
- Top 10 by Application Count
- Top 10 by Conversion Rate

---

## 11. Known Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Rejection reasons from free-text | 60-80% coverage, not 100% | "Unknown" category tracks gaps; phrase patterns can be extended |
| Responsibility attribution ~70-80% accuracy | Some stuck apps may have incorrect attribution | Stage-based rules are best effort with current data |
| No real-time streaming | Dashboard refresh 3x daily | Sufficient for operational decisions; can increase frequency |
| B2B cycle times vary widely | "Stuck" thresholds may not fit all B2B cases | Separate thresholds by party_type |
| Historical data only (no predictive) | Cannot predict future conversion | Focus on visibility first; ML in future phase |

---

## 12. Future Enhancements (v2)

Explicitly out of scope for v1, documented for future consideration:

- **Structured rejection reasons** - Replace free-text with dropdown in source system
- **Underwriter productivity metrics** - Applications processed per underwriter
- **Automated stuck alerts** - Push notifications when thresholds exceeded
- **Austria (AT) market** - Separate dashboard with BAWAG partner stage
- **Predictive scoring** - ML model for approval likelihood

---

## Appendix: Glossary

| Term | Definition |
|------|------------|
| **UAJ** | User Application Journey - customer-facing application portal |
| **KYC** | Know Your Customer - identity verification process |
| **QES** | Qualified Electronic Signature - legally binding digital signature |
| **AML** | Anti-Money Laundering - regulatory compliance check |
| **KDF** | Customer Due Diligence (Kundenprüfung) |
| **Intrum** | Credit bureau used for B2C credit scoring |
| **CRIF** | Credit bureau used for B2B credit scoring |
| **ZEK** | Swiss credit registry (Zentralstelle für Kreditinformation) |
| **SAAS_DO** | Service/operational contracts (post-funnel lifecycle) |
| **FLOWAPP** | Main application funnel origin |

---

*This document should be read alongside the technical deployment documentation in README.md and DEPLOYMENT_APPROVAL.md.*
