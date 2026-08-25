from intervals_mcp import analytics


class TestClassifyForm:
    def test_deep_negative_tsb_is_high_risk(self):
        label, _ = analytics.classify_form(-35)

        assert label == "high_risk"

    def test_moderately_negative_tsb_is_overreaching(self):
        label, _ = analytics.classify_form(-20)

        assert label == "overreaching"

    def test_tsb_near_zero_is_neutral(self):
        label, _ = analytics.classify_form(0)

        assert label == "neutral"

    def test_positive_tsb_is_fresh(self):
        label, _ = analytics.classify_form(15)

        assert label == "fresh"

    def test_very_high_tsb_is_very_fresh(self):
        label, _ = analytics.classify_form(40)

        assert label == "very_fresh"

    def test_band_boundaries_belong_to_the_higher_band(self):
        # -10 is the start of "neutral" in the -30/-10/5/25 banding, not the
        # tail of "overreaching".
        label, _ = analytics.classify_form(-10)

        assert label == "neutral"


class TestClassifyRamp:
    def test_negative_rate_is_declining(self):
        label, _ = analytics.classify_ramp(-2)

        assert label == "declining"

    def test_small_positive_rate_is_maintaining(self):
        label, _ = analytics.classify_ramp(1.5)

        assert label == "maintaining"

    def test_moderate_rate_is_building(self):
        label, _ = analytics.classify_ramp(6)

        assert label == "building"

    def test_steep_rate_is_aggressive(self):
        label, _ = analytics.classify_ramp(12)

        assert label == "aggressive"


class TestHrvDeviation:
    def test_none_when_recent_is_empty(self):
        assert analytics.hrv_deviation([], [60, 61, 62]) is None

    def test_none_when_baseline_is_empty(self):
        assert analytics.hrv_deviation([55, 56], []) is None

    def test_reports_a_drop_below_baseline(self):
        result = analytics.hrv_deviation(recent=[45, 45], baseline=[60, 60, 60])

        assert result["pct_change"] == -25.0
        assert result["below_baseline"] is True

    def test_does_not_flag_a_small_dip(self):
        result = analytics.hrv_deviation(recent=[58], baseline=[60, 60])

        assert result["below_baseline"] is False

    def test_reports_a_rise_above_baseline(self):
        result = analytics.hrv_deviation(recent=[66], baseline=[60])

        assert result["pct_change"] == 10.0
        assert result["below_baseline"] is False


class TestAssessReadiness:
    def _day(self, day_id, ctl, atl, ramp=1.0, hrv=None):
        entry = {"id": day_id, "ctl": ctl, "atl": atl, "rampRate": ramp}
        if hrv is not None:
            entry["hrv"] = hrv
        return entry

    def test_errors_when_no_day_has_ctl_and_atl(self):
        result = analytics.assess_readiness([{"id": "2026-08-01"}])

        assert "error" in result

    def test_uses_the_most_recent_day_with_data(self):
        days = [
            self._day("2026-08-01", ctl=40, atl=30),
            self._day("2026-08-02", ctl=41, atl=32),
        ]

        result = analytics.assess_readiness(days)

        assert result["as_of"] == "2026-08-02"
        assert result["ctl"] == 41
        assert result["atl"] == 32
        assert result["tsb"] == 9.0
        assert result["form"] == "fresh"

    def test_skips_trailing_days_missing_ctl_or_atl(self):
        days = [
            self._day("2026-08-01", ctl=40, atl=30),
            {"id": "2026-08-02", "ctl": None, "atl": None},
        ]

        result = analytics.assess_readiness(days)

        assert result["as_of"] == "2026-08-01"

    def test_includes_ramp_classification(self):
        days = [self._day("2026-08-01", ctl=40, atl=30, ramp=9)]

        result = analytics.assess_readiness(days)

        assert result["ramp"] == "aggressive"

    def test_omits_ramp_when_the_field_is_absent(self):
        day = {"id": "2026-08-01", "ctl": 40, "atl": 30}

        result = analytics.assess_readiness([day])

        assert "ramp" not in result

    def test_compares_recent_hrv_against_older_baseline(self):
        days = [
            *[self._day(f"2026-07-{i:02d}", ctl=40, atl=30, hrv=60) for i in range(1, 11)],
            *[self._day(f"2026-08-{i:02d}", ctl=40, atl=30, hrv=45) for i in range(1, 8)],
        ]

        result = analytics.assess_readiness(days, recent_days=7)

        assert result["hrv"]["below_baseline"] is True
        assert result["hrv"]["baseline_avg"] == 60.0
        assert result["hrv"]["recent_avg"] == 45.0

    def test_omits_hrv_when_no_day_reports_it(self):
        days = [self._day("2026-08-01", ctl=40, atl=30)]

        result = analytics.assess_readiness(days)

        assert "hrv" not in result
