# Payslip Analysis Summary

## Analysis Date: 31 January 2026

---

## Overview

| # | File | Employer | Employee | Verdict | Confidence |
|---|------|----------|----------|---------|------------|
| 1 | Payslip1.jpg | ZEREY GmbH | Fesu Constantin | FRAUDULENT | 95%+ |
| 2 | Payslip3.pdf | COOP Pronto | Roller Dylan | FRAUDULENT | 95%+ |
| 3 | Gotlieb.pdf | TAVAS Gastro | Iulian Pitigoi | FRAUDULENT | 90%+ |
| 4 | Bate.pdf | BATE.CH | Nita Roxana | FRAUDULENT | 95%+ |
| 5 | Lohnabrechnungen 29.01.26 1.pdf | Carrosserie Hess AG | Lorenzo Ackermann | LEGITIMATE | 90%+ |

---

## Detailed Findings

### 1. Payslip1.jpg (ZEREY GmbH)
**VERDICT: FRAUDULENT**

| Field | Value |
|-------|-------|
| Employee | Fesu Constantin |
| Gross | CHF 5,400.00 |
| Location | Not specified |

**Fraud Indicators:**
- Mathematical inconsistency: Sum of deductions (CHF 1,000.55) ≠ Stated total (CHF 1,055.55)
- CHF 55 discrepancy
- Quellensteuer calculation error (stated 413.00, calculated 415.80)
- Missing UID number
- Net salary calculation inconsistent

---

### 2. Payslip3.pdf (COOP Pronto)
**VERDICT: FRAUDULENT**

| Field | Value |
|-------|-------|
| Employee | Roller Dylan |
| Address | Rue Auguste Matringe 6, 1180 Rolle |
| Period | November 2025 |
| Gross | CHF 5,500.00 |
| Net | CHF 4,803.49 |

**Metadata Analysis:**
| Field | Value | Issue |
|-------|-------|-------|
| Author | Word | Not payroll software |
| Creator | Word | Manual creation |
| Title | "Salaire Coop Avril. 24" | MISMATCH - content says November 2025 |
| Created | Recent | Template reuse |

**Fraud Indicators:**
- Metadata title "April 2024" but content shows "November 2025"
- Created in Microsoft Word, not payroll software
- Missing employer UID
- Missing employee AHV number
- IBAN concatenated with "R Solde/Report" text

**Mathematics:** Correct (but doesn't prove authenticity)

---

### 3. Gotlieb.pdf (TAVAS Gastro)
**VERDICT: FRAUDULENT**

| Field | Value |
|-------|-------|
| Employee | Iulian Pitigoi |
| Address | Dorfstrasse 7A, 5417 Untersiggenthal |
| AHV Nr. | 756.9733.2488.04 |
| Periods | August, September, October 2025 |
| Gross | CHF 9,000.00 (all months) |
| Net | CHF 6,543.10 (all months) |

**Metadata Analysis:**
| Field | Value | Issue |
|-------|-------|-------|
| Creator | iOS Version 18.5 Quartz PDFContext | iPhone creation |
| File Size | 1.8 MB for 3 pages | Image-based |

**Fraud Indicators:**
- Created on iPhone, not payroll software
- L-GAV Beitrag = CHF 0.00 (MANDATORY for Gastro industry)
- Missing employer UID

**Note:** Identical values across 3 months is NOT itself a fraud indicator - fixed-salary employees legitimately have identical payslips month-to-month.

**Deduction Details (all 3 months identical):**
| Deduction | Amount |
|-----------|--------|
| AHV | 477.00 |
| ALV | 99.00 |
| BVG | 457.10 |
| NBU-Prämie | 181.80 |
| Krankentaggeld | 162.00 |
| L-GAV | 0.00 (ERROR) |
| Quellensteuer | 1,080.00 |

---

### 4. Bate.pdf (BATE.CH)
**VERDICT: FRAUDULENT**

| Field | Value |
|-------|-------|
| Employee | Nita Roxana |
| Address | Wolframplatz 1, 8045 Zürich |
| AHV Nr. | 756.9709.8392.41 |
| Period | "Lohnabrechnung August" (NO YEAR) |
| Datum | 03.02.1994 (!) |
| Gross | CHF 6,300.00 |
| Net | CHF 5,306.50 |

**Metadata Analysis:**
| Field | Value | Issue |
|-------|-------|-------|
| Author | profcan | Personal username |
| Creator | Microsoft Word 2019 | Not payroll software |
| Created | 26 November 2025 | |

**Fraud Indicators:**
- Author "profcan" = personal account, not payroll system
- Date shows 03.02.1994 (likely birthdate entered by mistake)
- No year specified in payslip title
- Invalid Quellensteuer code "L" (doesn't exist in Swiss system)
- Missing BVG/pension contribution (mandatory)
- Created in Microsoft Word
- Missing employer UID

**Deduction Details:**
| Deduction | Rate | Amount |
|-----------|------|--------|
| AHV | 5.30% | 333.90 |
| ALV | 1.10% | 69.30 |
| NBU | 2.02% | 127.25 |
| Quellensteuer "L" | 7.35% | 463.05 |
| BVG | MISSING | - |

---

### 5. Lohnabrechnungen 29.01.26 1.pdf (Carrosserie Hess AG)
**VERDICT: LEGITIMATE**

| Field | Value |
|-------|-------|
| Employee | Herr Lorenzo Ackermann |
| Address | Heidenhubelstrasse 20, 4500 Solothurn |
| MA-Nr | 10308 |
| AHV Nr. | 756.1082.7152.28 |
| Anstellung | 100.00% |
| Period | 01.12.2025 - 31.12.2025 |
| Valutadatum | 19.12.2025 |
| Kostenstelle | Projektleitung |
| Gross | CHF 14,050.00 (incl. 13th salary) |
| Net Payout | CHF 12,689.90 |
| Bank | Raiffeisen, St. Gallen (80808) |
| IBAN | CH91 8080 8009 0209 1009 9 |

**Metadata Analysis:**
| Field | Value | Assessment |
|-------|-------|------------|
| Producer | macOS Quartz PDFContext | Likely scanned |
| File Size | 8.1 MB | Image/scan |

**Authenticity Indicators:**
- Professional Lohnart codes (1001, 2001, 2005, 2101, 2501, etc.)
- Employee ID (MA-Nr: 10308)
- Cost center (Kostenstelle: Projektleitung)
- Full AHV number
- Employment percentage
- Specific pay period with dates
- Valutadatum (payment date)
- 13th salary in December (Swiss standard)
- Vacation tracking (4 separate fields)
- Company-specific deduction (Benzin: -99.15)
- Real, verifiable company (Carrosserie Hess AG, est. 1882)
- All mathematics perfect

**Salary Structure:**
| Code | Description | Amount |
|------|-------------|--------|
| 1001 | Salär | 7,025.00 |
| 1405 | 13. Gehalt | 7,025.00 |
| 1999 | Bruttolohn | 14,050.00 |

**Deductions:**
| Code | Description | Rate | Amount |
|------|-------------|------|--------|
| 2001 | AHV-Abzug | 5.30% | -744.65 |
| 2005 | ALV-Abzug | 1.10% | -154.55 |
| 2101 | KTG-Abzug | 0.81% | -113.80 |
| 2501 | PK-Beitrag | flat | -247.95 |
| 2799 | Total Abzüge | | -1,260.95 |

**Vacation Tracking:**
| Code | Description | Days |
|------|-------------|------|
| 6501 | Feriensaldo VJ | 2.00 |
| 6503 | Ferienanrecht aktuelles Jahr | 20.00 |
| 6504 | Saldo Bezug | 17.00 |
| 6505 | Ferienbezug | 5.00 |

---

## Key Patterns Identified

### Common Fraud Patterns

1. **Microsoft Word Creation**
   - Seen in: Payslip3.pdf, Bate.pdf
   - Legitimate payslips come from payroll software

2. **iPhone/iOS Creation**
   - Seen in: Gotlieb.pdf
   - Suggests manual document creation

3. **Metadata Title Mismatch**
   - Seen in: Payslip3.pdf ("April 24" vs "November 2025")
   - Template reuse without updating properties

4. **Personal Author Names**
   - Seen in: Bate.pdf (author "profcan")
   - Should be system/company name

5. **Missing Mandatory Elements**
   - Missing BVG: Bate.pdf
   - Missing L-GAV: Gotlieb.pdf (Gastro sector)
   - Missing UID: All fraudulent documents

6. **Invalid Data**
   - Invalid date (1994): Bate.pdf
   - Invalid tax code "L": Bate.pdf
   - No year specified: Bate.pdf

### Legitimacy Indicators

1. **Professional Lohnart Codes** (1001, 2001, etc.)
2. **Employee ID Numbers** (MA-Nr, Pers-Nr)
3. **Cost Center Allocation**
4. **Vacation Tracking Fields**
5. **13th Salary in December**
6. **Company-Specific Deductions**
7. **Verifiable Real Company**
8. **Complete Employee Information**

---

## Recommendations

### For Underwriting Team

1. **Always check metadata first** - fastest fraud indicator
2. **Verify AHV = 5.30% and ALV = 1.10%** - non-negotiable rates
3. **Look for Lohnart codes** - indicates real payroll software
4. **Check for BVG** on salaries > CHF 22,050/year
5. **Verify company exists** via Zefix.ch
6. **Request multiple months** - identical months = fraud
7. **Check Quellensteuer codes** are valid (A, B, C, H, etc.)

### High-Risk Indicators (Immediate Rejection)
- Created in Word/iPhone
- Personal author name in metadata
- Metadata title doesn't match content
- Invalid tax codes
- Date from distant past
- Missing mandatory contributions (BVG, L-GAV for gastro)

