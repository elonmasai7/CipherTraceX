from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timezone

import hashlib
import hmac
import json
import secrets
import jwt
import requests
from web3 import Web3, HTTPProvider, WebsocketProvider

from offchain.common.models import Transaction
from offchain.indexer.neo4j_store import from_env


def _build_web3(rpc_url: str) -> Web3:
    if rpc_url.startswith("ws"):
        return Web3(WebsocketProvider(rpc_url))
    return Web3(HTTPProvider(rpc_url))


def index_block(w3: Web3, block_number: int, store) -> int:
    block = w3.eth.get_block(block_number, full_transactions=True)
    api_url = os.getenv("API_URL")
    hmac_secret = os.getenv("API_HMAC_SECRET")
    jwt_secret = os.getenv("API_JWT_SECRET")
    jwt_aud = os.getenv("API_JWT_AUDIENCE")
    jwt_iss = os.getenv("API_JWT_ISSUER")
    for tx in block.transactions:
        timestamp = datetime.fromtimestamp(block.timestamp, tz=timezone.utc)
        transaction = Transaction(
            tx_hash=tx.hash.hex(),
            sender=tx["from"],
            receiver=tx.get("to") or "",
            amount=float(Web3.from_wei(tx["value"], "ether")),
            timestamp=timestamp,
        )
        if store:
            store.upsert_transaction(transaction)
        if api_url:
            try:
                payload = {
                    "tx_hash": transaction.tx_hash,
                    "from": transaction.sender,
                    "to": transaction.receiver,
                    "amount": transaction.amount,
                    "timestamp": transaction.timestamp.isoformat(),
                }
                headers = {}
                nonce = secrets.token_hex(16)
                headers["X-Nonce"] = nonce
                if hmac_secret:
                    ts = str(int(time.time()))
                    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                    sig = hmac.new(
                        hmac_secret.encode("utf-8"),
                        f"{ts}.{body}".encode("utf-8"),
                        hashlib.sha256,
                    ).hexdigest()
                    headers["X-Timestamp"] = ts
                    headers["X-Signature"] = sig
                if jwt_secret:
                    claims = {
                        "sub": "eth-indexer",
                        "iat": int(time.time()),
                        "exp": int(time.time()) + 300,
                    }
                    if jwt_aud:
                        claims["aud"] = jwt_aud
                    if jwt_iss:
                        claims["iss"] = jwt_iss
                    token = jwt.encode(claims, jwt_secret, algorithm="HS256")
                    headers["Authorization"] = f"Bearer {token}"
                requests.post(
                    f"{api_url.rstrip('/')}/events/tx",
                    json=payload,
                    headers=headers,
                    timeout=2,
                )
            except requests.RequestException:
                pass
    return len(block.transactions)


def follow_chain(w3: Web3, start_block: int, poll_interval: float, store) -> None:
    current = start_block
    while True:
        latest = w3.eth.block_number
        while current <= latest:
            count = index_block(w3, current, store)
            print(f"Indexed block {current} ({count} tx)")
            current += 1
        time.sleep(poll_interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ethereum RPC indexer with Neo4j sink")
    parser.add_argument("--rpc", default=os.getenv("ETH_RPC_URL", "http://localhost:8545"))
    parser.add_argument("--start-block", type=int, default=0)
    parser.add_argument("--poll-interval", type=float, default=3.0)
    args = parser.parse_args()

    w3 = _build_web3(args.rpc)
    if not w3.is_connected():
        raise SystemExit("Failed to connect to Ethereum RPC")

    store = from_env()
    if not store:
        print("Neo4j not configured; set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD")

    follow_chain(w3, args.start_block, args.poll_interval, store)


if __name__ == "__main__":
    main()
