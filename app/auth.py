"""API key issuance + validation (Phase 3 / T7). Identity model (a): email + API key.

Gating is OFF by default (settings.require_api_key) so the studio keeps working without keys.
When ON, work endpoints require a valid X-API-Key header, enforce a monthly quota, and record usage.
"""
import hashlib
import secrets
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import Header, HTTPException
from app.config import settings
from app.services.database_service import DatabaseService

_db = DatabaseService()


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_api_key() -> Dict[str, str]:
    """New raw key + its sha256 hash + a display prefix. The raw key is returned once, never stored."""
    raw = "la_" + secrets.token_hex(24)  # "la_" + 48 hex chars
    return {"raw": raw, "key_hash": hash_key(raw), "prefix": raw[:10]}


async def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> Optional[Dict[str, Any]]:
    """FastAPI dependency. No-op when REQUIRE_API_KEY is off. When on: validate key,
    enforce monthly quota, record usage. Returns {user_id, key_id} or raises 401/429."""
    if not settings.require_api_key:
        return None
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key. Send it in the X-API-Key header.")
    rec = await _db.get_api_key_by_hash(hash_key(x_api_key))
    if not rec or rec.get("revoked"):
        raise HTTPException(status_code=401, detail="Invalid or revoked API key.")
    user_id = rec.get("user_id")
    period = datetime.utcnow().strftime("%Y-%m")
    used = await _db.get_usage(user_id, period)
    if used >= settings.monthly_quota:
        raise HTTPException(status_code=429, detail=f"Monthly quota exceeded ({used}/{settings.monthly_quota}).")
    await _db.increment_usage(user_id, period, 1)
    await _db.touch_api_key(rec["id"])
    return {"user_id": user_id, "key_id": rec["id"]}
