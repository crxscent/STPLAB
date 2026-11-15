"""Stream anomaly detection with sliding windows (pure logic, no I/O)."""
from collections import deque, defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from models import Trade, Anomaly


@dataclass
class Rule:
    rule_type: str
    threshold: float
    window_sec: int
    cooldown_sec: int
    enabled: bool = True


DEFAULT_RULES = {
    "WHALE": Rule("WHALE", 50_000, 0, 0),
    "VOLATILITY": Rule("VOLATILITY", 1.5, 60, 30),
    "VOLUME_SPIKE": Rule("VOLUME_SPIKE", 3.0, 600, 120),
}


@dataclass
class SymbolState:
    prices: deque = field(default_factory=deque)       # (ts, price) for SMA window
    price_sum: float = 0.0
    volumes: deque = field(default_factory=deque)      # (ts, usd) for volume window
    volume_sum: float = 0.0
    baseline: float | None = None                      # EMA of window volume
    last_baseline_update: float = 0.0
    first_ts: float | None = None
    last_alert: dict = field(default_factory=dict)     # signal -> ts


class Detector:
    BASELINE_EVERY = 60.0   # seconds between baseline updates
    BASELINE_ALPHA = 0.1

    def __init__(self, rules: dict[str, Rule] | None = None):
        self.rules = dict(rules or DEFAULT_RULES)
        self.state: dict[str, SymbolState] = defaultdict(SymbolState)

    def _cooldown_ok(self, st: SymbolState, sig: str, ts: float) -> bool:
        cd = self.rules[sig].cooldown_sec
        last = st.last_alert.get(sig)
        if last is not None and ts - last < cd:
            return False
        st.last_alert[sig] = ts
        return True

    def process(self, t: Trade) -> list[Anomaly]:
        ts = t.timestamp.timestamp()
        st = self.state[t.symbol]
        if st.first_ts is None:
            st.first_ts = ts
        out: list[Anomaly] = []

        # --- Criterion 1: whale trade
        r = self.rules.get("WHALE")
        if r and r.enabled and t.total_usd > r.threshold:
            sev = "CRITICAL" if t.total_usd > 5 * r.threshold else "HIGH"
            out.append(Anomaly(t, "WHALE", sev, t.total_usd, r.threshold,
                               f"🐋 Whale {t.side} {t.volume:g} {t.symbol} ≈ ${t.total_usd:,.0f} @ {t.price:g}"))

        # --- Criterion 2: deviation from 60s SMA (computed over previous trades)
        r = self.rules.get("VOLATILITY")
        if r:
            while st.prices and ts - st.prices[0][0] > r.window_sec:
                st.price_sum -= st.prices.popleft()[1]
            if r.enabled and len(st.prices) >= 5:
                sma = st.price_sum / len(st.prices)
                dev = (t.price - sma) / sma * 100
                if abs(dev) > r.threshold and self._cooldown_ok(st, "VOLATILITY", ts):
                    sev = "CRITICAL" if abs(dev) > 2 * r.threshold else "HIGH"
                    arrow = "📈" if dev > 0 else "📉"
                    out.append(Anomaly(t, "VOLATILITY", sev, round(dev, 3), r.threshold,
                                       f"{arrow} {t.symbol} price {t.price:g} deviates {dev:+.2f}% from {r.window_sec}s SMA {sma:g}"))
            st.prices.append((ts, t.price))
            st.price_sum += t.price

        # --- Criterion 3: rolling volume vs baseline
        r = self.rules.get("VOLUME_SPIKE")
        if r:
            st.volumes.append((ts, t.total_usd))
            st.volume_sum += t.total_usd
            while st.volumes and ts - st.volumes[0][0] > r.window_sec:
                st.volume_sum -= st.volumes.popleft()[1]
            warmed = ts - st.first_ts >= r.window_sec
            if warmed and ts - st.last_baseline_update >= self.BASELINE_EVERY:
                if st.baseline is None:
                    st.baseline = st.volume_sum
                else:
                    # do not let a running spike pull the baseline up too fast
                    cur = min(st.volume_sum, st.baseline * r.threshold)
                    st.baseline += self.BASELINE_ALPHA * (cur - st.baseline)
                st.last_baseline_update = ts
            if r.enabled and st.baseline and st.volume_sum > r.threshold * st.baseline \
                    and self._cooldown_ok(st, "VOLUME_SPIKE", ts):
                ratio = st.volume_sum / st.baseline
                out.append(Anomaly(t, "VOLUME_SPIKE", "HIGH" if ratio < 2 * r.threshold else "CRITICAL",
                                   round(ratio, 2), r.threshold,
                                   f"📊 {t.symbol} {r.window_sec // 60}-min volume ${st.volume_sum:,.0f} is {ratio:.1f}× baseline ${st.baseline:,.0f}"))
        return out

    def volume_baseline(self, symbol: str) -> float | None:
        return self.state[symbol].baseline


class MetricsAggregator:
    """Accumulates per-symbol stats for a flush interval (VWAP, volatility, volume)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.buckets: dict[str, dict] = {}

    def add(self, t: Trade):
        b = self.buckets.setdefault(t.symbol, {"pv": 0.0, "v": 0.0, "usd": 0.0, "n": 0,
                                               "prices": [], "last": t.price})
        b["pv"] += t.price * t.volume
        b["v"] += t.volume
        b["usd"] += t.total_usd
        b["n"] += 1
        b["prices"].append(t.price)
        b["last"] = t.price

    def flush(self, ts: datetime, detector: Detector, interval: float) -> list[tuple]:
        rows = []
        for sym, b in self.buckets.items():
            if not b["v"]:
                continue
            vwap = b["pv"] / b["v"]
            ps = b["prices"]
            mean = sum(ps) / len(ps)
            std = (sum((p - mean) ** 2 for p in ps) / len(ps)) ** 0.5
            vol_pct = std / mean * 100
            base = detector.volume_baseline(sym)
            win = detector.rules["VOLUME_SPIKE"].window_sec or 600
            expected = base * interval / win if base else None
            dev = (b["usd"] / expected - 1) * 100 if expected else 0.0
            rows.append((ts, sym, b["last"], vwap, vol_pct, b["n"], b["usd"], dev))
        self.reset()
        return rows
