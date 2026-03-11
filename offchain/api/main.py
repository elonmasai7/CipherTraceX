from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, List

import networkx as nx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
import jwt
from pydantic import BaseModel, Field

from offchain.common.models import Transaction
from offchain.indexer.graph_builder import build_graph, serialize_graph, subgraph_around
from offchain.api.risk_engine import score_address
from offchain.api.neo4j_graph import fetch_subgraph
from offchain.indexer.neo4j_store import from_env

try:
    import redis
except ImportError:  # pragma: no cover - optional dependency
    redis = None

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
TX_FILE = DATA_DIR / "sample_txs.json"
GRAPH_FILE = DATA_DIR / "graph.json"

app = FastAPI(title="Fraud Tracing API", version="0.1.0")
app.mount("/ui", StaticFiles(directory=BASE_DIR / "web", html=True), name="ui")
logger = logging.getLogger("fraud_api")


class CaseRequest(BaseModel):
    case_id: str
    reporter_hash: str
    metadata: Dict[str, Any]


class CaseResponse(BaseModel):
    case_id: str
    metadata_hash: str
    anchored: bool


class TxEvent(BaseModel):
    tx_hash: str = Field(..., alias="tx_hash")
    sender: str = Field(..., alias="from")
    receiver: str = Field(..., alias="to")
    amount: float
    timestamp: str


class TxBatch(BaseModel):
    items: List[TxEvent]


def _load_transactions() -> List[Transaction]:
    raw = json.loads(TX_FILE.read_text())
    return [Transaction.from_dict(item) for item in raw]


def _load_graph() -> nx.DiGraph:
    if GRAPH_FILE.exists():
        raw = json.loads(GRAPH_FILE.read_text())
        graph = nx.DiGraph()
        for node in raw.get("nodes", []):
            graph.add_node(node["id"])
        for edge in raw.get("edges", []):
            graph.add_edge(
                edge["source"],
                edge["target"],
                tx_hash=edge.get("tx_hash"),
                amount=edge.get("amount"),
                timestamp=edge.get("timestamp"),
            )
        return graph

    txs = _load_transactions()
    graph = build_graph(txs)
    GRAPH_FILE.write_text(json.dumps(serialize_graph(graph), indent=2))
    return graph


txs_cache = _load_transactions()
graph_cache = _load_graph()
neo4j_store = from_env()
AUTH_MODE = os.getenv("API_AUTH_MODE", "hmac").lower()
HMAC_SECRET = os.getenv("API_HMAC_SECRET")
JWT_SECRET = os.getenv("API_JWT_SECRET")
JWT_AUDIENCE = os.getenv("API_JWT_AUDIENCE")
JWT_ISSUER = os.getenv("API_JWT_ISSUER")

NONCE_TTL_SECONDS = int(os.getenv("API_NONCE_TTL_SECONDS", "300"))
REDIS_URL = os.getenv("API_REDIS_URL")


class NonceStore:
    def check_and_store(self, nonce: str, now: float) -> bool:
        raise NotImplementedError


class MemoryNonceStore(NonceStore):
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._nonces: Dict[str, float] = {}

    def _prune(self, now: float) -> None:
        expired = [nonce for nonce, ts in self._nonces.items() if now - ts > self._ttl_seconds]
        for nonce in expired:
            self._nonces.pop(nonce, None)

    def check_and_store(self, nonce: str, now: float) -> bool:
        self._prune(now)
        if nonce in self._nonces:
            return False
        self._nonces[nonce] = now
        return True


class RedisNonceStore(NonceStore):
    def __init__(self, client: "redis.Redis", ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    def check_and_store(self, nonce: str, now: float) -> bool:
        result = self._client.set(
            name=f"nonce:{nonce}",
            value=str(int(now)),
            nx=True,
            ex=self._ttl_seconds,
        )
        return bool(result)


def _build_nonce_store() -> NonceStore:
    if REDIS_URL:
        if redis is None:
            logger.warning("API_REDIS_URL set but redis client is not installed; falling back to memory store.")
        else:
            try:
                client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
                client.ping()
                return RedisNonceStore(client, NONCE_TTL_SECONDS)
            except Exception:
                logger.warning("Failed to connect to Redis at API_REDIS_URL; falling back to memory store.")
    return MemoryNonceStore(NONCE_TTL_SECONDS)


_nonce_store = _build_nonce_store()


class WsManager:
    def __init__(self) -> None:
        self._connections: Dict[WebSocket, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def register(self, ws: WebSocket, address: str, depth: int) -> None:
        async with self._lock:
            self._connections[ws] = {"address": address, "depth": depth}

    async def unregister(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(ws, None)

    async def broadcast_updates(self) -> None:
        async with self._lock:
            items = list(self._connections.items())

        for ws, meta in items:
            try:
                graph_raw = _fetch_graph(meta["address"], meta["depth"])
                risk_raw = _score_from_graph(meta["address"], graph_raw)
                await ws.send_json({"graph": graph_raw, "risk": risk_raw})
            except Exception:
                await self.unregister(ws)


ws_manager = WsManager()


def _graph_from_serialized(raw: Dict[str, Any]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for node in raw.get("nodes", []):
        graph.add_node(node["id"])
    for edge in raw.get("edges", []):
        graph.add_edge(
            edge["source"],
            edge["target"],
            tx_hash=edge.get("tx_hash"),
            amount=edge.get("amount"),
            timestamp=edge.get("timestamp"),
        )
    return graph


def _fetch_graph(address: str, depth: int = 2) -> Dict[str, Any]:
    if neo4j_store:
        raw = fetch_subgraph(neo4j_store._driver, address, depth=depth, database=neo4j_store._database)
        if not raw["nodes"]:
            raise HTTPException(status_code=404, detail="Address not found")
        return raw

    sub = subgraph_around(graph_cache, address, depth=depth)
    if sub.number_of_nodes() == 0:
        raise HTTPException(status_code=404, detail="Address not found")
    return serialize_graph(sub)


def _score_from_graph(address: str, graph_raw: Dict[str, Any]) -> Dict[str, Any]:
    graph = _graph_from_serialized(graph_raw)
    score = score_address(address, graph, None)
    return {
        "address": score.address,
        "score": score.score,
        "reasons": score.reasons,
        "flags": score.flags,
    }


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _require_nonce(headers: Dict[str, str]) -> None:
    if AUTH_MODE == "none":
        return
    nonce = headers.get("x-nonce")
    if not nonce:
        raise HTTPException(status_code=401, detail="Missing nonce header")
    now = time.time()
    if not _nonce_store.check_and_store(nonce, now):
        raise HTTPException(status_code=401, detail="Nonce replayed")


def _require_hmac(payload: Any, headers: Dict[str, str]) -> None:
    if AUTH_MODE != "hmac":
        return
    if not HMAC_SECRET:
        return
    ts = headers.get("x-timestamp")
    sig = headers.get("x-signature")
    if not ts or not sig:
        raise HTTPException(status_code=401, detail="Missing signature headers")
    try:
        ts_int = int(ts)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid timestamp")

    now = int(time.time())
    if abs(now - ts_int) > 300:
        raise HTTPException(status_code=401, detail="Signature expired")

    body = _canonical_json(payload)
    expected = hmac.new(
        HMAC_SECRET.encode("utf-8"),
        f"{ts}.{body}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")


def _require_jwt(headers: Dict[str, str]) -> None:
    if AUTH_MODE != "jwt":
        return
    auth = headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1]
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT secret not configured")
    try:
        kwargs = {
            "key": JWT_SECRET,
            "algorithms": ["HS256"],
            "options": {"require": ["exp"]},
        }
        if JWT_AUDIENCE:
            kwargs["audience"] = JWT_AUDIENCE
        if JWT_ISSUER:
            kwargs["issuer"] = JWT_ISSUER
        jwt.decode(token, **kwargs)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def _upsert_tx_in_memory(tx: Transaction) -> None:
    txs_cache.append(tx)
    graph_cache.add_node(tx.sender)
    graph_cache.add_node(tx.receiver)
    graph_cache.add_edge(
        tx.sender,
        tx.receiver,
        tx_hash=tx.tx_hash,
        amount=tx.amount,
        timestamp=tx.timestamp.isoformat(),
    )


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/graph/{address}")
def graph(address: str, depth: int = 2) -> Dict[str, Any]:
    return _fetch_graph(address, depth)


@app.get("/risk/{address}")
def risk(address: str) -> Dict[str, Any]:
    if neo4j_store:
        raw = fetch_subgraph(neo4j_store._driver, address, depth=2, database=neo4j_store._database)
        if not raw["nodes"]:
            raise HTTPException(status_code=404, detail="Address not found")
        return _score_from_graph(address, raw)

    if address not in graph_cache:
        raise HTTPException(status_code=404, detail="Address not found")
    score = score_address(address, graph_cache, txs_cache)
    return {
        "address": score.address,
        "score": score.score,
        "reasons": score.reasons,
        "flags": score.flags,
    }


@app.post("/events/tx")
async def ingest_tx(payload: TxEvent, request: Request) -> Dict[str, str]:
    headers = {k.lower(): v for k, v in request.headers.items()}
    _require_nonce(headers)
    _require_hmac(payload.model_dump(by_alias=True), headers)
    _require_jwt(headers)
    tx = Transaction.from_dict(
        {
            "tx_hash": payload.tx_hash,
            "from": payload.sender,
            "to": payload.receiver,
            "amount": payload.amount,
            "timestamp": payload.timestamp,
        }
    )
    if neo4j_store:
        neo4j_store.upsert_transaction(tx)
    else:
        _upsert_tx_in_memory(tx)

    asyncio.create_task(ws_manager.broadcast_updates())
    return {"status": "accepted"}


@app.post("/events/tx/batch")
async def ingest_tx_batch(payload: TxBatch, request: Request) -> Dict[str, Any]:
    headers = {k.lower(): v for k, v in request.headers.items()}
    _require_nonce(headers)
    _require_hmac(
        {"items": [item.model_dump(by_alias=True) for item in payload.items]},
        headers,
    )
    _require_jwt(headers)
    count = 0
    for item in payload.items:
        tx = Transaction.from_dict(
            {
                "tx_hash": item.tx_hash,
                "from": item.sender,
                "to": item.receiver,
                "amount": item.amount,
                "timestamp": item.timestamp,
            }
        )
        if neo4j_store:
            neo4j_store.upsert_transaction(tx)
        else:
            _upsert_tx_in_memory(tx)
        count += 1

    asyncio.create_task(ws_manager.broadcast_updates())
    return {"status": "accepted", "count": count}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        params = await ws.receive_json()
        address = params.get("address")
        depth = int(params.get("depth", 2))
        mode = params.get("mode", "push")
        interval = float(params.get("interval", 3.0))
        if not address:
            await ws.send_json({"error": "address required"})
            await ws.close()
            return

        try:
            graph_raw = _fetch_graph(address, depth)
            risk_raw = _score_from_graph(address, graph_raw)
            await ws.send_json({"graph": graph_raw, "risk": risk_raw})
        except HTTPException as exc:
            await ws.send_json({"error": exc.detail})
            await ws.close()
            return

        if mode == "poll":
            while True:
                await asyncio.sleep(interval)
                try:
                    graph_raw = _fetch_graph(address, depth)
                    risk_raw = _score_from_graph(address, graph_raw)
                    await ws.send_json({"graph": graph_raw, "risk": risk_raw})
                except HTTPException as exc:
                    await ws.send_json({"error": exc.detail})
                    await ws.close()
                    return
        else:
            await ws_manager.register(ws, address, depth)
            while True:
                await asyncio.sleep(30)
    except WebSocketDisconnect:
        await ws_manager.unregister(ws)
        return


@app.post("/cases", response_model=CaseResponse)
def create_case(payload: CaseRequest) -> CaseResponse:
    metadata_bytes = json.dumps(payload.metadata, sort_keys=True).encode("utf-8")
    metadata_hash = hashlib.sha256(metadata_bytes).hexdigest()
    return CaseResponse(case_id=payload.case_id, metadata_hash=metadata_hash, anchored=False)
