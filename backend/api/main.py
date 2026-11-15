"""CryptoMonitor API + notification service.

* LISTENs on PostgreSQL channel `anomalies` (fired by a trigger on INSERT)
* sends an alert card to Telegram and updates notify_status
* broadcasts the anomaly to mobile clients over WebSocket /ws/alerts
* REST endpoints for the mobile app (alerts, stats, metrics, rules)
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from decimal import Decimal

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("api")

PG_DSN = os.getenv("PG_DSN", "postgresql://crypto:crypto@localhost:5432/cryptomonitor")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
TG_MIN_SEVERITY = os.getenv("TELEGRAM_MIN_SEVERITY", "HIGH")
SEV_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def row_to_dict(r) -> dict:
    out = {}
    for k, v in dict(r).items():
        if isinstance(v, Decimal):
            v = float(v)
        elif hasattr(v, "isoformat"):
            v = v.isoformat()
        out[k] = v
    return out


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()

    async def broadcast(self, payload: dict):
        msg = json.dumps(payload)
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                self.clients.discard(ws)


hub = Hub()
state: dict = {}


def tg_card(a: dict) -> str:
    return (f"🚨 <b>{a['signal_type']}</b> · {a['severity']}\n"
            f"<b>{a['symbol']}</b>\n{a['message']}\n"
            f"Price: {a['price']:g} · Volume: ${a['total_usd']:,.0f} · Side: {a['side']}\n"
            f"Time: {a['trade_time']}")


async def send_telegram(a: dict) -> str:
    if not (TG_TOKEN and TG_CHAT):
        return "SKIPPED"
    if SEV_ORDER.get(a["severity"], 0) < SEV_ORDER.get(TG_MIN_SEVERITY, 0):
        return "SKIPPED"
    try:
        r = await state["http"].post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                                     json={"chat_id": TG_CHAT, "text": tg_card(a), "parse_mode": "HTML"})
        if r.status_code == 429:  # rate limited
            await asyncio.sleep(r.json().get("parameters", {}).get("retry_after", 1))
            return await send_telegram(a)
        return "SENT" if r.status_code == 200 else "FAILED"
    except Exception as e:
        log.warning("Telegram error: %s", e)
        return "FAILED"


async def notifier(queue: asyncio.Queue):
    pool = state["pool"]
    while True:
        aid = await queue.get()
        row = await pool.fetchrow("SELECT * FROM anomalies WHERE id=$1", aid)
        if not row:
            continue
        a = row_to_dict(row)
        await hub.broadcast({"type": "anomaly", "data": a})
        status = await send_telegram(a)
        await pool.execute("UPDATE anomalies SET notify_status=$1, notified_at=now() WHERE id=$2", status, aid)


async def listener(queue: asyncio.Queue):
    while True:
        try:
            conn = await asyncpg.connect(PG_DSN)
            await conn.add_listener("anomalies", lambda *args: queue.put_nowait(int(args[3])))
            log.info("Listening for anomalies")
            while not conn.is_closed():
                await asyncio.sleep(5)
        except Exception as e:
            log.warning("Listener error: %s", e)
            await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(app):
    for _ in range(30):
        try:
            state["pool"] = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=5)
            break
        except Exception as e:
            log.info("Waiting for PostgreSQL (%s)", e)
            await asyncio.sleep(2)
    state["http"] = httpx.AsyncClient(timeout=10)
    q: asyncio.Queue = asyncio.Queue()
    tasks = [asyncio.create_task(listener(q)), asyncio.create_task(notifier(q))]
    yield
    for t in tasks:
        t.cancel()
    await state["http"].aclose()
    await state["pool"].close()


app = FastAPI(title="CryptoMonitor Stream API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"ok": True, "ws_clients": len(hub.clients)}


@app.get("/api/alerts")
async def alerts(limit: int = 50, symbol: str | None = None, signal_type: str | None = None):
    rows = await state["pool"].fetch(
        """SELECT * FROM anomalies WHERE ($1::text IS NULL OR symbol=$1)
           AND ($2::text IS NULL OR signal_type=$2) ORDER BY detected_at DESC LIMIT $3""",
        symbol, signal_type, min(limit, 500))
    return [row_to_dict(r) for r in rows]


@app.get("/api/stats")
async def stats():
    pool = state["pool"]
    counts = await pool.fetchrow("""
        SELECT count(*) FILTER (WHERE detected_at > now() - interval '10 minutes') AS last_10m,
               count(*) FILTER (WHERE detected_at > now() - interval '1 hour')     AS last_1h,
               count(*) FILTER (WHERE detected_at > now() - interval '1 day')      AS last_24h
        FROM anomalies""")
    by_type = await pool.fetch("""SELECT signal_type, count(*) AS n FROM anomalies
                                  WHERE detected_at > now() - interval '1 day' GROUP BY 1""")
    assets = await pool.fetch("""
        SELECT DISTINCT ON (symbol) symbol, last_price, ts FROM market_metrics ORDER BY symbol, ts DESC""")
    agg = await pool.fetch("""
        SELECT symbol, sum(vwap*volume_usd)/NULLIF(sum(volume_usd),0) AS vwap_1h,
               avg(volatility_pct) AS volatility_1h, avg(volume_dev_pct) AS volume_dev_1h,
               sum(volume_usd) AS volume_usd_1h
        FROM market_metrics WHERE ts > now() - interval '1 hour' GROUP BY symbol""")
    agg_map = {r["symbol"]: row_to_dict(r) for r in agg}
    return {
        "anomalies": row_to_dict(counts),
        "by_type": {r["signal_type"]: r["n"] for r in by_type},
        "assets": [{**row_to_dict(a), **agg_map.get(a["symbol"], {})} for a in assets],
    }


@app.get("/api/metrics/{symbol}")
async def metrics(symbol: str, minutes: int = 60):
    rows = await state["pool"].fetch(
        """SELECT ts, last_price, vwap, volatility_pct, volume_usd, volume_dev_pct FROM market_metrics
           WHERE symbol=$1 AND ts > now() - make_interval(mins => $2) ORDER BY ts""",
        symbol.upper(), minutes)
    return [row_to_dict(r) for r in rows]


@app.get("/api/rules")
async def rules():
    return [row_to_dict(r) for r in await state["pool"].fetch("SELECT * FROM monitoring_rules ORDER BY id")]


class RuleUpdate(BaseModel):
    threshold: float | None = None
    window_sec: int | None = None
    cooldown_sec: int | None = None
    enabled: bool | None = None


@app.put("/api/rules/{rule_type}")
async def update_rule(rule_type: str, body: RuleUpdate):
    r = await state["pool"].fetchrow(
        """UPDATE monitoring_rules SET threshold=COALESCE($2,threshold), window_sec=COALESCE($3,window_sec),
           cooldown_sec=COALESCE($4,cooldown_sec), enabled=COALESCE($5,enabled), updated_at=now()
           WHERE rule_type=$1 RETURNING *""",
        rule_type.upper(), body.threshold, body.window_sec, body.cooldown_sec, body.enabled)
    if not r:
        raise HTTPException(404, "rule not found")
    return row_to_dict(r)


@app.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    await ws.accept()
    hub.clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # keepalive / ignore
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)
