"""Hashing, signed tokens, and rate limiting (same ideas as the Blind Trust code)."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import time
import warnings
from collections import defaultdict, deque


def _production_mode() -> bool:
    """Resolve the mode while preserving DEMO_MODE for existing demo setups."""
    mode = os.getenv("MAWID_ENV")
    demo_mode = os.getenv("DEMO_MODE")

    if demo_mode is not None and demo_mode.strip().lower() not in {"true", "false"}:
        raise RuntimeError("DEMO_MODE must be either 'true' or 'false'.")

    if mode is not None:
        mode = mode.strip().lower()
        if mode not in {"demo", "production"}:
            raise RuntimeError("MAWID_ENV must be either 'demo' or 'production'.")
        is_production = mode == "production"
        if demo_mode is not None and (demo_mode.strip().lower() == "true") == is_production:
            raise RuntimeError("MAWID_ENV and DEMO_MODE specify conflicting modes.")
        return is_production

    # Existing deployments that set DEMO_MODE=false are treated as production.
    return demo_mode is not None and demo_mode.strip().lower() == "false"


PRODUCTION_MODE = _production_mode()


def _secret(name: str) -> bytes:
    value = os.getenv(name, "").strip()
    if PRODUCTION_MODE:
        if not value:
            raise RuntimeError(f"{name} is required when Mawid runs in production.")
        if len(value) < 32 or value.startswith("dev-only-"):
            raise RuntimeError(f"{name} must be a unique random value of at least 32 characters in production.")
        return value.encode()

    if not value:
        warnings.warn(f"{name} is not set; using an insecure dev value. Set it in Replit Secrets.")
        value = f"dev-only-{name}"
    return value.encode()


HMAC_KEY = _secret("HMAC_KEY")             # hashing user identifiers
SIGNING_SECRET = _secret("SIGNING_SECRET") # signing session tokens

if PRODUCTION_MODE and HMAC_KEY == SIGNING_SECRET:
    raise RuntimeError("HMAC_KEY and SIGNING_SECRET must be different in production.")


def hash_id(raw: str) -> str:
    return hmac.new(HMAC_KEY, raw.encode(), hashlib.sha256).hexdigest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign_token(payload: dict, ttl_seconds: int = 60 * 60 * 24) -> str:
    body = dict(payload, exp=int(time.time()) + ttl_seconds)
    raw = _b64(json.dumps(body, separators=(",", ":")).encode())
    sig = _b64(hmac.new(SIGNING_SECRET, raw.encode(), hashlib.sha256).digest())
    return f"{raw}.{sig}"


def verify_token(token: str) -> dict | None:
    try:
        raw, sig = token.split(".")
        expected = _b64(hmac.new(SIGNING_SECRET, raw.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        body = json.loads(_unb64(raw))
        return body if body.get("exp", 0) > time.time() else None
    except Exception:
        return None


class RateLimiter:
    """Sliding window, in memory. Fine for one Replit instance."""
    def __init__(self, limit: int = 60, window: int = 60):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.time()
        q = self.hits[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True
