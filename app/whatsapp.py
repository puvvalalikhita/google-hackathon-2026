import json
import os
import time
from typing import Any, Dict, Optional

import httpx
from google import genai
from google.genai import types

from app.database import get_full_state
from app.policies import lookup_policies
from app.tools import execute_tool


EXTRACTION_PROMPT = """You are DeliverEx AI Ops Agent processing a WhatsApp voice note or text message from a field delivery driver in India (often Hinglish, Hindi, Tamil, or noisy wholesale market audio).
Extract the delivery update as strict JSON ONLY (no markdown fences) with these keys:
{
  "transcript": "verbatim Hinglish/English transcript of what the driver said",
  "detected_language": "e.g. Hinglish (Hindi + English)",
  "customer_name": "shop name mentioned, e.g. Krishna Hardware",
  "delivered_bags": integer count of intact bags delivered,
  "damaged_bags": integer count of damaged/torn bags (0 if none),
  "cash_received": integer cash received in INR (0 if none),
  "discount_requested": integer extra discount requested in INR (0 if none),
  "notes": "short summary of any special request or context"
}"""


async def send_meta_whatsapp_message(to_phone: str, body: str) -> Dict[str, Any]:
    """
    Sends a real WhatsApp Cloud API message if WHATSAPP_ACCESS_TOKEN and
    WHATSAPP_PHONE_NUMBER_ID are configured; otherwise returns a simulated status.
    """
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    if not token or not phone_id or not to_phone:
        return {"sent_live": False, "mode": "SIMULATED_WHATSAPP_CARD", "to": to_phone or "Raju (+91-98110-XXXXX)"}

    url = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": body},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        return {"sent_live": resp.is_success, "status_code": resp.status_code, "response": resp.text[:300]}


async def process_whatsapp_voice_note(
    audio_bytes: Optional[bytes] = None,
    mime_type: str = "audio/webm",
    fallback_text: Optional[str] = None,
    driver_name: str = "Raju Kumar",
    sender_phone: str = "",
) -> Dict[str, Any]:
    """
    Processes an async WhatsApp Voice Note (real audio bytes OR simulated Hinglish text)
    using Gemini multimodal audio understanding + DeliverEx ERP & policy tools.
    """
    t0 = time.perf_counter()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_VOICE_NOTE_MODEL", "gemini-3.8-flash").strip()
    use_vertex = os.getenv("USE_VERTEX_AI", "false").strip().lower() == "true"

    extracted: Dict[str, Any]
    used_gemini = False

    if api_key and (audio_bytes or fallback_text):
        client = (
            genai.Client(vertexai=True, api_key=api_key)
            if use_vertex
            else genai.Client(api_key=api_key)
        )
        parts = [EXTRACTION_PROMPT]
        if audio_bytes:
            parts.append(types.Part.from_bytes(data=audio_bytes, mime_type=mime_type))
        if fallback_text:
            parts.append(f"Driver message text: {fallback_text}")

        resp = client.models.generate_content(
            model=model_name,
            contents=parts,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        raw_text = (resp.text or "{}").strip()
        try:
            extracted = json.loads(raw_text)
        except json.JSONDecodeError:
            extracted = _heuristic_extract(fallback_text or raw_text)
        used_gemini = True
    else:
        extracted = _heuristic_extract(
            fallback_text
            or "20 bags cement Krishna Hardware pe deliver kar diya, 15000 cash received, aur uncle 500 special discount maang rahe hain"
        )

    # 1. Lookup customer & policies
    cust_res, _ = execute_tool(
        "lookup_customer_and_invoice",
        {"customer_name": extracted.get("customer_name", "Krishna Hardware")},
        channel="WHATSAPP_VOICE_NOTE",
    )
    policies = lookup_policies(
        f"discount {extracted.get('discount_requested', 0)} damaged {extracted.get('damaged_bags', 0)} cash"
    )

    # 2. Execute real Tally/SAP ledger + inventory + Priya approval routing
    ledger_res, ledger_meta = execute_tool(
        "record_delivery_and_update_ledger",
        {
            "customer_name": extracted.get("customer_name", "Krishna Hardware"),
            "delivered_bags": extracted.get("delivered_bags", 20),
            "damaged_bags": extracted.get("damaged_bags", 0),
            "cash_received": extracted.get("cash_received", 15000),
            "discount_requested": extracted.get("discount_requested", 0),
            "driver_name": driver_name,
            "notes": extracted.get("notes") or extracted.get("transcript", ""),
        },
        channel="WHATSAPP_VOICE_NOTE",
    )

    # 3. Compose WhatsApp reply
    if ledger_res.get("needs_manager_approval"):
        reply_text = (
            f"✅ DeliverEx AI Ops Update ({ledger_res.get('tally_entry_id')})\n"
            f"Shop: {ledger_res.get('customer_name')} ({ledger_res.get('invoice_id')})\n"
            f"Logged in Tally/SAP: {ledger_res.get('delivered_bags')} intact bags, Rs {ledger_res.get('cash_posted_inr', 0):,} cash.\n"
            f"⏳ Exception sent to Priya Ma'am ({ledger_res['approval']['policy_ref']}): {ledger_res['approval']['summary']}"
        )
    else:
        reply_text = ledger_res.get("receipt", {}).get("message", "Delivery recorded in Tally/SAP.")

    wa_delivery = await send_meta_whatsapp_message(sender_phone, reply_text)
    total_ms = round((time.perf_counter() - t0) * 1000)

    return {
        "used_gemini": used_gemini,
        "processing_ms": total_ms,
        "extracted": extracted,
        "customer_match": cust_res,
        "grounded_policies": policies,
        "erp_result": ledger_res,
        "whatsapp_reply": reply_text,
        "whatsapp_delivery": wa_delivery,
        "state": get_full_state(),
    }


def _heuristic_extract(text: str) -> Dict[str, Any]:
    import re

    low = text.lower()
    customer = "Krishna Hardware"
    if "ganesh" in low:
        customer = "Shri Ganesh Stores"
    elif "bharat" in low:
        customer = "Bharat Traders"
    elif "murugan" in low:
        customer = "Murugan Builders"

    bags_match = re.search(r"(\d+)\s*(?:bags|bag|bori|bundle)", low)
    damaged_match = re.search(r"(\d+)\s*(?:damaged|damage|phate|phata|torn|kharab)", low)
    cash_match = re.search(r"(?:rs\.?|₹)?\s*(\d{4,6})\s*(?:cash|rupees|received|mila|mil)", low)
    disc_match = re.search(r"(?:rs\.?|₹)?\s*(\d{2,4})\s*(?:extra\s+)?(?:special\s+)?(?:discount|chhoot)", low)

    delivered = int(bags_match.group(1)) if bags_match else 18
    damaged = int(damaged_match.group(1)) if damaged_match else (2 if "damage" in low or "phat" in low else 0)
    cash = int(cash_match.group(1)) if cash_match else 15000
    discount = int(disc_match.group(1)) if disc_match else (500 if "discount" in low or "chhoot" in low else 0)

    return {
        "transcript": text,
        "detected_language": "Hinglish (Hindi + English)",
        "customer_name": customer,
        "delivered_bags": delivered,
        "damaged_bags": damaged,
        "cash_received": cash,
        "discount_requested": discount,
        "notes": "Processed via WhatsApp Voice Note workflow",
    }
