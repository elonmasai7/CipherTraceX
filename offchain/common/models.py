from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any


@dataclass
class Transaction:
    tx_hash: str
    sender: str
    receiver: str
    amount: float
    timestamp: datetime

    @staticmethod
    def from_dict(raw: Dict[str, Any]) -> "Transaction":
        return Transaction(
            tx_hash=raw["tx_hash"],
            sender=raw["from"],
            receiver=raw["to"],
            amount=float(raw["amount"]),
            timestamp=datetime.fromisoformat(raw["timestamp"].replace("Z", "+00:00")),
        )


@dataclass
class GraphEdge:
    source: str
    target: str
    tx_hash: str
    amount: float
    timestamp: str


@dataclass
class RiskScore:
    address: str
    score: float
    reasons: List[str]
    flags: List[str]
