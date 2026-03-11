#!/usr/bin/env bash
set -euo pipefail

pact -r contracts/tests/fraud-registry.repl
