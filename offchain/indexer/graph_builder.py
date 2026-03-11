from __future__ import annotations

from typing import Iterable, Dict, Any, List

import networkx as nx

from offchain.common.models import Transaction, GraphEdge


def build_graph(txs: Iterable[Transaction]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for tx in txs:
        graph.add_node(tx.sender)
        graph.add_node(tx.receiver)
        graph.add_edge(
            tx.sender,
            tx.receiver,
            tx_hash=tx.tx_hash,
            amount=tx.amount,
            timestamp=tx.timestamp.isoformat(),
        )
    return graph


def serialize_graph(graph: nx.DiGraph) -> Dict[str, Any]:
    nodes = [{"id": node} for node in graph.nodes()]
    edges: List[GraphEdge] = []
    for source, target, data in graph.edges(data=True):
        edges.append(
            GraphEdge(
                source=source,
                target=target,
                tx_hash=data.get("tx_hash", ""),
                amount=float(data.get("amount", 0.0)),
                timestamp=data.get("timestamp", ""),
            )
        )
    return {
        "nodes": nodes,
        "edges": [edge.__dict__ for edge in edges],
    }


def subgraph_around(graph: nx.DiGraph, address: str, depth: int = 2) -> nx.DiGraph:
    if address not in graph:
        return nx.DiGraph()

    frontier = {address}
    visited = {address}
    for _ in range(depth):
        next_frontier = set()
        for node in frontier:
            next_frontier.update(graph.predecessors(node))
            next_frontier.update(graph.successors(node))
        next_frontier -= visited
        visited |= next_frontier
        frontier = next_frontier

    return graph.subgraph(visited).copy()
