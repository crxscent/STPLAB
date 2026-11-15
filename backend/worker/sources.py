"""Trade sources: Binance public WebSocket and a market simulator."""
import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from typing import AsyncIterator

import websockets

from models import Trade

log = logging.getLogger("source")

BINANCE_WS = "wss://stream.binance.com:9443/stream?streams="


async def binance_stream(symbols: list[str]) -> AsyncIterator[Trade]:
    url = BINANCE_WS + "/".join(f"{s.lower()}@trade" for s in symbols)
    async with websockets.connect(url, ping_interval=20, open_timeout=10) as ws:
        log.info("Connected to Binance: %s", url)
        async for raw in ws:
            d = json.loads(raw).get("data", {})
            if d.get("e") != "trade":
                continue
            price, qty = float(d["p"]), float(d["q"])
            yield Trade(
                timestamp=datetime.fromtimestamp(d["T"] / 1000, tz=timezone.utc),
                symbol=d["s"],
                trade_id=str(d["t"]),
                price=price,
                volume=qty,
                # m = buyer is market maker -> aggressive side is SELL
                side="SELL" if d["m"] else "BUY",
                total_usd=round(price * qty, 2),
            )


SIM_START = {"BTCUSDT": 67000.0, "ETHUSDT": 3500.0, "SOLUSDT": 150.0, "BNBUSDT": 580.0, "XRPUSDT": 0.55}


async def simulator_stream(symbols: list[str], rate: float = 20.0) -> AsyncIterator[Trade]:
    """Random-walk market with injected whales, price jumps and volume bursts."""
    prices = {s: SIM_START.get(s, 100.0) for s in symbols}
    seq = 0
    burst_until: dict[str, float] = {}
    loop = asyncio.get_running_loop()
    log.info("Simulator started for %s at ~%.0f trades/s", symbols, rate)
    while True:
        await asyncio.sleep(random.expovariate(rate))
        now = loop.time()
        s = random.choice(symbols)
        p = prices[s] * (1 + random.gauss(0, 0.0004))
        r = random.random()
        if r < 0.0015:  # sudden price jump (volatility)
            p *= 1 + random.choice([-1, 1]) * random.uniform(0.02, 0.04)
        elif r < 0.0017 and burst_until.get(s, 0) < now - 1800:  # rare volume burst (5 min, x40)
            burst_until[s] = now + 300
        prices[s] = p
        usd = random.lognormvariate(6.5, 1.3)  # typical ~ $700
        if burst_until.get(s, 0) > now:
            usd = min(usd * 40, 45_000)  # keep burst trades below whale threshold
        if random.random() < 0.003:  # whale
            usd = random.uniform(55_000, 500_000)
        seq += 1
        yield Trade(
            timestamp=datetime.now(timezone.utc),
            symbol=s,
            trade_id=f"sim-{seq}",
            price=round(p, 6),
            volume=round(usd / p, 8),
            side=random.choice(["BUY", "SELL"]),
            total_usd=round(usd, 2),
        )


async def trade_source(kind: str, symbols: list[str]) -> AsyncIterator[Trade]:
    """Yields trades forever; reconnects Binance, falls back to the simulator."""
    failures = 0
    while True:
        if kind == "binance" and failures < 3:
            try:
                async for t in binance_stream(symbols):
                    failures = 0
                    yield t
            except Exception as e:  # network errors, geo-blocks, etc.
                failures += 1
                log.warning("Binance stream error (%s), retry %d/3", e, failures)
                await asyncio.sleep(2 * failures)
                continue
        else:
            if kind == "binance":
                log.warning("Binance unavailable, switching to simulator")
            async for t in simulator_stream(symbols):
                yield t
