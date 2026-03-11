from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, Any

import requests
from nacl.signing import SigningKey


def blake2b_256(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=32).hexdigest()


def sign_hash(hash_hex: str, secret_hex: str) -> str:
    signing_key = SigningKey(bytes.fromhex(secret_hex))
    signature = signing_key.sign(bytes.fromhex(hash_hex)).signature
    return signature.hex()


def build_command(code: str, public_key: str, chain_id: str, network_id: str) -> Dict[str, Any]:
    cmd = {
        "networkId": network_id,
        "payload": {
            "exec": {
                "code": code,
                "data": {
                    "admin-keyset": {"keys": [public_key], "pred": "keys-all"}
                },
            }
        },
        "signers": [
            {
                "pubKey": public_key,
                "caps": [],
            }
        ],
        "meta": {
            "chainId": chain_id,
            "sender": public_key,
            "gasLimit": int(os.getenv("GAS_LIMIT", "1000")),
            "gasPrice": float(os.getenv("GAS_PRICE", "1e-8")),
            "ttl": int(os.getenv("TTL", "28800")),
            "creationTime": int(time.time()),
        },
        "nonce": f"deploy-fraud-registry-{int(time.time())}",
    }
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy Pact module to a Chainweb node")
    parser.add_argument("--node", default=os.getenv("KADENA_NODE", "http://localhost:8080"))
    parser.add_argument("--network", default=os.getenv("KADENA_NETWORK", "development"))
    parser.add_argument("--chain", default=os.getenv("KADENA_CHAIN", "0"))
    parser.add_argument("--code", default=str(Path("contracts/fraud-registry.pact")))
    parser.add_argument("--local-only", action="store_true")
    args = parser.parse_args()

    public_key = os.getenv("KADENA_PUBLIC_KEY")
    secret_key = os.getenv("KADENA_SECRET_KEY")
    if not public_key or not secret_key:
        raise SystemExit("Set KADENA_PUBLIC_KEY and KADENA_SECRET_KEY (hex-encoded)")

    code = Path(args.code).read_text()
    cmd = build_command(code, public_key, args.chain, args.network)
    cmd_json = json.dumps(cmd, separators=(",", ":"))
    cmd_hash = blake2b_256(cmd_json.encode("utf-8"))
    sig = sign_hash(cmd_hash, secret_key)

    payload = {
        "cmds": [
            {
                "hash": cmd_hash,
                "sigs": [{"sig": sig}],
                "cmd": cmd_json,
            }
        ]
    }

    local_url = f"{args.node}/pact/api/v1/local"
    send_url = f"{args.node}/pact/api/v1/send"

    local_resp = requests.post(local_url, json=payload["cmds"][0]).json()
    print("Local response:")
    print(json.dumps(local_resp, indent=2))

    if args.local_only:
        return

    send_resp = requests.post(send_url, json=payload).json()
    print("Send response:")
    print(json.dumps(send_resp, indent=2))


if __name__ == "__main__":
    main()
