from datetime import datetime, timezone, timedelta
from detector import Detector
from models import Trade

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def tr(sec, price=100.0, usd=100.0, sym="BTCUSDT"):
    return Trade(T0 + timedelta(seconds=sec), sym, str(sec), price, usd / price, "BUY", usd)


def test_whale():
    d = Detector()
    assert [a.signal_type for a in d.process(tr(0, usd=60_000))] == ["WHALE"]
    assert d.process(tr(1, usd=40_000)) == []


def test_volatility_and_cooldown():
    d = Detector()
    for i in range(10):
        assert d.process(tr(i)) == []
    a = d.process(tr(11, price=102.0))
    assert [x.signal_type for x in a] == ["VOLATILITY"] and a[0].metric_value > 1.5
    assert d.process(tr(12, price=103.0)) == []  # cooldown
    assert d.process(tr(13, price=100.5)) == []


def test_volume_spike():
    d = Detector()
    sigs = []
    for s in range(0, 1300):          # steady $100/s for > window
        sigs += d.process(tr(s))
    assert not sigs
    for s in range(1300, 1700):       # 10x volume
        sigs += [a.signal_type for a in d.process(tr(s, usd=1000))]
    assert "VOLUME_SPIKE" in sigs
