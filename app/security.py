import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional

from fastapi import Header, HTTPException


def _auth_secret() -> str:
    return (
        os.getenv("AUTH_SECRET", "").strip()
        or os.getenv("ADMIN_API_KEY", "").strip()
        or "deliverex_dev_hmac_secret_2026"
    )


def get_owner_pin() -> str:
    return os.getenv("OWNER_PIN", "4242").strip() or "4242"


def is_manager_auth_enforced() -> bool:
    val = os.getenv("ENFORCE_MANAGER_AUTH", "").strip().lower()
    if val in {"true", "1", "yes"}:
        return True
    if val in {"false", "0", "no"}:
        return False
    return os.getenv("ENVIRONMENT", "development").strip().lower() == "production"


def issue_token(actor: str, role: str, ttl_seconds: int = 86400) -> str:
    payload = {
        "sub": actor,
        "role": role.upper(),
        "exp": int(time.time()) + ttl_seconds,
        "iat": int(time.time()),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(_auth_secret().encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def verify_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    try:
        b64, sig = token.strip().split(".", 1)
        expected = hmac.new(_auth_secret().encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        padded = b64 + "=" * (-len(b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def extract_bearer(authorization: Optional[str], x_owner_token: Optional[str]) -> Optional[str]:
    if x_owner_token and x_owner_token.strip():
        return x_owner_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def require_owner_session(
    authorization: Optional[str] = Header(default=None),
    x_owner_token: Optional[str] = Header(default=None),
    x_admin_key: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    admin_key = os.getenv("ADMIN_API_KEY", "").strip()
    if admin_key and x_admin_key and hmac.compare_digest(admin_key, x_admin_key.strip()):
        return {"sub": "Admin Key", "role": "OWNER", "auth": "admin_key"}

    tok = extract_bearer(authorization, x_owner_token)
    claims = verify_token(tok)
    if claims and claims.get("role") in {"OWNER", "MANAGER"}:
        return claims

    if not is_manager_auth_enforced():
        return {"sub": "Priya Sharma (Local Dev)", "role": "OWNER", "auth": "dev_bypass"}

    raise HTTPException(
        status_code=401,
        detail="Owner authentication required. Sign in with Manager PIN to approve, export, or inspect audit logs.",
    )


def compute_audit_hash(prev_hash: str, record: Dict[str, Any]) -> str:
    canonical = json.dumps(
        {
            "prev_hash": prev_hash,
            "audit_id": record.get("audit_id"),
            "timestamp": record.get("timestamp"),
            "actor": record.get("actor"),
            "role": record.get("role"),
            "action": record.get("action"),
            "target_id": record.get("target_id"),
            "summary": record.get("summary"),
            "before_json": record.get("before_json"),
            "after_json": record.get("after_json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_audit_chain(entries_asc: list[Dict[str, Any]]) -> bool:
    prev = "GENESIS"
    for item in entries_asc:
        stored_prev = item.get("prev_hash") or "GENESIS"
        if stored_prev != prev:
            return False
        expected = compute_audit_hash(prev, item)
        if item.get("integrity_hash") != expected:
            return False
        prev = expected
    return True
