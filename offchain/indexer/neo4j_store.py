from __future__ import annotations

import os
from typing import Optional

from neo4j import GraphDatabase, Driver

from offchain.common.models import Transaction


class Neo4jStore:
    def __init__(self, uri: str, user: str, password: str, database: Optional[str] = None) -> None:
        self._driver: Driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database

    def close(self) -> None:
        self._driver.close()

    def ensure_constraints(self) -> None:
        cypher = "CREATE CONSTRAINT wallet_address IF NOT EXISTS FOR (w:Wallet) REQUIRE w.address IS UNIQUE"
        with self._driver.session(database=self._database) as session:
            session.run(cypher)

    def upsert_transaction(self, tx: Transaction) -> None:
        cypher = """
        MERGE (sender:Wallet {address: $sender})
        MERGE (receiver:Wallet {address: $receiver})
        MERGE (sender)-[t:TRANSFER {tx_hash: $tx_hash}]->(receiver)
        SET t.amount = $amount,
            t.timestamp = $timestamp
        """
        with self._driver.session(database=self._database) as session:
            session.run(
                cypher,
                sender=tx.sender,
                receiver=tx.receiver,
                tx_hash=tx.tx_hash,
                amount=tx.amount,
                timestamp=tx.timestamp.isoformat(),
            )


def from_env() -> Optional[Neo4jStore]:
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    database = os.getenv("NEO4J_DATABASE")
    if not uri or not user or not password:
        return None
    store = Neo4jStore(uri=uri, user=user, password=password, database=database)
    store.ensure_constraints()
    return store
