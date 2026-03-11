CREATE CONSTRAINT wallet_address IF NOT EXISTS FOR (w:Wallet) REQUIRE w.address IS UNIQUE;

MERGE (a:Wallet {address: '0x111'})
MERGE (b:Wallet {address: '0x222'})
MERGE (c:Wallet {address: '0x333'})
MERGE (d:Wallet {address: '0x444'})

MERGE (a)-[t1:TRANSFER {tx_hash: 'seed-1'}]->(b)
SET t1.amount = 5.2, t1.timestamp = '2026-03-09T10:01:00Z'

MERGE (b)-[t2:TRANSFER {tx_hash: 'seed-2'}]->(c)
SET t2.amount = 5.1, t2.timestamp = '2026-03-09T10:02:10Z'

MERGE (c)-[t3:TRANSFER {tx_hash: 'seed-3'}]->(d)
SET t3.amount = 5.0, t3.timestamp = '2026-03-09T10:02:55Z'
