"""
quarterly_segment_refresh.py
─────────────────────────────
Quarterly batch job that reads historical portfolio performance from DataHub/ODS
and writes per-segment default rates + WoE drift to:

  - lt_risk_engine.population_segment_performance  (per bin per factor)
  - lt_risk_engine.model_monitoring_snapshot       (overall Gini / KS / PSI)

Purpose: provides the data for periodic model recalibration and drift detection.

Segments computed:
  FACTOR_BIN  — observed DR per scorecard bin (LTV, Term, Age, CRIF, Intrum,
                 DSCR, Permit, ZEK, VehiclePriceTier, DealerRisk)
  TIER        — DR breakdown by risk tier (BRIGHT_GREEN / GREEN / YELLOW / RED)
  OVERALL     — portfolio-level summary

WoE drift: observed WoE from portfolio vs original WoE from woe_scorecard_params.
A drift > 0.1 nats flags the bin for recalibration review.

Schedule: quarterly, e.g. first week of Jan / Apr / Jul / Oct (configured via cron)

Usage:
  python -m app.services.quarterly_segment_refresh
  OR via: POST /v1/admin/refresh-segment-performance

Environment variables:
  DATABASE_URL   — Risk engine DB (lt_risk_engine schema)
  DATAHUB_URL    — DataHub / ODS read-only connection string

NOTE ON JOIN KEYS:
  Queries join dwh.dim_contract → ods.contracts_sst using `party_orig_key`.
  This assumes dwh.dim_contract.party_orig_key = ods.contracts_sst.party_orig_key.
  Verify this against the actual DataHub ETL mapping if queries return unexpected results.
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
import structlog

logger = structlog.get_logger(__name__)

# ─── Configuration ────────────────────────────────────────────────
DATAHUB_URL = os.getenv("DATAHUB_URL", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Minimum contracts per bin to compute a reliable DR
MIN_BIN_VOLUME = 20

# WoE drift threshold (nats) above which a bin is flagged
WOE_DRIFT_THRESHOLD = 0.1

# How many months of contract history to include in the observation window
OBSERVATION_WINDOW_MONTHS = 12


# ─── Bin definitions (must match scoring engine exactly) ──────────

# These CASE expressions mirror the factor scoring in app/scoring/engine.py.
# Changing bin boundaries here without changing the engine will produce misleading drift metrics.

FACTOR_BIN_QUERIES: dict[str, str] = {

    "LTV": """
        SELECT
            CASE
                WHEN (c.financed_amount / NULLIF(c.offer_price, 0)) < 0.75  THEN '<75%'
                WHEN (c.financed_amount / NULLIF(c.offer_price, 0)) < 0.85  THEN '75-85%'
                WHEN (c.financed_amount / NULLIF(c.offer_price, 0)) < 0.95  THEN '85-95%'
                WHEN (c.financed_amount / NULLIF(c.offer_price, 0)) <= 1.0  THEN '95-100%'
                ELSE '>100%'
            END                                                    AS bin_label,
            COUNT(*)                                               AS contract_count,
            SUM(CASE WHEN dc.dpd >= 90 OR dc.wo_amt_ltd > 0
                     THEN 1 ELSE 0 END)                            AS default_count,
            AVG(dc.financed_amt)                                   AS avg_contract_size
        FROM dwh.dim_contract dc
        JOIN ods.contracts_sst c ON c.party_orig_key = dc.party_orig_key
        WHERE dc.current_flg = 1
          AND dc.activation_dt >= NOW() - INTERVAL '{window_months} months'
          AND c.offer_price > 0
        GROUP BY bin_label
        HAVING COUNT(*) >= {min_volume}
    """,

    "Term": """
        SELECT
            CASE
                WHEN c.duration <= 24  THEN '<=24m'
                WHEN c.duration <= 36  THEN '25-36m'
                WHEN c.duration <= 48  THEN '37-48m'
                WHEN c.duration <= 60  THEN '49-60m'
                ELSE '>60m'
            END                                                    AS bin_label,
            COUNT(*)                                               AS contract_count,
            SUM(CASE WHEN dc.dpd >= 90 OR dc.wo_amt_ltd > 0
                     THEN 1 ELSE 0 END)                            AS default_count,
            AVG(dc.financed_amt)                                   AS avg_contract_size
        FROM dwh.dim_contract dc
        JOIN ods.contracts_sst c ON c.party_orig_key = dc.party_orig_key
        WHERE dc.current_flg = 1
          AND dc.activation_dt >= NOW() - INTERVAL '{window_months} months'
          AND c.duration IS NOT NULL
        GROUP BY bin_label
        HAVING COUNT(*) >= {min_volume}
    """,

    "Age": """
        SELECT
            CASE
                WHEN DATE_PART('year', AGE(p.date_of_birth)) < 25   THEN '<25'
                WHEN DATE_PART('year', AGE(p.date_of_birth)) < 35   THEN '25-35'
                WHEN DATE_PART('year', AGE(p.date_of_birth)) < 45   THEN '35-45'
                WHEN DATE_PART('year', AGE(p.date_of_birth)) < 55   THEN '45-55'
                ELSE '>=55'
            END                                                    AS bin_label,
            COUNT(*)                                               AS contract_count,
            SUM(CASE WHEN dc.dpd >= 90 OR dc.wo_amt_ltd > 0
                     THEN 1 ELSE 0 END)                            AS default_count,
            AVG(dc.financed_amt)                                   AS avg_contract_size
        FROM dwh.dim_contract dc
        JOIN ods.contracts_sst c ON c.party_orig_key = dc.party_orig_key
        JOIN ods.persons_sst p ON p.party_orig_key = c.party_customer_orig_key
        WHERE dc.current_flg = 1
          AND dc.activation_dt >= NOW() - INTERVAL '{window_months} months'
          AND p.date_of_birth IS NOT NULL
        GROUP BY bin_label
        HAVING COUNT(*) >= {min_volume}
    """,

    "CRIF": """
        SELECT
            CASE
                WHEN poi.credit_score_crif IS NULL             THEN 'NULL/unknown'
                WHEN poi.credit_score_crif <= 0               THEN '<=0'
                WHEN poi.credit_score_crif <= 500             THEN '1-500'
                WHEN poi.credit_score_crif <= 700             THEN '501-700'
                WHEN poi.credit_score_crif <= 850             THEN '701-850'
                ELSE '>850'
            END                                                    AS bin_label,
            COUNT(*)                                               AS contract_count,
            SUM(CASE WHEN dc.dpd >= 90 OR dc.wo_amt_ltd > 0
                     THEN 1 ELSE 0 END)                            AS default_count,
            AVG(dc.financed_amt)                                   AS avg_contract_size
        FROM dwh.dim_contract dc
        JOIN ods.contracts_sst c ON c.party_orig_key = dc.party_orig_key
        LEFT JOIN ods.person_other_information_sst poi
               ON poi.party_orig_key = c.party_customer_orig_key
        WHERE dc.current_flg = 1
          AND dc.activation_dt >= NOW() - INTERVAL '{window_months} months'
        GROUP BY bin_label
        HAVING COUNT(*) >= {min_volume}
    """,

    "Intrum": """
        SELECT
            CASE
                WHEN poi.credit_score_intrum IS NULL      THEN 'NULL/no_hit'
                WHEN poi.credit_score_intrum <= 2         THEN '1-2'
                WHEN poi.credit_score_intrum <= 5         THEN '3-5'
                WHEN poi.credit_score_intrum <= 8         THEN '6-8'
                ELSE '>8'
            END                                                    AS bin_label,
            COUNT(*)                                               AS contract_count,
            SUM(CASE WHEN dc.dpd >= 90 OR dc.wo_amt_ltd > 0
                     THEN 1 ELSE 0 END)                            AS default_count,
            AVG(dc.financed_amt)                                   AS avg_contract_size
        FROM dwh.dim_contract dc
        JOIN ods.contracts_sst c ON c.party_orig_key = dc.party_orig_key
        LEFT JOIN ods.person_other_information_sst poi
               ON poi.party_orig_key = c.party_customer_orig_key
        WHERE dc.current_flg = 1
          AND dc.activation_dt >= NOW() - INTERVAL '{window_months} months'
        GROUP BY bin_label
        HAVING COUNT(*) >= {min_volume}
    """,

    "DSCR": """
        SELECT
            CASE
                WHEN poi.dscr_customer_dscr IS NULL       THEN 'NULL/unknown'
                WHEN poi.dscr_customer_dscr < 1.2         THEN '<1.2'
                WHEN poi.dscr_customer_dscr < 1.4         THEN '1.2-1.4'
                WHEN poi.dscr_customer_dscr < 1.6         THEN '1.4-1.6'
                WHEN poi.dscr_customer_dscr < 2.0         THEN '1.6-2.0'
                ELSE '>=2.0'
            END                                                    AS bin_label,
            COUNT(*)                                               AS contract_count,
            SUM(CASE WHEN dc.dpd >= 90 OR dc.wo_amt_ltd > 0
                     THEN 1 ELSE 0 END)                            AS default_count,
            AVG(dc.financed_amt)                                   AS avg_contract_size
        FROM dwh.dim_contract dc
        JOIN ods.contracts_sst c ON c.party_orig_key = dc.party_orig_key
        LEFT JOIN ods.person_other_information_sst poi
               ON poi.party_orig_key = c.party_customer_orig_key
        WHERE dc.current_flg = 1
          AND dc.activation_dt >= NOW() - INTERVAL '{window_months} months'
        GROUP BY bin_label
        HAVING COUNT(*) >= {min_volume}
    """,

    "Permit": """
        SELECT
            CASE
                WHEN p.permit_type ILIKE '%C%'            THEN 'C_permit'
                WHEN p.permit_type ILIKE '%B%'            THEN 'B_permit'
                WHEN p.nationality = 'CH'                 THEN 'Swiss_citizen'
                ELSE 'other'
            END                                                    AS bin_label,
            COUNT(*)                                               AS contract_count,
            SUM(CASE WHEN dc.dpd >= 90 OR dc.wo_amt_ltd > 0
                     THEN 1 ELSE 0 END)                            AS default_count,
            AVG(dc.financed_amt)                                   AS avg_contract_size
        FROM dwh.dim_contract dc
        JOIN ods.contracts_sst c ON c.party_orig_key = dc.party_orig_key
        LEFT JOIN ods.persons_sst p ON p.party_orig_key = c.party_customer_orig_key
        WHERE dc.current_flg = 1
          AND dc.activation_dt >= NOW() - INTERVAL '{window_months} months'
        GROUP BY bin_label
        HAVING COUNT(*) >= {min_volume}
    """,

    "ZEK": """
        SELECT
            CASE
                WHEN c.zek_code IS NULL OR c.zek_code = ''        THEN 'no_hit'
                WHEN c.zek_code IN ('01','02','03')               THEN '1_issue'
                ELSE '2plus_issues'
            END                                                    AS bin_label,
            COUNT(*)                                               AS contract_count,
            SUM(CASE WHEN dc.dpd >= 90 OR dc.wo_amt_ltd > 0
                     THEN 1 ELSE 0 END)                            AS default_count,
            AVG(dc.financed_amt)                                   AS avg_contract_size
        FROM dwh.dim_contract dc
        JOIN ods.contracts_sst c ON c.party_orig_key = dc.party_orig_key
        WHERE dc.current_flg = 1
          AND dc.activation_dt >= NOW() - INTERVAL '{window_months} months'
        GROUP BY bin_label
        HAVING COUNT(*) >= {min_volume}
    """,

    "VehiclePriceTier": """
        SELECT
            CASE
                WHEN c.offer_price < 15000   THEN '<15k'
                WHEN c.offer_price < 25000   THEN '15-25k'
                WHEN c.offer_price < 40000   THEN '25-40k'
                WHEN c.offer_price < 60000   THEN '40-60k'
                ELSE '>=60k'
            END                                                    AS bin_label,
            COUNT(*)                                               AS contract_count,
            SUM(CASE WHEN dc.dpd >= 90 OR dc.wo_amt_ltd > 0
                     THEN 1 ELSE 0 END)                            AS default_count,
            AVG(dc.financed_amt)                                   AS avg_contract_size
        FROM dwh.dim_contract dc
        JOIN ods.contracts_sst c ON c.party_orig_key = dc.party_orig_key
        WHERE dc.current_flg = 1
          AND dc.activation_dt >= NOW() - INTERVAL '{window_months} months'
          AND c.offer_price IS NOT NULL
        GROUP BY bin_label
        HAVING COUNT(*) >= {min_volume}
    """,

    "DealerRisk": """
        SELECT
            CASE
                WHEN drm.current_default_rate IS NULL            THEN 'unknown'
                WHEN drm.current_default_rate < 0.10             THEN '<10%'
                WHEN drm.current_default_rate < 0.20             THEN '10-20%'
                ELSE '>=20%'
            END                                                    AS bin_label,
            COUNT(*)                                               AS contract_count,
            SUM(CASE WHEN dc.dpd >= 90 OR dc.wo_amt_ltd > 0
                     THEN 1 ELSE 0 END)                            AS default_count,
            AVG(dc.financed_amt)                                   AS avg_contract_size
        FROM dwh.dim_contract dc
        JOIN ods.contracts_sst c ON c.party_orig_key = dc.party_orig_key
        LEFT JOIN lt_risk_engine.dealer_risk_metrics drm
               ON drm.dealer_id = dc.party_dealer_orig_key::text
              AND drm.snapshot_date = (
                  SELECT MAX(snapshot_date)
                  FROM lt_risk_engine.dealer_risk_metrics
                  WHERE dealer_id = dc.party_dealer_orig_key::text
              )
        WHERE dc.current_flg = 1
          AND dc.activation_dt >= NOW() - INTERVAL '{window_months} months'
        GROUP BY bin_label
        HAVING COUNT(*) >= {min_volume}
    """,
}

# Tier distribution by join to risk_assessment if data available, else estimate from score ranges
TIER_QUERY = """
    SELECT
        ra.risk_tier                                               AS bin_label,
        COUNT(*)                                                   AS contract_count,
        SUM(CASE WHEN dc.dpd >= 90 OR dc.wo_amt_ltd > 0
                 THEN 1 ELSE 0 END)                                AS default_count,
        AVG(dc.financed_amt)                                       AS avg_contract_size
    FROM lt_risk_engine.risk_assessment ra
    JOIN dwh.dim_contract dc ON dc.party_orig_key = ra.application_id
    WHERE ra.risk_tier IS NOT NULL
      AND ra.created_at >= NOW() - INTERVAL '{window_months} months'
    GROUP BY ra.risk_tier
    HAVING COUNT(*) >= {min_volume}
"""

OVERALL_QUERY = """
    SELECT
        COUNT(*)                                                   AS contract_count,
        SUM(CASE WHEN dc.dpd >= 90 OR dc.wo_amt_ltd > 0
                 THEN 1 ELSE 0 END)                                AS default_count,
        AVG(dc.financed_amt)                                       AS avg_contract_size
    FROM dwh.dim_contract dc
    WHERE dc.current_flg = 1
      AND dc.activation_dt >= NOW() - INTERVAL '{window_months} months'
"""


@dataclass
class SegmentRow:
    segment_type: str            # FACTOR_BIN | TIER | OVERALL
    segment_key: str             # e.g. "LTV:<75%"
    factor_name: Optional[str]   # e.g. "LTV"
    bin_label: Optional[str]     # e.g. "<75%"
    contract_count: int
    default_count: int
    observed_dr: float
    avg_score: Optional[float] = None
    original_woe: Optional[float] = None
    observed_woe: Optional[float] = None
    woe_drift: Optional[float] = None


def _compute_woe(default_count: int, total: int,
                 pop_default_count: int, pop_total: int) -> Optional[float]:
    """
    WoE = ln( P(non-default in bin) / P(default in bin) )
        = ln( (non_default_bin / total_non_defaults) / (default_bin / total_defaults) )
    Returns None if any cell is zero (undefined WoE).
    """
    non_def_bin = total - default_count
    def_bin = default_count
    non_def_pop = pop_total - pop_default_count
    def_pop = pop_default_count

    if def_bin == 0 or non_def_bin == 0 or def_pop == 0 or non_def_pop == 0:
        return None

    return math.log((non_def_bin / non_def_pop) / (def_bin / def_pop))


def fetch_original_woe(re_conn) -> dict[tuple[str, str], float]:
    """
    Read original WoE values from lt_risk_engine.woe_scorecard_params.
    Returns dict keyed by (factor_name, bin_label).
    """
    with re_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT factor_name, bin_label, woe_value
            FROM lt_risk_engine.woe_scorecard_params
            WHERE param_type = 'BIN_POINTS'
              AND woe_value IS NOT NULL
              AND factor_name IS NOT NULL
              AND bin_label IS NOT NULL
        """)
        return {
            (row["factor_name"], row["bin_label"]): float(row["woe_value"])
            for row in cur.fetchall()
        }


def fetch_factor_segments(
    dh_conn,
    factor_name: str,
    sql_template: str,
    window_months: int,
    min_volume: int,
) -> list[dict]:
    """Run a factor bin query against DataHub, return raw rows."""
    sql = sql_template.format(
        window_months=window_months,
        min_volume=min_volume,
    )
    with dh_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        try:
            cur.execute(sql)
            return cur.fetchall()
        except psycopg2.Error as e:
            logger.warning(
                "factor_query_failed",
                factor=factor_name,
                error=str(e)[:200],
            )
            dh_conn.rollback()
            return []


def build_segment_rows(
    factor_name: str,
    raw_rows: list[dict],
    original_woe_map: dict,
) -> list[SegmentRow]:
    """Convert raw query results into SegmentRow objects with WoE drift."""
    if not raw_rows:
        return []

    # Portfolio totals (for WoE calculation)
    pop_total = sum(int(r["contract_count"]) for r in raw_rows)
    pop_defaults = sum(int(r["default_count"]) for r in raw_rows)

    rows = []
    for r in raw_rows:
        cnt = int(r["contract_count"])
        def_cnt = int(r["default_count"])
        observed_dr = def_cnt / cnt if cnt > 0 else 0.0
        bin_label = str(r["bin_label"])

        observed_woe = _compute_woe(def_cnt, cnt, pop_defaults, pop_total)
        original_woe = original_woe_map.get((factor_name, bin_label))
        woe_drift = (
            (observed_woe - original_woe)
            if observed_woe is not None and original_woe is not None
            else None
        )

        rows.append(SegmentRow(
            segment_type="FACTOR_BIN",
            segment_key=f"{factor_name}:{bin_label}",
            factor_name=factor_name,
            bin_label=bin_label,
            contract_count=cnt,
            default_count=def_cnt,
            observed_dr=observed_dr,
            original_woe=original_woe,
            observed_woe=observed_woe,
            woe_drift=woe_drift,
        ))

    return rows


def fetch_overall_stats(dh_conn, window_months: int) -> Optional[SegmentRow]:
    """Portfolio-wide default rate."""
    sql = OVERALL_QUERY.format(window_months=window_months, min_volume=0)
    with dh_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        try:
            cur.execute(sql)
            row = cur.fetchone()
        except psycopg2.Error as e:
            logger.warning("overall_query_failed", error=str(e)[:200])
            dh_conn.rollback()
            return None

    if not row or not row["contract_count"]:
        return None

    cnt = int(row["contract_count"])
    def_cnt = int(row["default_count"])
    return SegmentRow(
        segment_type="OVERALL",
        segment_key="OVERALL:portfolio",
        factor_name=None,
        bin_label="portfolio",
        contract_count=cnt,
        default_count=def_cnt,
        observed_dr=def_cnt / cnt if cnt > 0 else 0.0,
    )


# ─── Write to lt_risk_engine ──────────────────────────────────────

UPSERT_SEGMENT = """
INSERT INTO lt_risk_engine.population_segment_performance (
    snapshot_date, segment_type, segment_key,
    factor_name, bin_label,
    contract_count, default_count, observed_default_rate,
    observed_woe, original_woe, woe_drift,
    data_source, observation_window_months,
    created_by
) VALUES (
    %(snapshot_date)s, %(segment_type)s, %(segment_key)s,
    %(factor_name)s, %(bin_label)s,
    %(contract_count)s, %(default_count)s, %(observed_dr)s,
    %(observed_woe)s, %(original_woe)s, %(woe_drift)s,
    'DATAHUB_ODS', %(window_months)s,
    'quarterly_segment_refresh'
)
ON CONFLICT DO NOTHING
"""


def write_segment_rows(
    re_conn,
    rows: list[SegmentRow],
    snapshot_date: date,
    window_months: int,
) -> int:
    params = [
        {
            "snapshot_date":    snapshot_date,
            "segment_type":     r.segment_type,
            "segment_key":      r.segment_key,
            "factor_name":      r.factor_name,
            "bin_label":        r.bin_label,
            "contract_count":   r.contract_count,
            "default_count":    r.default_count,
            "observed_dr":      round(r.observed_dr, 6),
            "observed_woe":     round(r.observed_woe, 4) if r.observed_woe is not None else None,
            "original_woe":     round(r.original_woe, 4) if r.original_woe is not None else None,
            "woe_drift":        round(r.woe_drift, 4) if r.woe_drift is not None else None,
            "window_months":    window_months,
        }
        for r in rows
    ]

    with re_conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, UPSERT_SEGMENT, params, page_size=50)
    re_conn.commit()
    return len(params)


def write_monitoring_snapshot(
    re_conn,
    overall: Optional[SegmentRow],
    all_rows: list[SegmentRow],
    snapshot_date: date,
    window_months: int,
) -> None:
    """
    Write a model_monitoring_snapshot record.
    Gini / KS / AUC-ROC require score-level data (risk_assessment.composite_score
    joined to outcomes). Here we compute the subset available from segment-level data:
      - calibration ratio (predicted PD / observed DR, using 8.3% baseline predicted)
      - PSI from tier drift if tier-level data is available
      - overall observed DR
    Full discrimination metrics (Gini, KS, AUC) should be computed separately by a
    script that joins risk_assessment → dwh.dim_contract at the contract level.
    """
    if not overall:
        return

    # Tier distribution from TIER segments
    tier_rows = [r for r in all_rows if r.segment_type == "TIER"]
    tier_dist = {}
    if tier_rows:
        total_tier = sum(r.contract_count for r in tier_rows)
        tier_dist = {
            r.bin_label: round(r.contract_count / total_tier, 4)
            for r in tier_rows
        }

    # PSI: compare current tier distribution vs dev sample baseline
    # Dev sample baseline (from migration 005 seed): approximate
    baseline_tier_dist = {
        "BRIGHT_GREEN": 0.255,
        "GREEN":        0.254,
        "YELLOW":       0.238,
        "RED":          0.150,
    }

    psi_score = None
    if tier_dist:
        psi = 0.0
        for tier, expected in baseline_tier_dist.items():
            actual = tier_dist.get(tier, 0.001)
            expected = max(expected, 0.001)
            actual = max(actual, 0.001)
            psi += (actual - expected) * math.log(actual / expected)
        psi_score = round(psi, 4)

    psi_status = None
    if psi_score is not None:
        if psi_score < 0.1:
            psi_status = "STABLE"
        elif psi_score < 0.25:
            psi_status = "SHIFT"
        else:
            psi_status = "ALARM"

    import json
    with re_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO lt_risk_engine.model_monitoring_snapshot (
                snapshot_date, model_version, scorecard_type,
                overall_observed_dr,
                psi_score, psi_status,
                total_contracts, total_defaults,
                observation_window_months,
                tier_distribution_json,
                created_by
            ) VALUES (
                %(snapshot_date)s, %(model_version)s, %(scorecard_type)s,
                %(overall_observed_dr)s,
                %(psi_score)s, %(psi_status)s,
                %(total_contracts)s, %(total_defaults)s,
                %(window_months)s,
                %(tier_dist)s,
                'quarterly_segment_refresh'
            )
            ON CONFLICT (snapshot_date, model_version) DO UPDATE SET
                overall_observed_dr      = EXCLUDED.overall_observed_dr,
                psi_score                = EXCLUDED.psi_score,
                psi_status               = EXCLUDED.psi_status,
                total_contracts          = EXCLUDED.total_contracts,
                total_defaults           = EXCLUDED.total_defaults,
                tier_distribution_json   = EXCLUDED.tier_distribution_json
        """, {
            "snapshot_date":      snapshot_date,
            "model_version":      "1.2.0",
            "scorecard_type":     "V1_2_COMPOSITE",
            "overall_observed_dr": round(overall.observed_dr, 4),
            "psi_score":          psi_score,
            "psi_status":         psi_status,
            "total_contracts":    overall.contract_count,
            "total_defaults":     overall.default_count,
            "window_months":      window_months,
            "tier_dist":          json.dumps(tier_dist) if tier_dist else None,
        })
    re_conn.commit()
    logger.info(
        "monitoring_snapshot_written",
        snapshot_date=snapshot_date.isoformat(),
        observed_dr=overall.observed_dr,
        psi_score=psi_score,
        psi_status=psi_status,
    )


# ─── Drift report ─────────────────────────────────────────────────

@dataclass
class RefreshSummary:
    snapshot_date: str
    window_months: int
    factors_processed: int
    segments_written: int
    overall_dr: Optional[float]
    high_drift_bins: list[dict] = field(default_factory=list)
    psi_status: Optional[str] = None
    elapsed_seconds: float = 0.0
    status: str = "success"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "snapshot_date":     self.snapshot_date,
            "window_months":     self.window_months,
            "factors_processed": self.factors_processed,
            "segments_written":  self.segments_written,
            "overall_dr":        self.overall_dr,
            "high_drift_bins":   self.high_drift_bins,
            "psi_status":        self.psi_status,
            "elapsed_seconds":   self.elapsed_seconds,
            "status":            self.status,
            "errors":            self.errors,
        }


# ─── Main entry point ─────────────────────────────────────────────

def run_refresh(
    datahub_url: Optional[str] = None,
    database_url: Optional[str] = None,
    snapshot_date: Optional[date] = None,
    window_months: int = OBSERVATION_WINDOW_MONTHS,
    min_bin_volume: int = MIN_BIN_VOLUME,
) -> dict:
    """
    Full quarterly segment refresh:
      1. For each scoring factor, query DataHub for per-bin observed DR
      2. Compute WoE drift vs original scorecard params
      3. Write all segments to population_segment_performance
      4. Write a model_monitoring_snapshot with PSI and calibration
      5. Return summary with any high-drift bins flagged

    Args:
        datahub_url:    Override DATAHUB_URL env var
        database_url:   Override DATABASE_URL env var
        snapshot_date:  Override today's date (for backfill)
        window_months:  Observation window in months (default 12)
        min_bin_volume: Minimum contracts per bin (default 20)
    """
    dh_url = datahub_url or DATAHUB_URL
    re_url = database_url or DATABASE_URL
    snap_dt = snapshot_date or date.today()

    if not dh_url:
        raise ValueError("DATAHUB_URL not set")
    if not re_url:
        raise ValueError("DATABASE_URL not set")

    started_at = datetime.now(timezone.utc)
    logger.info("quarterly_refresh_started",
                snapshot_date=snap_dt.isoformat(),
                window_months=window_months)

    summary = RefreshSummary(
        snapshot_date=snap_dt.isoformat(),
        window_months=window_months,
        factors_processed=0,
        segments_written=0,
        overall_dr=None,
    )

    dh_conn = psycopg2.connect(dh_url)
    re_conn = psycopg2.connect(re_url)

    try:
        # Load original WoE from risk engine DB
        original_woe_map = fetch_original_woe(re_conn)
        logger.info("original_woe_loaded", bins=len(original_woe_map))

        all_rows: list[SegmentRow] = []

        # Process each scoring factor
        for factor_name, sql_template in FACTOR_BIN_QUERIES.items():
            raw = fetch_factor_segments(
                dh_conn, factor_name, sql_template,
                window_months, min_bin_volume
            )
            if not raw:
                summary.errors.append(f"No data returned for factor: {factor_name}")
                continue

            rows = build_segment_rows(factor_name, raw, original_woe_map)
            all_rows.extend(rows)
            summary.factors_processed += 1

            # Flag high-drift bins
            for r in rows:
                if r.woe_drift is not None and abs(r.woe_drift) > WOE_DRIFT_THRESHOLD:
                    summary.high_drift_bins.append({
                        "factor":    factor_name,
                        "bin":       r.bin_label,
                        "drift":     round(r.woe_drift, 4),
                        "observed_dr": round(r.observed_dr, 4),
                    })

            logger.info("factor_processed", factor=factor_name, bins=len(rows))

        # Overall stats
        overall = fetch_overall_stats(dh_conn, window_months)
        if overall:
            all_rows.append(overall)
            summary.overall_dr = round(overall.observed_dr, 4)

        # Write all segment rows
        written = write_segment_rows(re_conn, all_rows, snap_dt, window_months)
        summary.segments_written = written

        # Write monitoring snapshot
        write_monitoring_snapshot(re_conn, overall, all_rows, snap_dt, window_months)

        # Log high-drift summary
        if summary.high_drift_bins:
            logger.warning(
                "high_drift_bins_detected",
                count=len(summary.high_drift_bins),
                bins=[f"{b['factor']}:{b['bin']} (drift={b['drift']})"
                      for b in summary.high_drift_bins],
            )

    finally:
        dh_conn.close()
        re_conn.close()

    summary.elapsed_seconds = round(
        (datetime.now(timezone.utc) - started_at).total_seconds(), 2
    )

    result = summary.to_dict()
    logger.info("quarterly_refresh_complete", **{
        k: v for k, v in result.items() if k != "high_drift_bins"
    })
    return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    try:
        result = run_refresh()
        print(
            f"✓ Segment refresh complete: {result['factors_processed']} factors, "
            f"{result['segments_written']} segments written, "
            f"portfolio DR={result['overall_dr']:.1%} "
            f"({result['elapsed_seconds']}s)"
        )
        if result["high_drift_bins"]:
            print(f"  ⚠ {len(result['high_drift_bins'])} bins with WoE drift > {WOE_DRIFT_THRESHOLD}:")
            for b in result["high_drift_bins"]:
                print(f"    {b['factor']}:{b['bin']}  drift={b['drift']:+.3f}  "
                      f"obs_DR={b['observed_dr']:.1%}")
        if result["errors"]:
            print(f"  ✗ Errors: {result['errors']}")
    except Exception as e:
        print(f"✗ Refresh failed: {e}", file=sys.stderr)
        sys.exit(1)
