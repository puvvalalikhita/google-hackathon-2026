"""
Open-source WhatsApp alternative messaging & push bridge powered by ntfy
(https://github.com/binwiederhier/ntfy — Apache-2.0 / GPLv2).

Dispatches official delivery receipts, Tally/CSV ledgers, manager approvals,
and Android app update alerts over simple HTTPS JSON pub-sub without Meta/WhatsApp fees.
"""
import os
from typing import Any, Dict, List, Optional

import httpx


def get_ntfy_config() -> Dict[str, str]:
    server = os.getenv("NTFY_SERVER_URL", "https://ntfy.sh").strip().rstrip("/")
    topic = os.getenv("NTFY_TOPIC", "rajubhai-ops-353183969363").strip().strip("/")
    token = os.getenv("NTFY_TOKEN", "").strip()
    return {
        "server": server or "https://ntfy.sh",
        "topic": topic or "rajubhai-ops-353183969363",
        "token": token,
        "topic_url": f"{server or 'https://ntfy.sh'}/{topic or 'rajubhai-ops-353183969363'}",
    }


_PRIORITY_MAP = {
    "min": 1,
    "low": 2,
    "default": 3,
    "high": 4,
    "urgent": 5,
    "max": 5,
}


async def publish_ntfy_message(
    *,
    title: str,
    message: str,
    tags: Optional[List[str]] = None,
    priority: str = "high",
    click_url: Optional[str] = None,
    attach_url: Optional[str] = None,
    actions: Optional[str] = None,
) -> Dict[str, Any]:
    cfg = get_ntfy_config()
    headers: Dict[str, str] = {"Content-Type": "application/json; charset=utf-8"}
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"

    payload: Dict[str, Any] = {
        "topic": cfg["topic"],
        "title": title[:120],
        "message": message,
        "priority": _PRIORITY_MAP.get(priority.lower(), 4),
        "tags": tags or ["truck", "raju-bhai"],
    }
    if click_url:
        payload["click"] = click_url
    if attach_url:
        payload["attach"] = attach_url

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                cfg["server"],
                json=payload,
                headers=headers,
            )
            return {
                "ok": resp.is_success,
                "status_code": resp.status_code,
                "provider": "ntfy (github.com/binwiederhier/ntfy)",
                "topic": cfg["topic"],
                "topic_url": cfg["topic_url"],
            }
    except Exception as exc:
        return {
            "ok": False,
            "provider": "ntfy (github.com/binwiederhier/ntfy)",
            "topic": cfg["topic"],
            "error": str(exc),
        }
