"""
005 — Seed WoE scorecard parameters from the original logistic regression model

Populates woe_scorecard_params with the intercept, coefficients, WoE values,
and point allocations from the B2C Credit Scoring Model v1.2 development sample.

Development sample: 2,461 B2C contracts from the LeaseTeq portfolio
Validated on: 3,930 full portfolio (backtest Feb 2026)

The INTERCEPT (+389) represents the base score for the population.
It is the scaled log-odds of the population average default rate.
Each bin's points are derived from: coefficient × WoE × scaling_factor + offset.

Revision ID: 005
Create Date: 2026-02-26
"""
from alembic import op
from sqlalchemy import text as sa_text

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

SCHEMA = "lt_risk_engine"


def upgrade() -> None:
    conn = op.get_bind()

    # ── INTERCEPT: base score added to every contract ──
    conn.execute(sa_text(f"""
        INSERT INTO {SCHEMA}.woe_scorecard_params
            (version_id, param_type, factor_name, bin_label, coefficient, woe_value, points,
             bin_default_rate, bin_count, bin_default_count)
        VALUES ('1.2.0', 'INTERCEPT', NULL, NULL, NULL, NULL, 389,
                NULL, 2461, NULL)
    """))

    # ── COEFFICIENTS per factor ──
    coefficients = [
        ("LTV",    -0.8280),
        ("Term",   -0.8084),
        ("Age",    -0.7428),
        ("Intrum", -0.6098),
        ("Permit", -0.5391),
        ("DSCR",   -0.3589),
    ]
    for factor, coeff in coefficients:
        conn.execute(sa_text(f"""
            INSERT INTO {SCHEMA}.woe_scorecard_params
                (version_id, param_type, factor_name, bin_label, coefficient, woe_value, points)
            VALUES ('1.2.0', 'COEFFICIENT', '{factor}', NULL, {coeff}, NULL, 0)
        """))

    # ── BIN-LEVEL POINTS with WoE, default rate, and sample counts ──
    # Format: (factor, bin_label, woe, default_rate, count, points)
    bin_data = [
        # LTV — coefficient: -0.8280
        ("LTV", "<75%",   -0.56, 0.02, 680, 36),
        ("LTV", "75-85%", -0.23, 0.04, 892, 15),
        ("LTV", "85-95%", -0.11, 0.06, 567, 7),
        ("LTV", ">95%",    0.28, 0.11, 322, -18),

        # Term — coefficient: -0.8084
        ("Term", "≤36m",   -0.34, 0.03, 445, 22),
        ("Term", "37-48m", -0.39, 0.02, 1120, 25),
        ("Term", ">48m",    0.11, 0.08, 896, -7),

        # Age — coefficient: -0.7428
        ("Age", "18-25", 0.27, 0.11, 198, -16),
        ("Age", "26-35", -0.10, 0.04, 623, 6),
        ("Age", "36-45", 0.05, 0.06, 789, -3),
        ("Age", "46-55", -0.48, 0.02, 534, 28),
        ("Age", "56+",   0.14, 0.07, 317, -8),

        # Intrum — coefficient: -0.6098
        ("Intrum", "0",    0.15, 0.08, 412, -7),
        ("Intrum", "1",   -0.02, 0.05, 356, 1),
        ("Intrum", "1-3",  0.06, 0.07, 289, -3),
        ("Intrum", ">3",  -0.17, 0.03, 1404, 8),

        # Permit — coefficient: -0.5391
        ("Permit", "B2B",       0.14, 0.08, 234, -6),
        ("Permit", "B_permit",  0.12, 0.07, 189, -5),
        ("Permit", "C_permit", -0.14, 0.03, 1567, 6),
        ("Permit", "Other_B2C",-0.16, 0.03, 471, 7),

        # DSCR — coefficient: -0.3589
        ("DSCR", "0-3",  0.04, 0.06, 345, -1),
        ("DSCR", "3-7",  0.00, 0.05, 890, 0),
        ("DSCR", "7-15", 0.10, 0.07, 412, -3),
        ("DSCR", "<0",   0.21, 0.12, 89, -6),
        ("DSCR", ">15", -0.32, 0.02, 725, 9),
    ]

    for factor, bin_label, woe, dr, count, points in bin_data:
        default_count = int(round(dr * count))
        conn.execute(sa_text(f"""
            INSERT INTO {SCHEMA}.woe_scorecard_params
                (version_id, param_type, factor_name, bin_label, coefficient,
                 woe_value, points, bin_default_rate, bin_count, bin_default_count)
            VALUES ('1.2.0', 'BIN_POINTS', '{factor}', '{bin_label}',
                    (SELECT coefficient FROM {SCHEMA}.woe_scorecard_params
                     WHERE version_id = '1.2.0' AND param_type = 'COEFFICIENT' AND factor_name = '{factor}'),
                    {woe}, {points}, {dr}, {count}, {default_count})
        """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa_text(f"DELETE FROM {SCHEMA}.woe_scorecard_params WHERE version_id = '1.2.0'"))
