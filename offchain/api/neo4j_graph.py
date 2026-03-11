from __future__ import annotations

from typing import Dict, Any, List

from neo4j import Driver


def fetch_subgraph(driver: Driver, address: str, depth: int = 2, database: str | None = None) -> Dict[str, Any]:
    query = """
    MATCH p=(w:Wallet {address: $address})-[:TRANSFER*1..$depth]-(n:Wallet)
    RETURN p
    """
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[str, Dict[str, Any]] = {}

    with driver.session(database=database) as session:
        result = session.run(query, address=address, depth=depth)
        for record in result:
            path = record["p"]
            for node in path.nodes:
                addr = node.get("address")
                if addr:
                    nodes[addr] = {"id": addr}
            for rel in path.relationships:
                edge_id = rel.get("tx_hash") or f"{rel.start_node.get('address')}->{rel.end_node.get('address')}"
                edges[edge_id] = {
                    "source": rel.start_node.get("address"),
                    "target": rel.end_node.get("address"),
                    "tx_hash": rel.get("tx_hash"),
                    "amount": rel.get("amount"),
                    "timestamp": rel.get("timestamp"),
                }

    return {
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }
