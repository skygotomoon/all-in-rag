from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


class Config(BaseModel):
    venue_name: str = "默认场地"
    fetch_url: str = "http://localhost:9000/mock"
    poll_interval_seconds: int = Field(default=10, ge=3, le=300)
    occupied_threshold: float = Field(default=0.85, ge=0.0, le=1.0)


@dataclass
class SlotSnapshot:
    timestamp: str
    total: int
    occupied: int

    @property
    def ratio(self) -> float:
        return 0.0 if self.total == 0 else self.occupied / self.total


class VenueMonitor:
    def __init__(self, db_path: str = "venue_monitor.db") -> None:
        self.db_path = db_path
        self._init_db()
        self._subscribers: List[asyncio.Queue] = []

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    venue_name TEXT NOT NULL,
                    total_slots INTEGER NOT NULL,
                    occupied_slots INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def save(self, venue_name: str, snapshot: SlotSnapshot) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO snapshots (ts, venue_name, total_slots, occupied_slots) VALUES (?, ?, ?, ?)",
                (snapshot.timestamp, venue_name, snapshot.total, snapshot.occupied),
            )
            conn.commit()

    def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT ts, venue_name, total_slots, occupied_slots FROM snapshots ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for ts, venue, total, occupied in rows[::-1]:
            ratio = 0.0 if total == 0 else occupied / total
            result.append(
                {
                    "timestamp": ts,
                    "venue_name": venue,
                    "total_slots": total,
                    "occupied_slots": occupied,
                    "occupancy_ratio": round(ratio, 4),
                }
            )
        return result

    async def publish(self, payload: Dict[str, Any]) -> None:
        for q in list(self._subscribers):
            await q.put(payload)

    async def subscribe(self):
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        try:
            while True:
                item = await q.get()
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            self._subscribers.remove(q)


def parse_payload(raw: Dict[str, Any]) -> SlotSnapshot:
    # 约定上游返回:
    # {"total_slots": 12, "occupied_slots": 8}
    total = int(raw.get("total_slots", 0))
    occupied = int(raw.get("occupied_slots", 0))
    if total < 0 or occupied < 0 or occupied > total:
        raise ValueError("invalid slot numbers")
    return SlotSnapshot(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total=total,
        occupied=occupied,
    )


app = FastAPI(title="WeChat Mini Program Venue Monitor")
config = Config()
monitor = VenueMonitor()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
def get_config() -> Config:
    return config


@app.post("/config")
def update_config(new_config: Config) -> Config:
    global config
    config = new_config
    return config


@app.get("/history")
def get_history(limit: int = 50):
    if limit > 500:
        raise HTTPException(status_code=400, detail="limit too large")
    return monitor.history(limit)


@app.get("/stream")
async def stream_events():
    return StreamingResponse(monitor.subscribe(), media_type="text/event-stream")


@app.get("/mock")
def mock_data() -> Dict[str, int]:
    now_second = datetime.now().second
    total = 20
    occupied = (now_second * 7) % 20
    return {"total_slots": total, "occupied_slots": occupied}


async def polling_loop() -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        while True:
            try:
                resp = await client.get(config.fetch_url)
                resp.raise_for_status()
                snapshot = parse_payload(resp.json())
                monitor.save(config.venue_name, snapshot)
                payload = {
                    "timestamp": snapshot.timestamp,
                    "venue_name": config.venue_name,
                    "total_slots": snapshot.total,
                    "occupied_slots": snapshot.occupied,
                    "occupancy_ratio": round(snapshot.ratio, 4),
                    "alert": snapshot.ratio >= config.occupied_threshold,
                }
                await monitor.publish(payload)
            except Exception as e:  # noqa: BLE001
                await monitor.publish({"error": str(e)})
            await asyncio.sleep(config.poll_interval_seconds)


@app.on_event("startup")
async def startup_event() -> None:
    asyncio.create_task(polling_loop())
