"""Tests for pure metric functions."""

from kol.metrics import cpm, engagement_rate_check, parse_price, posting_frequency, views_per_post
from kol.fraud import detect_fraud
from kol.dedup import ChannelEntry, dedup_channels


class TestParsePrice:
    def test_dollar_suffix(self):
        assert parse_price("450$") == 450.0

    def test_dollar_prefix(self):
        assert parse_price("$450") == 450.0

    def test_usd_suffix(self):
        assert parse_price("450 USD") == 450.0

    def test_euro(self):
        assert parse_price("€50") == 50.0

    def test_comma_separated(self):
        assert parse_price("1,200$") == 1200.0

    def test_k_notation(self):
        assert parse_price("1.5k$") == 1500.0

    def test_markdown_link(self):
        assert parse_price("[80$](https://example.com)") == 80.0

    def test_none_input(self):
        assert parse_price(None) is None

    def test_empty(self):
        assert parse_price("") is None

    def test_zero(self):
        assert parse_price("0") is None

    def test_numeric(self):
        assert parse_price(100) == 100.0

    def test_float_input(self):
        assert parse_price(99.5) == 99.5


class TestCPM:
    def test_basic(self):
        assert cpm(100, 50000) == 2.0  # 1000 * 100 / 50000

    def test_zero_reach(self):
        assert cpm(100, 0) is None

    def test_none_price(self):
        assert cpm(None, 10000) is None

    def test_negative_price(self):
        assert cpm(-5, 10000) is None


class TestERCheck:
    def test_very_high(self):
        assert engagement_rate_check(15.0) == "very-high"

    def test_average(self):
        assert engagement_rate_check(3.0) == "average"

    def test_low(self):
        assert engagement_rate_check(1.0) == "low"

    def test_none(self):
        assert engagement_rate_check(None) is None


class TestFraud:
    def test_low_reach_ratio(self):
        flags = detect_fraud(subscribers=100000, reach=2000)
        assert any(f.code == "LOW_REACH_RATIO" for f in flags)

    def test_extreme_er(self):
        flags = detect_fraud(er_pct=35.0)
        assert any(f.code == "EXTREME_ER" for f in flags)

    def test_growth_spike(self):
        flags = detect_fraud(subscriber_growth_30d_pct=120.0)
        assert any(f.code == "GROWTH_SPIKE" for f in flags)

    def test_clean_channel(self):
        flags = detect_fraud(subscribers=50000, reach=20000, er_pct=5.0)
        assert len(flags) == 0

    def test_dead_views(self):
        flags = detect_fraud(subscribers=100000, views_avg=50)
        assert any(f.code == "DEAD_VIEWS" for f in flags)


class TestDedup:
    def test_case_insensitive(self):
        entries = [
            ChannelEntry(handle="@CryptoAlpha", price_raw="100$"),
            ChannelEntry(handle="@cryptoalpha", price_raw="200$"),
        ]
        result = dedup_channels(entries)
        assert len(result) == 1
        assert result[0].handle == "@CryptoAlpha"  # Keeps first (lower price)

    def test_keep_min_price(self):
        entries = [
            ChannelEntry(handle="@chan", price_raw="500$"),
            ChannelEntry(handle="@Chan", price_raw="200$"),
        ]
        result = dedup_channels(entries)
        assert len(result) == 1
        assert parse_price(result[0].price_raw) == 200.0

    def test_no_duplicates(self):
        entries = [
            ChannelEntry(handle="@alpha"),
            ChannelEntry(handle="@beta"),
        ]
        result = dedup_channels(entries)
        assert len(result) == 2

    def test_keep_priced_over_unpriced(self):
        entries = [
            ChannelEntry(handle="@chan", price_raw=None),
            ChannelEntry(handle="@Chan", price_raw="100$"),
        ]
        result = dedup_channels(entries)
        assert len(result) == 1
        assert parse_price(result[0].price_raw) == 100.0


class TestViewsPerPost:
    def test_basic(self):
        assert views_per_post(10000, 10) == 1000.0

    def test_zero_posts(self):
        assert views_per_post(10000, 0) is None


class TestPostingFrequency:
    def test_daily(self):
        result = posting_frequency(30, days=30)
        assert abs(result - 7.0) < 0.01

    def test_weekly(self):
        result = posting_frequency(4, days=28)
        assert abs(result - 1.0) < 0.01
