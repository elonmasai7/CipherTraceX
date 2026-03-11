# Fraud Tracing Prototype (Kadena + Off-Chain)

This is a minimal, runnable scaffold that includes:
- Kadena Pact contracts for fraud case registry, reports, and wallet attestations
- A single-chain off-chain indexer + graph builder
- A lightweight risk engine
- A FastAPI service with stubbed case creation and graph/risk endpoints

## Structure
- `contracts/fraud-registry.pact`
- `offchain/indexer/indexer.py`
- `offchain/indexer/graph_builder.py`
- `offchain/api/main.py`
- `offchain/api/risk_engine.py`
- `data/sample_txs.json`

## Quick Start
1. Install dependencies:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

2. Build the local sample graph:

```bash
python -m offchain.indexer.indexer
```

3. Run the API:

```bash
uvicorn offchain.api.main:app --reload --port 8000
```

4. Try endpoints:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/graph/0x222
curl http://localhost:8000/risk/0x222
```

## Ethereum RPC Indexer (Live Streaming)
This streams Ethereum blocks via RPC and writes transactions into Neo4j.

Required env:
- `ETH_RPC_URL` (e.g., `http://localhost:8545` or `wss://...`)
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, optional `NEO4J_DATABASE`

Run:

```bash
python -m offchain.indexer.eth_indexer --start-block 0 --poll-interval 3
```

## Neo4j-Backed Graph API
If `NEO4J_URI` is set, the API will query Neo4j instead of the local JSON graph.

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=changeme
uvicorn offchain.api.main:app --reload --port 8000
```

## Web UI
Open `http://localhost:8000/ui` after starting the API.
The UI uses `/ws` for live graph updates (push mode by default).

## Live Push Events
External indexers can push new transactions to `/events/tx` to trigger server-side broadcasts.
Auth is controlled by `API_AUTH_MODE`:
- `hmac` (default): requires `X-Nonce`, `X-Timestamp`, `X-Signature`
- `jwt`: requires `X-Nonce`, `Authorization: Bearer <token>`
- `none`: no auth

Replay protection:
- `X-Nonce` must be unique within `API_NONCE_TTL_SECONDS` (default 300s).
- For multi-instance deployments, set `API_REDIS_URL` (e.g., `redis://localhost:6379/0`) to store nonces in Redis.

HMAC details:
- `X-Timestamp`: unix seconds
- `X-Signature`: HMAC-SHA256 of `${timestamp}.${canonical_json}`
- Canonical JSON uses sorted keys and no spaces (`json.dumps(..., sort_keys=True, separators=(",", ":"))`).

JWT details:
- `API_JWT_SECRET` is required
- Optional `API_JWT_AUDIENCE`, `API_JWT_ISSUER`
- Token must include `exp`

Batch ingest:
- `POST /events/tx/batch` with body `{"items":[...]}` and the same auth scheme.

## Docker Compose
Includes Neo4j, API, and the Ethereum indexer.

```bash
docker compose up --build
```

Notes:
- Set `ETH_RPC_URL` in `docker-compose.yml` to your RPC endpoint.
- Neo4j UI available at `http://localhost:7474` (user: `neo4j`, password: `changeme`).
- Seed data is loaded from `neo4j/seed.cypher` by `neo4j-seed`.
- The indexer pushes new transactions to the API via `API_URL` for server-side broadcasts.

## Pact Tests
Requires `pact` CLI installed.

```bash
./scripts/pact-test.sh
```

## Pact Deploy (Local Devnet)
This script builds and signs a deploy command and submits it to a Chainweb node.

Required env:
- `KADENA_PUBLIC_KEY` (hex)
- `KADENA_SECRET_KEY` (hex seed)
- `KADENA_NODE` (default `http://localhost:8080`)
- `KADENA_NETWORK` (default `development`)
- `KADENA_CHAIN` (default `0`)

Run:

```bash
./scripts/pact-deploy.sh
```

## Notes
- The data is stubbed in `data/sample_txs.json`.
- The `POST /cases` endpoint simulates hash anchoring and returns a SHA-256 hash.
- The Pact contract uses an `admin-keyset` for governance.
