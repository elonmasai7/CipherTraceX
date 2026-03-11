from __future__ import annotations

import json
from pathlib import Path
from typing import List

from offchain.common.models import Transaction
from offchain.indexer.graph_builder import build_graph, serialize_graph

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TX_FILE = DATA_DIR / "sample_txs.json"
GRAPH_FILE = DATA_DIR / "graph.json"


def load_transactions() -> List[Transaction]:
    raw = json.loads(TX_FILE.read_text())
    return [Transaction.from_dict(item) for item in raw]


def main() -> None:
    txs = load_transactions()
    graph = build_graph(txs)
    GRAPH_FILE.write_text(json.dumps(serialize_graph(graph), indent=2))
    print(f"Wrote graph to {GRAPH_FILE}")


if __name__ == "__main__":
    main()
