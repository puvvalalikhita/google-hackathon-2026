import os
from typing import Any, Dict, Optional

import httpx

from app.whatsapp_workflow import WHATSAPP_WORKFLOW


async def send_meta_whatsapp_message(to_phone: str, body: str) -> Dict[str, Any]:
    """
    Sends a real WhatsApp Cloud API message if WHATSAPP_ACCESS_TOKEN and
    WHATSAPP_PHONE_NUMBER_ID are configured; otherwise returns a simulated status.
    """
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    if not token or not phone_id or not to_phone:
        return {
            "sent_live": False,
            "mode": "SIMULATED_WHATSAPP_CARD",
            "to": to_phone or "Raju (+91-98110-XXXXX)",
        }

    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": body},
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            return {
                "sent_live": resp.is_success,
                "status_code": resp.status_code,
                "response": resp.text[:300],
            }
    except Exception as exc:
        return {"sent_live": False, "mode": "SIMULATED_WHATSAPP_CARD", "error": str(exc)}


async def process_whatsapp_voice_note(
    audio_bytes: Optional[bytes] = None,
    mime_type: str = "audio/webm",
    fallback_text: Optional[str] = None,
    driver_name: str = "Raju Kumar",
    sender_phone: str = "",
    image_bytes: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg",
    image_data_url: Optional[str] = None,
    active_store: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Processes an incoming WhatsApp Chat message, audio voice note, or photo proof
    through the stateful WhatsAppWorkflowEngine.
    """
    return await WHATSAPP_WORKFLOW.handle_message(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        fallback_text=fallback_text,
        driver_name=driver_name,
        sender_phone=sender_phone,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
        image_data_url=image_data_url,
        active_store=active_store,
        send_outbound_fn=send_meta_whatsapp_message,
    )
