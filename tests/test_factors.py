"""
Unit tests for individual scoring factors.
"""
from datetime import date
from app.scoring.factors import (
    score_ltv, score_term, score_age, score_crif, score_intrum,
    score_dscr, score_permit, score_vehicle_price_tier, score_zek,
    score_dealer_risk,
)


class TestLTV:
    def test_low_ltv_best_score(self):
        r = score_ltv(financed_amount=30_000, vehicle_price=60_000)  # 50%
        assert r.bin_label == "<75%"
        assert r.raw_score == 8.0

    def test_mid_ltv(self):
        r = score_ltv(financed_amount=48_000, vehicle_price=60_000)  # 80%
        assert r.bin_label == "75-85%"
        assert r.raw_score == 4.0

    def test_high_ltv(self):
        r = score_ltv(financed_amount=54_000, vehicle_price=60_000)  # 90%
        assert r.bin_label == "85-95%"
        assert r.raw_score == 0.0

    def test_very_high_ltv(self):
        r = score_ltv(financed_amount=59_000, vehicle_price=60_000)  # 98.3%
        assert r.bin_label == ">95%"
        assert r.raw_score == -8.0

    def test_zero_vehicle_price(self):
        r = score_ltv(financed_amount=10_000, vehicle_price=0)
        assert r.bin_label == "MISSING"


class TestTerm:
    def test_short_term(self):
        assert score_term(24).raw_score == 5.0

    def test_mid_term(self):
        assert score_term(48).raw_score == 6.0

    def test_long_term(self):
        assert score_term(60).raw_score == -3.0


class TestAge:
    def test_young(self):
        r = score_age(date(2004, 1, 1), reference_date=date(2026, 2, 26))
        assert r.bin_label == "18-25"
        assert r.raw_score == -6.0

    def test_prime(self):
        r = score_age(date(1976, 6, 15), reference_date=date(2026, 2, 26))
        assert r.bin_label == "46-55"
        assert r.raw_score == 7.0

    def test_minor(self):
        r = score_age(date(2010, 1, 1), reference_date=date(2026, 2, 26))
        assert r.bin_label == "<18 (minor)"
        assert r.raw_score == -10.0


class TestCRIF:
    def test_excellent(self):
        assert score_crif(750).raw_score == 8.0

    def test_good(self):
        assert score_crif(550).raw_score == 4.0

    def test_poor(self):
        assert score_crif(200).raw_score == -8.0

    def test_missing(self):
        assert score_crif(None).raw_score == -5.0


class TestIntrum:
    def test_no_data(self):
        assert score_intrum(0).raw_score == -4.0

    def test_established(self):
        assert score_intrum(5).raw_score == 5.0


class TestDSCR:
    def test_strong(self):
        assert score_dscr(20.0).raw_score == 7.0

    def test_tight(self):
        assert score_dscr(2.0).raw_score == -3.0

    def test_negative(self):
        assert score_dscr(-1.5).raw_score == -8.0


class TestPermit:
    def test_b2b(self):
        assert score_permit("B2B", "C").raw_score == -3.0  # B2B overrides permit

    def test_c_permit(self):
        assert score_permit("B2C", "C").raw_score == 5.0

    def test_b_permit(self):
        assert score_permit("B2C", "B").raw_score == -3.0

    def test_unknown(self):
        assert score_permit("B2C", None).raw_score == 2.0


class TestVehiclePriceTier:
    def test_economy(self):
        assert score_vehicle_price_tier(15_000).raw_score == -2.0

    def test_mid(self):
        assert score_vehicle_price_tier(35_000).raw_score == 3.0

    def test_premium(self):
        assert score_vehicle_price_tier(75_000).raw_score == 2.0


class TestZEK:
    def test_clean(self):
        assert score_zek(False).raw_score == 5.0

    def test_multiple_entries(self):
        assert score_zek(True, 3).raw_score == -7.0

    def test_not_checked(self):
        assert score_zek(None).raw_score == 0.0


class TestDealerRisk:
    def test_low(self):
        assert score_dealer_risk(0.02, 24).raw_score == 4.0

    def test_new_dealer(self):
        assert score_dealer_risk(None, None).raw_score == -2.0

    def test_high_risk_dealer(self):
        assert score_dealer_risk(0.18, 36).raw_score == -6.0
