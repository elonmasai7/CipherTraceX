import importlib
import sys
import time

from fastapi import HTTPException


def _load_app(monkeypatch, **env):
    for key in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE", "API_REDIS_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop("offchain.api.main", None)
    module = importlib.import_module("offchain.api.main")
    return module


BASE_TX = {
    "tx_hash": "0xabc",
    "from": "0x111",
    "to": "0x222",
    "amount": 1.5,
    "timestamp": "2024-01-01T00:00:00Z",
}


def test_hmac_missing_signature_headers_rejected(monkeypatch):
    module = _load_app(
        monkeypatch,
        API_AUTH_MODE="hmac",
        API_HMAC_SECRET="test-secret",
        API_NONCE_TTL_SECONDS="300",
    )
    try:
        module._require_hmac(BASE_TX, {"x-nonce": "nonce-1"})
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "Missing signature headers"
    else:
        raise AssertionError("Expected HTTPException for missing signature headers")


def test_nonce_replay_rejected(monkeypatch):
    module = _load_app(
        monkeypatch,
        API_AUTH_MODE="hmac",
        API_HMAC_SECRET="test-secret",
        API_NONCE_TTL_SECONDS="300",
    )
    headers = {"x-nonce": "nonce-replay"}
    module._require_nonce(headers)
    try:
        module._require_nonce(headers)
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail == "Nonce replayed"
    else:
        raise AssertionError("Expected HTTPException for nonce replay")


def test_redis_nonce_store_replay_detected(monkeypatch):
    module = _load_app(
        monkeypatch,
        API_AUTH_MODE="hmac",
        API_HMAC_SECRET="test-secret",
        API_NONCE_TTL_SECONDS="300",
    )

    class FakeRedis:
        def __init__(self):
            self.store = {}

        def set(self, name, value, nx, ex):  # noqa: ARG002 - signature matches redis client
            if nx and name in self.store:
                return None
            self.store[name] = value
            return True

    store = module.RedisNonceStore(FakeRedis(), 300)
    now = time.time()
    assert store.check_and_store("nonce-redis", now) is True
    assert store.check_and_store("nonce-redis", now) is False
