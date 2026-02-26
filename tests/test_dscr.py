"""
Unit tests for DSCR calculator.
"""
from app.schemas.risk_request import ContractData, CustomerData
from app.services.dscr_calculator import calculate_dscr


def _make_b2c_customer(**kwargs) -> CustomerData:
    defaults = {
        "customer_id": "CUST-T01",
        "date_of_birth": "1985-03-15",
        "party_type": "B2C",
        "monthly_net_income": 7_000.0,
        "monthly_rent": 1_200.0,
        "monthly_insurance": 250.0,
        "monthly_alimony": 0.0,
        "monthly_existing_obligations": 400.0,
    }
    defaults.update(kwargs)
    return CustomerData(**defaults)


def _make_b2b_customer(**kwargs) -> CustomerData:
    defaults = {
        "customer_id": "CUST-T02",
        "date_of_birth": "1975-01-01",
        "party_type": "B2B",
        "annual_ebitda": 300_000.0,
        "total_debt_service": 80_000.0,
    }
    defaults.update(kwargs)
    return CustomerData(**defaults)


def _make_contract(**kwargs) -> ContractData:
    defaults = {
        "contract_id": "CTR-T01",
        "financed_amount": 40_000.0,
        "downpayment_amount": 10_000.0,
        "term_months": 48,
        "monthly_payment": 900.0,
    }
    defaults.update(kwargs)
    return ContractData(**defaults)


class TestB2CDSCR:
    def test_positive_dscr(self):
        cust = _make_b2c_customer()
        contract = _make_contract()
        result = calculate_dscr(cust, contract)

        assert result.is_valid
        assert result.calculation_method == "B2C_NET_INCOME"
        assert result.dscr_value is not None
        # Net 7000 - rent 1200 - ins 250 - alimony 0 - obligations 400 - living 1485 = 3665
        # DSCR = 3665 / 900 ≈ 4.07
        assert 3.5 < result.dscr_value < 4.5

    def test_no_income_fallback(self):
        cust = _make_b2c_customer(monthly_net_income=None)
        contract = _make_contract()
        result = calculate_dscr(cust, contract)

        assert not result.is_valid
        assert result.calculation_method == "FALLBACK"

    def test_negative_dscr(self):
        cust = _make_b2c_customer(
            monthly_net_income=2_000.0,
            monthly_rent=1_500.0,
            monthly_existing_obligations=1_000.0,
        )
        contract = _make_contract()
        result = calculate_dscr(cust, contract)

        assert result.is_valid
        assert result.dscr_value is not None
        assert result.dscr_value < 0


class TestB2BDSCR:
    def test_healthy_b2b(self):
        cust = _make_b2b_customer()
        contract = _make_contract()
        result = calculate_dscr(cust, contract)

        assert result.is_valid
        assert result.calculation_method == "B2B_EBITDA"
        # EBITDA 300k / (80k existing + 10.8k new) = 300k / 90.8k ≈ 3.30
        assert 3.0 < result.dscr_value < 3.5

    def test_no_ebitda_fallback(self):
        cust = _make_b2b_customer(annual_ebitda=None)
        contract = _make_contract()
        result = calculate_dscr(cust, contract)

        assert not result.is_valid
        assert result.calculation_method == "FALLBACK"
