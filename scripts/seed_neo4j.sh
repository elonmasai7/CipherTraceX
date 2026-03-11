#!/usr/bin/env bash
set -euo pipefail

BOLT_URL=${NEO4J_URI:-bolt://neo4j:7687}
USER=${NEO4J_USER:-neo4j}
PASS=${NEO4J_PASSWORD:-changeme}
SEED_FILE=${SEED_FILE:-/seed/seed.cypher}

for i in {1..30}; do
  if cypher-shell -a "$BOLT_URL" -u "$USER" -p "$PASS" "RETURN 1" >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [ "$i" -eq 30 ]; then
    echo "Neo4j not ready" >&2
    exit 1
  fi
done

cypher-shell -a "$BOLT_URL" -u "$USER" -p "$PASS" -f "$SEED_FILE"
