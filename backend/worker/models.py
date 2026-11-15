from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class Trade:
    timestamp: datetime
    symbol: str
    trade_id: str
    price: float
    volume: float
    side: str  # BUY / SELL
    total_usd: float

    def to_doc(self) -> dict:
        d = asdict(self)
        d["ingested_at"] = datetime.now(timezone.utc)
        return d


@dataclass
class Anomaly:
    trade: Trade
    signal_type: str  # WHALE / VOLATILITY / VOLUME_SPIKE
    severity: str
    metric_value: float
    threshold: float
    message: str
