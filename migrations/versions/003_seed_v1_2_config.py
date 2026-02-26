"""
003 — Seed initial v1.2 model configuration

Populates all calibration tables with the v1.2 scoring model parameters.
This is the baseline that can be adjusted through the UI.

Revision ID: 003
Create Date: 2026-02-26
"""
from alembic import op
from datetime import datetime, timezone

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

SCHEMA = "lt_risk_engine"


def upgrade() -> None:
    conn = op.get_bind()

    # ── Model Version ──
    conn.execute(
        sa_text(f"""
        INSERT INTO {SCHEMA}.model_version (version_id, description, status, published_at, published_by, created_by)
        VALUES ('1.2.0', 'Initial v1.2 model - 10 factor composite scoring', 'PUBLISHED', NOW(), 'system', 'system')
        """)
    )

    # ── Factor Configs ──
    factors = [
        ("LTV", 0.15, "Loan-to-Value ratio", -8, 8, 1),
        ("Term", 0.10, "Contract term length in months", -3, 6, 2),
        ("Age", 0.10, "Customer age at application", -10, 7, 3),
        ("CRIF", 0.15, "CRIF bureau score (0-1000)", -8, 8, 4),
        ("Intrum", 0.10, "Intrum debt collection score", -4, 5, 5),
        ("DSCR", 0.15, "Debt Service Coverage Ratio", -8, 7, 6),
        ("Permit", 0.10, "Party type + Swiss residence permit", -3, 5, 7),
        ("VehiclePriceTier", 0.05, "Vehicle price segment", -2, 3, 8),
        ("ZEK", 0.05, "ZEK credit information entries", -7, 5, 9),
        ("DealerRisk", 0.05, "Dealer historical default rate", -6, 4, 10),
    ]
    for name, weight, desc, smin, smax, order in factors:
        conn.execute(sa_text(f"""
            INSERT INTO {SCHEMA}.scoring_factor_config
                (version_id, factor_name, weight, enabled, description, score_range_min, score_range_max, display_order)
            VALUES ('1.2.0', '{name}', {weight}, true, '{desc}', {smin}, {smax}, {order})
        """))

    # ── Factor Bins ──
    bins = [
        # LTV
        ("LTV", 1, "<75%", None, 75, False, False, None, False, 8, "Strong equity cushion"),
        ("LTV", 2, "75-85%", 75, 85, True, True, None, False, 4, "Adequate equity"),
        ("LTV", 3, "85-95%", 85, 95, False, True, None, False, 0, "Neutral"),
        ("LTV", 4, ">95%", 95, None, False, False, None, False, -8, "Minimal equity"),
        ("LTV", 5, "MISSING", None, None, False, False, None, True, -5, "Cannot assess"),

        # Term
        ("Term", 1, "≤36m", None, 36, False, True, None, False, 5, "Short term"),
        ("Term", 2, "37-48m", 37, 48, True, True, None, False, 6, "Optimal term"),
        ("Term", 3, ">48m", 48, None, False, False, None, False, -3, "Long exposure"),

        # Age
        ("Age", 1, "<18", None, 18, False, False, None, False, -10, "Minor"),
        ("Age", 2, "18-25", 18, 25, True, True, None, False, -6, "Young adult"),
        ("Age", 3, "26-35", 26, 35, True, True, None, False, 2, "Early career"),
        ("Age", 4, "36-45", 36, 45, True, True, None, False, 0, "Mid career"),
        ("Age", 5, "46-55", 46, 55, True, True, None, False, 7, "Peak earning"),
        ("Age", 6, "56+", 56, None, True, False, None, False, -2, "Senior"),

        # CRIF
        ("CRIF", 1, "≥700", 700, None, True, False, None, False, 8, "Excellent"),
        ("CRIF", 2, "500-699", 500, 699, True, True, None, False, 4, "Good"),
        ("CRIF", 3, "300-499", 300, 499, True, True, None, False, -2, "Fair"),
        ("CRIF", 4, "<300", None, 300, False, False, None, False, -8, "Poor"),
        ("CRIF", 5, "MISSING", None, None, False, False, None, True, -5, "No data"),

        # Intrum
        ("Intrum", 1, "0 (No data)", None, None, False, False, "0", False, -4, "Unverifiable"),
        ("Intrum", 2, "1", None, None, False, False, "1", False, 1, "Minimal history"),
        ("Intrum", 3, "2-3", 2, 3, True, True, None, False, -1, "Some concerns"),
        ("Intrum", 4, ">3", 3, None, False, False, None, False, 5, "Established"),

        # DSCR
        ("DSCR", 1, "<0 (Negative)", None, 0, False, False, None, False, -8, "Cannot service"),
        ("DSCR", 2, "0-3 (Tight)", 0, 3, True, True, None, False, -3, "Minimal headroom"),
        ("DSCR", 3, "3-7 (Adequate)", 3, 7, False, True, None, False, 0, "Meets minimum"),
        ("DSCR", 4, "7-15 (Good)", 7, 15, False, True, None, False, 3, "Comfortable"),
        ("DSCR", 5, ">15 (Strong)", 15, None, False, False, None, False, 7, "Very strong"),
        ("DSCR", 6, "MISSING", None, None, False, False, None, True, -5, "Cannot calculate"),

        # Permit (categorical — uses match_value)
        ("Permit", 1, "B2B", None, None, False, False, "B2B", False, -3, "Business applicant"),
        ("Permit", 2, "B_permit", None, None, False, False, "B", False, -3, "Temporary residence"),
        ("Permit", 3, "C_permit", None, None, False, False, "C", False, 5, "Permanent settlement"),
        ("Permit", 4, "L/Diplomat", None, None, False, False, "L", False, -1, "Short-term"),
        ("Permit", 5, "Other_B2C", None, None, False, False, None, False, 2, "Default B2C"),

        # VehiclePriceTier
        ("VehiclePriceTier", 1, "≤20k", None, 20000, False, True, None, False, -2, "Economy"),
        ("VehiclePriceTier", 2, "20k-50k", 20000, 50000, False, True, None, False, 3, "Mid range"),
        ("VehiclePriceTier", 3, "50k-100k", 50000, 100000, False, True, None, False, 2, "Premium"),
        ("VehiclePriceTier", 4, ">100k", 100000, None, False, False, None, False, -1, "Luxury"),

        # ZEK
        ("ZEK", 1, "Clean", None, None, False, False, "clean", False, 5, "No negatives"),
        ("ZEK", 2, "1 entry", None, None, False, False, "1", False, -3, "Isolated incident"),
        ("ZEK", 3, "2+ entries", None, None, False, False, "2+", False, -7, "Pattern of issues"),
        ("ZEK", 4, "NOT_CHECKED", None, None, False, False, None, True, 0, "Not queried"),

        # DealerRisk
        ("DealerRisk", 1, "≤3% (Low)", None, 0.03, False, True, None, False, 4, "Trusted partner"),
        ("DealerRisk", 2, "3-8% (Average)", 0.03, 0.08, False, True, None, False, 0, "Normal"),
        ("DealerRisk", 3, "8-15% (Elevated)", 0.08, 0.15, False, True, None, False, -3, "Under watch"),
        ("DealerRisk", 4, ">15% (High)", 0.15, None, False, False, None, False, -6, "Watchlist"),
        ("DealerRisk", 5, "New/Unknown", None, None, False, False, None, True, -2, "Unproven"),
    ]

    for b in bins:
        factor, order, label, lo, hi, lo_inc, hi_inc, match, is_miss, score, interp = b
        lo_str = str(lo) if lo is not None else "NULL"
        hi_str = str(hi) if hi is not None else "NULL"
        match_str = f"'{match}'" if match else "NULL"
        conn.execute(sa_text(f"""
            INSERT INTO {SCHEMA}.scoring_factor_bins
                (version_id, factor_name, bin_order, bin_label, lower_bound, upper_bound,
                 lower_inclusive, upper_inclusive, match_value, is_missing_bin, raw_score, risk_interpretation)
            VALUES ('1.2.0', '{factor}', {order}, '{label}', {lo_str}, {hi_str},
                    {str(lo_inc).lower()}, {str(hi_inc).lower()}, {match_str}, {str(is_miss).lower()}, {score}, '{interp}')
        """))

    # ── Tier Thresholds ──
    tiers = [
        ("BRIGHT_GREEN", 1, 25, "AUTO_APPROVE", 0.015, "#27AE60", "Auto-approve, standard terms"),
        ("GREEN", 2, 10, "APPROVE_STANDARD", 0.035, "#2ECC71", "Approve with standard terms"),
        ("YELLOW", 3, 0, "MANUAL_REVIEW", 0.070, "#F39C12", "Requires credit analyst review"),
        ("RED", 4, None, "DECLINE", 0.150, "#E74C3C", "Decline or maximum collateral required"),
    ]
    for name, order, min_score, decision, pd, color, desc in tiers:
        ms = str(min_score) if min_score is not None else "NULL"
        conn.execute(sa_text(f"""
            INSERT INTO {SCHEMA}.scoring_tier_thresholds
                (version_id, tier_name, tier_order, min_score, decision, estimated_pd, color_hex, description)
            VALUES ('1.2.0', '{name}', {order}, {ms}, '{decision}', {pd}, '{color}', '{desc}')
        """))

    # ── Business Rules ──
    rules = [
        ("BR-01", "Minor applicant", "Applicant is under 18 years of age", "age", "<", "18"),
        ("BR-02", "Extreme over-financing", "LTV exceeds 120%", "ltv", ">", "120"),
        ("BR-03", "Negative DSCR", "Expenses exceed income", "dscr_value", "<", "0"),
        ("BR-04", "Multiple ZEK negatives", "3 or more negative ZEK entries", "zek_entry_count", ">=", "3"),
        ("BR-05", "Critical CRIF score", "CRIF score below 150", "crif_score", "<", "150"),
        ("BR-06", "No income data (B2C)", "No calculable income for individual applicant", "monthly_net_income", "<=", "0"),
        ("BR-07", "Watchlist dealer", "Dealer default rate exceeds 20%", "dealer_default_rate", ">", "0.20"),
        ("BR-08", "Excessive term", "Contract term exceeds 72 months", "term_months", ">", "72"),
    ]
    for code, name, desc, field, op_str, val in rules:
        conn.execute(sa_text(f"""
            INSERT INTO {SCHEMA}.business_rules
                (version_id, rule_code, rule_name, description, condition_field, condition_operator, condition_value, enabled, severity)
            VALUES ('1.2.0', '{code}', '{name}', '{desc}', '{field}', '{op_str}', '{val}', true, 'HARD')
        """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa_text(f"DELETE FROM {SCHEMA}.business_rules WHERE version_id = '1.2.0'"))
    conn.execute(sa_text(f"DELETE FROM {SCHEMA}.scoring_tier_thresholds WHERE version_id = '1.2.0'"))
    conn.execute(sa_text(f"DELETE FROM {SCHEMA}.scoring_factor_bins WHERE version_id = '1.2.0'"))
    conn.execute(sa_text(f"DELETE FROM {SCHEMA}.scoring_factor_config WHERE version_id = '1.2.0'"))
    conn.execute(sa_text(f"DELETE FROM {SCHEMA}.model_version WHERE version_id = '1.2.0'"))


from sqlalchemy import text as sa_text
