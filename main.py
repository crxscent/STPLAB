"""CryptoMonitor Stream worker: source -> detector -> MongoDB (raw) + PostgreSQL (anomalies, metrics)."""
import asyncio
import logging
import os
from datetime import datetime, timezone

import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient

from detector import Detector, MetricsAggregator, Rule
from sources import trade_source

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

PG_DSN = os.getenv("PG_DSN", "postgresql://crypto:crypto@localhost:5432/cryptomonitor")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
SOURCE = os.getenv("SOURCE", "binance")
SYMBOLS = [s.strip().upper() for s in os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT").split(",")]
BATCH = int(os.getenv("MONGO_BATCH", "200"))
METRICS_INTERVAL = float(os.getenv("METRICS_INTERVAL", "10"))


async def connect_pg():
    for i in range(30):
        try:
            return await asyncpg.create_pool(PG_DSN, min_size=1, max_size=4)
        except Exception as e:
            log.info("Waiting for PostgreSQL (%s)", e)
            await asyncio.sleep(2)
    raise RuntimeError("PostgreSQL unavailable")


async def load_rules(pool, detector: Detector):
    while True:
        try:
            rows = await pool.fetch("SELECT rule_type, threshold, window_sec, cooldown_sec, enabled FROM monitoring_rules")
            for r in rows:
                detector.rules[r["rule_type"]] = Rule(r["rule_type"], float(r["threshold"]), r["window_sec"],
                                                      r["cooldown_sec"], r["enabled"])
        except Exception as e:
            log.warning("Rule reload failed: %s", e)
        await asyncio.sleep(30)


async def mongo_writer(queue: asyncio.Queue, coll):
    buf = []
    while True:
        try:
            doc = await asyncio.wait_for(queue.get(), timeout=1.0)
            buf.append(doc)
        except asyncio.TimeoutError:
            pass
        if buf and (len(buf) >= BATCH or queue.empty()):
            try:
                await coll.insert_many(buf, ordered=False)
            except Exception as e:
                log.warning("Mongo insert failed: %s", e)
            buf = []


async def metrics_flusher(pool, agg: MetricsAggregator, detector: Detector):
    while True:
        await asyncio.sleep(METRICS_INTERVAL)
        rows = agg.flush(datetime.now(timezone.utc), detector, METRICS_INTERVAL)
        if rows:
            await pool.executemany(
                "INSERT INTO market_metrics VALUES ($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT DO NOTHING", rows)


INSERT_ANOMALY = """
INSERT INTO anomalies (trade_time, symbol, signal_type, severity, price, volume, total_usd, side,
                       trade_id, metric_value, threshold, message)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)"""


async def main():
    pool = await connect_pg()
    mongo = AsyncIOMotorClient(MONGO_URI)
    coll = mongo.cryptomonitor.trades
    await coll.create_index([("symbol", 1), ("timestamp", -1)])

    detector = Detector()
    agg = MetricsAggregator()
    queue: asyncio.Queue = asyncio.Queue(maxsize=50_000)
    tasks = [asyncio.create_task(load_rules(pool, detector)),
             asyncio.create_task(mongo_writer(queue, coll)),
             asyncio.create_task(metrics_flusher(pool, agg, detector))]

    count = 0
    async for trade in trade_source(SOURCE, SYMBOLS):
        count += 1
        try:
            queue.put_nowait(trade.to_doc())
        except asyncio.QueueFull:
            log.warning("Mongo queue full, dropping raw trade")
        agg.add(trade)
        for a in detector.process(trade):
            t = a.trade
            await pool.execute(INSERT_ANOMALY, t.timestamp, t.symbol, a.signal_type, a.severity, t.price,
                               t.volume, t.total_usd, t.side, t.trade_id, a.metric_value, a.threshold, a.message)
            log.info("ANOMALY %s", a.message)
        if count % 5000 == 0:
            log.info("Processed %d trades", count)


if __name__ == "__main__":
    asyncio.run(main())
