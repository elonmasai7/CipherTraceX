from __future__ import annotations

from datetime import timedelta, datetime
from typing import List, Dict, Optional

import networkx as nx

from offchain.common.models import Transaction, RiskScore


def _rapid_hops(txs: List[Transaction], address: str, max_gap_seconds: int = 120) -> bool:
    relevant = [tx for tx in txs if tx.sender == address or tx.receiver == address]
    relevant.sort(key=lambda tx: tx.timestamp)
    for i in range(1, len(relevant)):
        if (relevant[i].timestamp - relevant[i - 1].timestamp) <= timedelta(seconds=max_gap_seconds):
            return True
    return False


def _parse_ts(raw: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _rapid_hops_from_graph(graph: nx.DiGraph, address: str, max_gap_seconds: int = 120) -> bool:
    if address not in graph:
        return False
    timestamps = []
    for _, _, data in graph.out_edges(address, data=True):
        ts = data.get("timestamp")
        if ts:
            timestamps.append(ts)
    for _, _, data in graph.in_edges(address, data=True):
        ts = data.get("timestamp")
        if ts:
            timestamps.append(ts)
    parsed = []
    for ts in timestamps:
        parsed_ts = _parse_ts(ts)
        if parsed_ts:
            parsed.append(parsed_ts)
    parsed = sorted(parsed)
    if len(parsed) < 2:
        return False
    for i in range(1, len(parsed)):
        delta = (parsed[i] - parsed[i - 1]).total_seconds()
        if delta <= max_gap_seconds:
            return True
    return False


def _high_out_degree(graph: nx.DiGraph, address: str, threshold: int = 3) -> bool:
    if address not in graph:
        return False
    return graph.out_degree(address) >= threshold


def score_address(address: str, graph: nx.DiGraph, txs: Optional[List[Transaction]] = None) -> RiskScore:
    reasons: List[str] = []
    flags: List[str] = []
    score = 0.1

    if txs is not None and _rapid_hops(txs, address):
        score += 0.4
        reasons.append("Rapid hop activity detected")
        flags.append("rapid-hops")
    elif txs is None and _rapid_hops_from_graph(graph, address):
        score += 0.2
        reasons.append("Rapid hop activity detected (graph)")
        flags.append("rapid-hops")

    if _high_out_degree(graph, address):
        score += 0.3
        reasons.append("High out-degree fan-out")
        flags.append("fan-out")

    if score > 0.8:
        flags.append("high-risk")

    return RiskScore(address=address, score=min(score, 1.0), reasons=reasons, flags=flags)


def score_many(addresses: List[str], graph: nx.DiGraph, txs: List[Transaction]) -> Dict[str, RiskScore]:
    return {addr: score_address(addr, graph, txs) for addr in addresses}
