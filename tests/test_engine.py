"""
Integration tests for the full scoring engine.
Tests end-to-end scoring with realistic LeaseTeq scenarios.
"""
from datetime import date

from app.schemas.risk_request import (
    ContractData, CustomerData, DealerData, RiskEvaluationRequest, VehicleData,
)
from app.schemas.risk_response import Decision, RiskTier
from app.scoring.engine import evaluate


def _make_request(**overrides) -> RiskEvaluationRequest:
    """Build a baseline 'good' application, then override specific fields."""
    customer_kwargs = {
        "customer_id": "CUST-001",
        "date_of_birth": date(1980, 5, 15),  # age ~45
        "party_type": "B2C",
        "permit_type": "C",
        "monthly_net_income": 8_000.0,
        "monthly_rent": 1_500.0,
        "monthly_insurance": 300.0,
        "monthly_alimony": 0.0,
        "monthly_existing_obligations": 500.0,
        "crif_score": 720,
        "intrum_score": 5,
        "zek_has_entries": False,
        "zek_entry_count": 0,
    }
    customer_kwargs.update(overrides.get("customer", {}))

    vehicle_kwargs = {"vehicle_price": 50_000.0}
    vehicle_kwargs.update(overrides.get("vehicle", {}))

    contract_kwargs = {
        "contract_id": "CTR-001",
        "financed_amount": 40_000.0,  # LTV=80%
        "downpayment_amount": 10_000.0,
        "term_months": 48,
        "monthly_payment": 900.0,
    }
    contract_kwargs.update(overrides.get("contract", {}))

    dealer_kwargs = {
        "dealer_id": "DLR-001",
        "dealer_default_rate": 0.04,
        "dealer_active_months": 36,
    }
    dealer_kwargs.update(overrides.get("dealer", {}))

    return RiskEvaluationRequest(
        request_id="TEST-001",
        timestamp="2026-02-26T17:00:00Z",
        customer=CustomerData(**customer_kwargs),
        vehicle=VehicleData(**vehicle_kwargs),
        contract=ContractData(**contract_kwargs),
        dealer=DealerData(**dealer_kwargs),
    )


class TestEngineEndToEnd:

    def test_good_application_bright_green(self):
        """Prime-age, C-permit, low LTV, strong DSCR, clean ZEK → BRIGHT_GREEN."""
        req = _make_request()
        resp = evaluate(req)

        assert resp.tier == RiskTier.BRIGHT_GREEN
        assert resp.decision == Decision.AUTO_APPROVE
        assert resp.total_score > 25
        assert len(resp.factor_scores) == 10
        assert resp.legacy_band in ("A", "B")

    def test_risky_application_red(self):
        """Young, B-permit, high LTV, no income, bad CRIF → RED."""
        req = _make_request(
            customer={
                "date_of_birth": date(2003, 1, 1),  # age 23
                "permit_type": "B",
                "monthly_net_income": 0.0,
                "crif_score": 200,
                "intrum_score": 0,
                "zek_has_entries": True,
                "zek_entry_count": 4,
            },
            contract={
                "financed_amount": 49_000.0,  # LTV=98%
                "downpayment_amount": 1_000.0,
                "term_months": 60,
                "monthly_payment": 900.0,
            },
        )
        resp = evaluate(req)

        assert resp.tier == RiskTier.RED
        assert resp.decision == Decision.DECLINE
        assert len(resp.business_rule_overrides) > 0  # BR-05 (CRIF<150), BR-04 (ZEK>=3), BR-06 (no income)

    def test_borderline_yellow(self):
        """Average everything → should land in YELLOW or GREEN."""
        req = _make_request(
            customer={
                "crif_score": 450,
                "intrum_score": 2,
                "permit_type": "B",
            },
            contract={
                "financed_amount": 46_000.0,  # LTV=92%
                "term_months": 60,
            },
        )
        resp = evaluate(req)

        assert resp.tier in (RiskTier.YELLOW, RiskTier.GREEN)
        assert resp.decision in (Decision.MANUAL_REVIEW, Decision.APPROVE_STANDARD)

    def test_business_rule_minor_forces_red(self):
        """Even with perfect scores, a minor triggers BR-01 → RED."""
        req = _make_request(
            customer={"date_of_birth": date(2010, 6, 1)},  # 15 years old
        )
        resp = evaluate(req)

        assert resp.tier == RiskTier.RED
        override_codes = [o.rule_code for o in resp.business_rule_overrides]
        assert "BR-01" in override_codes

    def test_business_rule_extreme_ltv(self):
        """LTV > 120% → BR-02 forces RED."""
        req = _make_request(
            contract={"financed_amount": 65_000.0},  # 130% of 50k
        )
        resp = evaluate(req)

        override_codes = [o.rule_code for o in resp.business_rule_overrides]
        assert "BR-02" in override_codes
        assert resp.tier == RiskTier.RED

    def test_b2b_application(self):
        """B2B with EBITDA-based DSCR."""
        req = _make_request(
            customer={
                "party_type": "B2B",
                "permit_type": None,
                "monthly_net_income": None,
                "annual_ebitda": 500_000.0,
                "total_debt_service": 100_000.0,
            },
        )
        resp = evaluate(req)

        assert resp.dscr.calculation_method == "B2B_EBITDA"
        assert resp.dscr.dscr_value is not None
        assert resp.dscr.dscr_value > 0

    def test_idempotency_key_in_response(self):
        req = _make_request()
        resp = evaluate(req)
        assert resp.request_id == "TEST-001"

    def test_legacy_scorecard_populated(self):
        req = _make_request()
        resp = evaluate(req)
        assert resp.legacy_score is not None
        assert resp.legacy_band is not None
        assert 333 <= resp.legacy_score <= 502

    def test_processing_time_reasonable(self):
        """Scoring should complete in under 50ms (no I/O)."""
        req = _make_request()
        resp = evaluate(req)
        assert resp.processing_time_ms < 50

    def test_all_factors_present(self):
        req = _make_request()
        resp = evaluate(req)
        factor_names = {fs.factor_name for fs in resp.factor_scores}
        expected = {"LTV", "Term", "Age", "CRIF", "Intrum", "DSCR", "Permit", "VehiclePriceTier", "ZEK", "DealerRisk"}
        assert factor_names == expected
