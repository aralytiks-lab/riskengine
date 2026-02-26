"""
dealer_metrics_refresh.py
─────────────────────────
Nightly batch job that reads dealer default rates from the DataHub
(dwh.dim_contract) and writes results to lt_risk_engine.dealer_risk_metrics.

This is the mechanism by which historical portfolio data enters the scoring path:
  DataHub (dwh.dim_contract) → dealer_risk_metrics → Flowable reads it → passes in POST payload → Risk Engine scores.

Schedule: 02:00 UTC nightly (configured via cron / Kubernetes CronJob)

Usage:
  python -m app.services.dealer_metrics_refresh
  OR via the admin endpoint: POST /v1/admin/refresh-dealer-metrics

Environment variables required:
  DATABASE_URL  - Risk engine DB (lt_risk_engine schema)
  DATAHUB_URL   - DataHub/DWH read-only connection string

"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras
import structlog

logger = structlog.get_logger(__name__)

# ─── Configuration ────────────────────────────────────────────────
DATAHUB_URL = os.getenv("DATAHUB_URL", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Minimum number of contracts a dealer must have to be included
# Below this threshold the default rate is unreliable (small sample noise)
MIN_CONTRACT_VOLUME = 5

# Default rate above which the dealer is flagged for the watchlist
# → triggers BR-07 override in scoring engine
WATCHLIST_THRESHOLD = 0.20

# Volume tiers (total originated contracts)
VOLUME_TIERS = [
    (200, "PLATINUM"),
    (50,  "GOLD"),
    (20,  "SILVER"),
    (0,   "BRONZE"),
]


@dataclass
class DealerStats:
    dealer_id: str
    dealer_name: Optional[str]
    active_contracts: int
    total_originated: int
    default_count: int
    current_default_rate: float
    avg_contract_size: float
    first_contract_date: Optional[date]

    @property
    def active_months(self) -> int:
        if not self.first_contract_date:
            return 0
        delta = date.today() - self.first_contract_date
        return int(delta.days / 30.44)

    @property
    def volume_tier(self) -> str:
        for threshold, tier in VOLUME_TIERS:
            if self.total_originated >= threshold:
                return tier
        return "BRONZE"

    @property
    def is_watchlist(self) -> bool:
        return self.current_default_rate > WATCHLIST_THRESHOLD


# ─── DataHub query ────────────────────────────────────────────────

DATAHUB_QUERY = """
SELECT
    dc.party_dealer_orig_key::text                      AS dealer_id,
    NULL                                                AS dealer_name,
    COUNT(*) FILTER (WHERE dc.close_dt IS NULL)         AS active_contracts,
    COUNT(*)                                            AS total_originated,
    COUNT(*) FILTER (
        WHERE dc.dpd >= 90 OR dc.wo_amt_ltd > 0
    )                                                   AS default_count,
    ROUND(
        COUNT(*) FILTER (WHERE dc.dpd >= 90 OR dc.wo_amt_ltd > 0)::numeric
        / NULLIF(COUNT(*), 0),
        4
    )                                                   AS current_default_rate,
    ROUND(AVG(dc.financed_amt), 2)                      AS avg_contract_size,
    MIN(dc.activation_dt)                               AS first_contract_date
FROM dwh.dim_contract dc
WHERE dc.current_flg = 1
  AND dc.party_dealer_orig_key IS NOT NULL
GROUP BY dc.party_dealer_orig_key
HAVING COUNT(*) >= %(min_volume)s
ORDER BY total_originated DESC;
"""


def fetch_dealer_stats(datahub_url: str) -> list[DealerStats]:
    """
    Pull dealer default rates from the DataHub.
    Uses a read-only connection — never writes to DWH.
    """
    conn = psycopg2.connect(datahub_url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(DATAHUB_QUERY, {"min_volume": MIN_CONTRACT_VOLUME})
            rows = cur.fetchall()
    finally:
        conn.close()

    stats = []
    for row in rows:
        stats.append(DealerStats(
            dealer_id=str(row["dealer_id"]),
            dealer_name=row.get("dealer_name"),
            active_contracts=int(row["active_contracts"] or 0),
            total_originated=int(row["total_originated"] or 0),
            default_count=int(row["default_count"] or 0),
            current_default_rate=float(row["current_default_rate"] or 0),
            avg_contract_size=float(row["avg_contract_size"] or 0),
            first_contract_date=row.get("first_contract_date"),
        ))

    logger.info("datahub_query_complete", dealer_count=len(stats))
    return stats


# ─── Previous snapshot read ───────────────────────────────────────

def fetch_previous_rates(re_conn) -> dict[str, float]:
    """
    Read the most recent default rate for each dealer from the risk engine DB.
    Used to compute trend (IMPROVING / STABLE / WORSENING).
    """
    with re_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT DISTINCT ON (dealer_id)
                dealer_id,
                current_default_rate
            FROM lt_risk_engine.dealer_risk_metrics
            ORDER BY dealer_id, snapshot_date DESC
        """)
        return {row["dealer_id"]: float(row["current_default_rate"]) for row in cur.fetchall()}


def compute_trend(current: float, previous: Optional[float]) -> str:
    if previous is None:
        return "NEW"
    delta = current - previous
    if delta < -0.02:   # improved by more than 2pp
        return "IMPROVING"
    if delta > 0.02:    # worsened by more than 2pp
        return "WORSENING"
    return "STABLE"


# ─── Write to lt_risk_engine ──────────────────────────────────────

UPSERT_QUERY = """
INSERT INTO lt_risk_engine.dealer_risk_metrics (
    dealer_id, dealer_name, snapshot_date,
    active_contracts, total_originated,
    default_count, current_default_rate,
    previous_default_rate, default_rate_trend,
    active_months, volume_tier, avg_contract_size,
    is_watchlist, watchlist_reason,
    data_source, created_at
) VALUES (
    %(dealer_id)s, %(dealer_name)s, %(snapshot_date)s,
    %(active_contracts)s, %(total_originated)s,
    %(default_count)s, %(current_default_rate)s,
    %(previous_default_rate)s, %(default_rate_trend)s,
    %(active_months)s, %(volume_tier)s, %(avg_contract_size)s,
    %(is_watchlist)s, %(watchlist_reason)s,
    'DATAHUB', NOW()
)
ON CONFLICT (dealer_id, snapshot_date)
DO UPDATE SET
    active_contracts     = EXCLUDED.active_contracts,
    total_originated     = EXCLUDED.total_originated,
    default_count        = EXCLUDED.default_count,
    current_default_rate = EXCLUDED.current_default_rate,
    default_rate_trend   = EXCLUDED.default_rate_trend,
    is_watchlist         = EXCLUDED.is_watchlist,
    watchlist_reason     = EXCLUDED.watchlist_reason,
    volume_tier          = EXCLUDED.volume_tier;
"""


def write_dealer_metrics(
    re_conn,
    stats: list[DealerStats],
    previous_rates: dict[str, float],
    snapshot_date: date,
) -> int:
    """
    Write all dealer stats to lt_risk_engine.dealer_risk_metrics.
    Returns the number of rows written.
    """
    rows = []
    watchlist_count = 0
    for s in stats:
        prev = previous_rates.get(s.dealer_id)
        trend = compute_trend(s.current_default_rate, prev)
        is_watchlist = s.is_watchlist
        if is_watchlist:
            watchlist_count += 1

        rows.append({
            "dealer_id":            s.dealer_id,
            "dealer_name":          s.dealer_name,
            "snapshot_date":        snapshot_date,
            "active_contracts":     s.active_contracts,
            "total_originated":     s.total_originated,
            "default_count":        s.default_count,
            "current_default_rate": s.current_default_rate,
            "previous_default_rate": prev,
            "default_rate_trend":   trend,
            "active_months":        s.active_months,
            "volume_tier":          s.volume_tier,
            "avg_contract_size":    s.avg_contract_size,
            "is_watchlist":         is_watchlist,
            "watchlist_reason":     (
                f"Default rate {s.current_default_rate:.1%} exceeds {WATCHLIST_THRESHOLD:.0%} threshold"
                if is_watchlist else None
            ),
        })

    with re_conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, UPSERT_QUERY, rows, page_size=50)
    re_conn.commit()

    logger.info(
        "dealer_metrics_written",
        rows=len(rows),
        watchlist=watchlist_count,
        snapshot_date=snapshot_date.isoformat(),
    )
    return len(rows)


# ─── Main entry point ─────────────────────────────────────────────

def run_refresh(
    datahub_url: Optional[str] = None,
    database_url: Optional[str] = None,
    snapshot_date: Optional[date] = None,
) -> dict:
    """
    Full refresh cycle:
      1. Fetch dealer stats from DataHub
      2. Read previous rates from risk engine DB
      3. Write updated metrics
      4. Return summary

    Args:
        datahub_url:   Override DATAHUB_URL env var (for testing)
        database_url:  Override DATABASE_URL env var (for testing)
        snapshot_date: Override today's date (for backfill)
    """
    dh_url = datahub_url or DATAHUB_URL
    re_url = database_url or DATABASE_URL
    snap_dt = snapshot_date or date.today()

    if not dh_url:
        raise ValueError("DATAHUB_URL not set — cannot connect to DataHub")
    if not re_url:
        raise ValueError("DATABASE_URL not set — cannot connect to risk engine DB")

    started_at = datetime.now(timezone.utc)
    logger.info("dealer_refresh_started", snapshot_date=snap_dt.isoformat())

    # Step 1: Pull from DataHub
    stats = fetch_dealer_stats(dh_url)

    # Step 2: Previous rates
    re_conn = psycopg2.connect(re_url)
    try:
        previous_rates = fetch_previous_rates(re_conn)

        # Step 3: Write
        rows_written = write_dealer_metrics(re_conn, stats, previous_rates, snap_dt)
    finally:
        re_conn.close()

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    watchlist = sum(1 for s in stats if s.is_watchlist)

    result = {
        "snapshot_date":   snap_dt.isoformat(),
        "dealers_processed": len(stats),
        "rows_written":    rows_written,
        "watchlist_count": watchlist,
        "elapsed_seconds": round(elapsed, 2),
        "status":          "success",
    }
    logger.info("dealer_refresh_complete", **result)
    return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    try:
        result = run_refresh()
        print(f"✓ Dealer metrics refreshed: {result['dealers_processed']} dealers, "
              f"{result['watchlist_count']} on watchlist ({result['elapsed_seconds']}s)")
    except Exception as e:
        print(f"✗ Refresh failed: {e}", file=sys.stderr)
        sys.exit(1)
