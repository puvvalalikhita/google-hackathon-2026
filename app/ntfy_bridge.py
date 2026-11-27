"""
Open-source WhatsApp alternative messaging & push bridge powered by ntfy
(https://github.com/binwiederhier/ntfy — Apache-2.0 / GPLv2).

Dispatches official delivery receipts, Tally/CSV ledgers, manager approvals,
and Android app update alerts over simple HTTPS pub-sub without Meta/WhatsApp fees.
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
    headers: Dict[str, str] = {
        "Title": title[:120],
        "Priority": priority,
        "Tags": ",".join(tags or ["truck", "raju-bhai"]),
    }
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    if click_url:
        headers["Click"] = click_url
    if attach_url:
        headers["Attach"] = attach_url
    if actions:
        headers["Actions"] = actions

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                cfg["topic_url"],
                content=message.encode("utf-8"),
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
