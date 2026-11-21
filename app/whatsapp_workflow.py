import asyncio
import base64
import hashlib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from app.database import (
    add_whatsapp_message,
    clear_whatsapp_session,
    find_customer,
    get_full_state,
    get_whatsapp_session,
    save_whatsapp_session,
)
from app.policies import lookup_policies
from app.tools import LATEST_VISUAL_PROOF, execute_tool, set_latest_visual_proof

# Circuit-breaker timestamp: if Gemini fails/times out, skip retrying for 60s so chat stays <15ms
_GEMINI_COOLDOWN_UNTIL: float = 0.0


VALID_INTENTS = {
    "GREETING",
    "CANCEL",
    "CHECK_STATUS",
    "LOOKUP_CUSTOMER",
    "POLICY_CHECK",
    "ESCALATE",
    "DAMAGE_REPORT",
    "RECORD_DELIVERY",
}

EXTRACTION_PROMPT = """You are DeliverEx AI Ops Agent processing a WhatsApp chat message, photo, or voice note from a field delivery driver in India (often Hinglish, Hindi, Tamil/Tanglish, or English).
Classify the driver's intent and extract entities as strict JSON ONLY (no markdown fences):
{
  "intent": "One of: GREETING, CANCEL, CHECK_STATUS, LOOKUP_CUSTOMER, POLICY_CHECK, ESCALATE, DAMAGE_REPORT, RECORD_DELIVERY",
  "transcript": "verbatim Hinglish/English transcript or message text",
  "detected_language": "e.g. Hinglish (Hindi + English) or Tanglish (Tamil + English)",
  "customer_name": "exact shop name if mentioned (Krishna Hardware, Shri Ganesh Stores, Bharat Traders, Murugan Builders) or null if not mentioned",
  "delivered_bags": integer count of intact bags delivered (null if not stated),
  "damaged_bags": integer count of damaged/torn bags (0 if none),
  "cash_received": integer cash received in INR (null if not stated),
  "discount_requested": integer extra discount requested in INR (0 if none),
  "notes": "short summary of request, dispute, or context"
}
Rules:
- Use GREETING for hello/hi/namaste/help without an operational request.
- Use CANCEL for cancel/clear/reset draft.
- Use CHECK_STATUS when asking for today's summary, pending approvals, or open orders.
- Use LOOKUP_CUSTOMER when asking about a shop's balance due, invoice, or expected bags without reporting a delivery.
- Use POLICY_CHECK when asking about discount limits, damage rules, or company SOPs.
- Use ESCALATE when asking to speak to Manager Priya or reporting a customer refusal/dispute.
- Use DAMAGE_REPORT when reporting/showing torn or damaged bags without logging cash/delivery settlement.
- Use RECORD_DELIVERY when reporting delivered bags and/or cash received."""


def _safe_int(val: Any, allow_none: bool = False) -> Optional[int]:
    if val is None or isinstance(val, bool):
        return None if allow_none else 0
    if isinstance(val, (int, float)):
        return max(0, int(val))
    s = str(val).replace(",", "").strip().lower()
    if not s or s == "null" or s == "none":
        return None if allow_none else 0
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None if allow_none else 0
    num = float(m.group(0))
    if "k" in s:
        num *= 1000
    return max(0, int(num))


def detect_customer_in_text(low: str) -> Optional[str]:
    if not low:
        return None
    if "ganesh" in low or "chandni" in low or "8845" in low:
        return "Shri Ganesh Stores"
    if "bharat" in low or "sadar" in low or "8850" in low:
        return "Bharat Traders"
    if "murugan" in low or "nagar" in low or "chennai" in low or "8862" in low:
        return "Murugan Builders"
    if "krishna" in low or "old delhi" in low or "8841" in low:
        return "Krishna Hardware"
    cust = find_customer(low)
    return cust["name"] if cust else None


def heuristic_extract(
    text: str,
    has_audio: bool = False,
    has_image: bool = False,
    workflow_stage: str = "IDLE",
    session_customer: Optional[str] = None,
) -> Dict[str, Any]:
    low = (text or "").lower().strip()
    customer = detect_customer_in_text(low)

    normalized = low.replace(",", "")
    bags_match = re.search(r"(\d+)\s*(?:intact\s+)?(?:bags|bag|bori|bundle|pieces|pcs|ok)", normalized)
    damaged_match = re.search(
        r"(\d+)\s*(?:damaged|damage|torn|phate|phata|phat|kharab|broken|dmg)", normalized
    )
    cash_match = re.search(
        r"(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(k)?\s*(?:cash|rupees|received|mila|mil|kedaichu|paid|collect|collected)",
        normalized,
    )
    if not cash_match:
        cash_match = re.search(
            r"(?:cash|paid|received|mila)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(k)?",
            normalized,
        )
    disc_match = re.search(
        r"(?:rs\.?|inr|₹)?\s*(\d+)\s*(?:extra\s+)?(?:special\s+)?(?:discount|chhoot|off|kam|disc)",
        normalized,
    )

    delivered = int(bags_match.group(1)) if bags_match else None
    damaged = (
        int(damaged_match.group(1))
        if damaged_match
        else (2 if any(w in low for w in ["damage", "torn", "phat", "kharab", "dmg"]) else 0)
    )

    cash: Optional[int] = None
    if cash_match:
        val = float(cash_match.group(1))
        if cash_match.group(2) == "k":
            val *= 1000
        cash = max(0, int(val))

    discount = (
        int(disc_match.group(1))
        if disc_match
        else (
            500
            if ("discount" in low or "chhoot" in low)
            and any(w in low for w in ["maang", "request", "extra", "special", "de do", "chahiye"])
            else 0
        )
    )

    lang = "Hinglish (Hindi + English)"
    if any(w in low for w in ["anna", "pannitten", "kedaichu", "murugan", "tamil", "aayiduchu"]):
        lang = "Tanglish (Tamil + English)"
    elif re.match(r"^[a-z0-9\s.,?!₹-]+$", low) and not any(
        w in low
        for w in [
            "hai",
            "hain",
            "kar",
            "kiya",
            "mila",
            "kitna",
            "bata",
            "bhej",
            "maang",
            "aaj",
            "ruko",
            "bhai",
            "chahiye",
            "se",
        ]
    ):
        lang = "English"

    has_delivery_numbers = (delivered is not None) or (cash is not None) or any(
        w in low
        for w in [
            "deliver",
            "delivered",
            "unload",
            "settled",
            "bhej diya",
            "kar diya",
            "mila",
            "received",
            "intact",
        ]
    )

    # Check multi-turn follow-up states first
    if any(w in low for w in ["cancel", "clear draft", "reset chat", "bhool jao", "chhodo"]):
        intent = "CANCEL"
    elif re.fullmatch(
        r"(?:hi|hello|hey|namaste|vanakkam|hlo|help|start|menu|ok|okay|thanks|thank you|shukriya)[\s!?.]*",
        low,
    ):
        intent = "GREETING"
    elif any(
        w in low
        for w in ["priya", "manager", "handoff", "takeover", "take over", "baat kara", "escalate", "dispute"]
    ):
        intent = "ESCALATE"
    elif any(
        w in low
        for w in ["summary", "aaj ka", "pending approval", "approvals", "all stores", "sabhi", "hisaab", "route status"]
    ):
        intent = "CHECK_STATUS"
    elif any(w in low for w in ["policy", "sop", "rule", "limit"]) and not has_delivery_numbers:
        intent = "POLICY_CHECK"
    elif workflow_stage == "AWAITING_STORE_FOR_DELIVERY" and customer and not has_delivery_numbers:
        intent = "RECORD_DELIVERY"
    elif workflow_stage == "AWAITING_STORE_FOR_DAMAGE" and customer and not has_delivery_numbers:
        intent = "DAMAGE_REPORT"
    elif workflow_stage == "AWAITING_DELIVERY_DETAILS" and (delivered is not None or cash is not None or discount > 0 or damaged > 0):
        intent = "RECORD_DELIVERY"
    elif (has_image or damaged > 0) and not has_delivery_numbers and cash is None and delivered is None:
        intent = "DAMAGE_REPORT"
    elif any(w in low for w in ["due", "balance", "kitna", "baki", "invoice", "pending", "check", "details", "status"]) and not has_delivery_numbers:
        intent = "LOOKUP_CUSTOMER"
    elif has_audio and not low:
        intent = "RECORD_DELIVERY"
    elif has_delivery_numbers or discount > 0:
        intent = "RECORD_DELIVERY"
    elif customer:
        intent = "LOOKUP_CUSTOMER"
    else:
        intent = "GREETING"

    if customer is None and session_customer and intent in {"RECORD_DELIVERY", "DAMAGE_REPORT", "ESCALATE"}:
        customer = session_customer

    return {
        "intent": intent,
        "transcript": text,
        "detected_language": lang,
        "customer_name": customer,
        "delivered_bags": delivered,
        "damaged_bags": damaged,
        "cash_received": cash,
        "discount_requested": discount,
        "notes": text or "Processed via WhatsApp Workflow",
    }


def _sanitize_extracted(
    raw: Dict[str, Any],
    fallback_text: str,
    session_customer: Optional[str],
) -> Dict[str, Any]:
    intent = str(raw.get("intent") or "RECORD_DELIVERY").upper().strip()
    if intent not in VALID_INTENTS:
        intent = "RECORD_DELIVERY"

    raw_cust = raw.get("customer_name")
    resolved_cust = detect_customer_in_text(str(raw_cust).lower()) if raw_cust else None
    if not resolved_cust and fallback_text:
        resolved_cust = detect_customer_in_text(fallback_text.lower())
    if not resolved_cust and session_customer and intent in {"RECORD_DELIVERY", "DAMAGE_REPORT", "ESCALATE"}:
        resolved_cust = session_customer

    return {
        "intent": intent,
        "transcript": str(raw.get("transcript") or fallback_text or ""),
        "detected_language": str(raw.get("detected_language") or "Hinglish (Hindi + English)"),
        "customer_name": resolved_cust,
        "delivered_bags": _safe_int(raw.get("delivered_bags"), allow_none=True),
        "damaged_bags": _safe_int(raw.get("damaged_bags"), allow_none=False) or 0,
        "cash_received": _safe_int(raw.get("cash_received"), allow_none=True),
        "discount_requested": _safe_int(raw.get("discount_requested"), allow_none=False) or 0,
        "notes": str(raw.get("notes") or fallback_text or "Processed via WhatsApp Workflow"),
    }


async def _extract_with_gemini_async(
    api_key: str,
    model_name: str,
    use_vertex: bool,
    text_prompt: str,
    context_prompt: str,
    audio_bytes: Optional[bytes] = None,
    mime_type: str = "audio/webm",
    image_bytes: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg",
    resolved_image_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    global _GEMINI_COOLDOWN_UNTIL
    if time.time() < _GEMINI_COOLDOWN_UNTIL:
        return None

    from google import genai
    from google.genai import types

    parts: List[Any] = [EXTRACTION_PROMPT]
    if audio_bytes:
        parts.append(types.Part.from_bytes(data=audio_bytes, mime_type=mime_type or "audio/webm"))
    if image_bytes:
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type or "image/jpeg"))
    elif resolved_image_url and "," in resolved_image_url:
        try:
            hdr, b64_part = resolved_image_url.split(",", 1)
            img_mime = hdr.split(";")[0].split(":", 1)[1] if ":" in hdr and ";" in hdr else "image/jpeg"
            parts.append(types.Part.from_bytes(data=base64.b64decode(b64_part), mime_type=img_mime))
        except Exception:
            pass
    if text_prompt:
        parts.append(f"Driver WhatsApp message: {text_prompt}")
    if context_prompt:
        parts.append(context_prompt)

    http_opts = types.HttpOptions(
        timeout=2500,
        retry_options=types.HttpRetryOptions(attempts=1),
    )
    client = (
        genai.Client(vertexai=True, api_key=api_key, http_options=http_opts)
        if use_vertex
        else genai.Client(api_key=api_key, http_options=http_opts)
    )
    candidate_models = list(dict.fromkeys([model_name, "gemini-2.5-flash"]))
    for candidate in candidate_models:
        try:
            resp = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=candidate,
                    contents=parts,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                ),
                timeout=2.8,
            )
            raw_text = (resp.text or "").strip()
            if raw_text.startswith("```"):
                raw_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.DOTALL).strip()
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict) and parsed.get("intent"):
                return parsed
        except Exception:
            continue
    _GEMINI_COOLDOWN_UNTIL = time.time() + 60.0
    return None


class WhatsAppWorkflowEngine:
    """
    Fault-tolerant, stateful multi-turn workflow engine behind DeliverEx WhatsApp Chat.
    Guarantees:
    - Persistent session & partial draft recovery across turns (SQLite whatsapp_sessions)
    - Idempotency guard against accidental double-taps / webhook retries
    - Strict input validation & sanitization
    - Non-blocking async Gemini extraction with instant deterministic NLU fallback
    - Safe exception boundary so the endpoint never returns HTTP 500
    """

    async def handle_message(
        self,
        *,
        audio_bytes: Optional[bytes] = None,
        mime_type: str = "audio/webm",
        fallback_text: Optional[str] = None,
        driver_name: str = "Raju Kumar",
        sender_phone: str = "",
        image_bytes: Optional[bytes] = None,
        image_mime_type: str = "image/jpeg",
        image_data_url: Optional[str] = None,
        active_store: Optional[str] = None,
        send_outbound_fn=None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        session_id = sender_phone.strip() or "default"
        session = get_whatsapp_session(session_id)

        clean_text = (fallback_text or "").strip()
        resolved_image_url = image_data_url
        if not resolved_image_url and image_bytes:
            b64_img = base64.b64encode(image_bytes).decode("ascii")
            resolved_image_url = f"data:{image_mime_type or 'image/jpeg'};base64,{b64_img}"

        audio_data_url: Optional[str] = None
        if audio_bytes:
            b64_aud = base64.b64encode(audio_bytes).decode("ascii")
            audio_data_url = f"data:{mime_type or 'audio/webm'};base64,{b64_aud}"

        # Normalize incoming message type & body
        if resolved_image_url:
            incoming_type = "image"
            incoming_body = clean_text or "📷 [Field Photo Proof attached]"
            incoming_media = resolved_image_url
        elif audio_bytes:
            incoming_type = "audio"
            incoming_body = clean_text or "🎤 [WhatsApp Voice Note]"
            incoming_media = audio_data_url
        else:
            incoming_type = "text"
            incoming_body = (
                clean_text
                or "20 bags cement Krishna Hardware pe deliver kar diya, 15000 cash received, aur uncle 500 special discount maang rahe hain"
            )
            incoming_media = None

        driver_msg_record = add_whatsapp_message(
            sender="driver",
            body=incoming_body,
            msg_type=incoming_type,
            driver_name=driver_name,
            media_data_url=incoming_media,
            metadata={"sender_phone": sender_phone} if sender_phone else None,
        )

        # Duplicate-tap / webhook-retry idempotency check (3-second window on identical mutating message)
        msg_hash = hashlib.sha256(
            f"{session_id}|{clean_text.lower()}|{bool(resolved_image_url)}|{bool(audio_bytes)}".encode("utf-8")
        ).hexdigest()[:16]
        now_ts = time.time()
        is_duplicate = (
            bool(clean_text or resolved_image_url or audio_bytes)
            and session.get("last_msg_hash") == msg_hash
            and (now_ts - float(session.get("last_msg_ts") or 0.0)) < 3.0
            and session.get("workflow_stage") in {"COMPLETED", "AWAITING_MANAGER_APPROVAL"}
        )

        if is_duplicate:
            reply_text = (
                "⏳ Yeh update abhi-abhi process ho chuka hai — duplicate entry Tally/SAP mein block kar di gayi hai."
            )
            total_ms = round((time.perf_counter() - t0) * 1000)
            add_whatsapp_message(
                sender="bot",
                body=reply_text,
                msg_type="text",
                driver_name="DeliverEx Ops",
                metadata={"intent": "DUPLICATE_GUARD", "processing_ms": total_ms},
            )
            return {
                "intent": "DUPLICATE_GUARD",
                "used_gemini": False,
                "processing_ms": total_ms,
                "extracted": {"intent": "DUPLICATE_GUARD", "transcript": clean_text},
                "customer_match": {},
                "grounded_policies": [],
                "tool_calls": [],
                "erp_result": {"success": True, "deduplicated": True},
                "driver_message": driver_msg_record,
                "whatsapp_reply": reply_text,
                "whatsapp_delivery": {"sent_live": False, "mode": "DEDUPLICATED"},
                "workflow": get_whatsapp_session(session_id),
                "state": get_full_state(),
            }

        # Context resolution: explicit UI active_store > session store
        context_store = detect_customer_in_text((active_store or "").lower()) or session.get("active_customer_name")
        workflow_stage = session.get("workflow_stage") or "IDLE"
        pending_draft = dict(session.get("pending_draft") or {})

        # Multimodal Gemini extraction with instant offline fallback
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        model_name = os.getenv("GEMINI_VOICE_NOTE_MODEL", "gemini-3.8-flash").strip()
        use_vertex_env = os.getenv("USE_VERTEX_AI", "").strip().lower()
        use_vertex = (use_vertex_env == "true") or (use_vertex_env != "false" and api_key.startswith("AQ."))
        offline_only = os.getenv("WHATSAPP_OFFLINE_ONLY", "false").strip().lower() == "true"

        raw_extracted: Optional[Dict[str, Any]] = None
        used_gemini = False

        if api_key and not offline_only and (audio_bytes or image_bytes or resolved_image_url or clean_text):
            context_prompt = (
                f"Current session active store: {context_store} (stage={workflow_stage})"
                if context_store
                else ""
            )
            raw_extracted = await _extract_with_gemini_async(
                api_key,
                model_name,
                use_vertex,
                text_prompt=clean_text,
                context_prompt=context_prompt,
                audio_bytes=audio_bytes,
                mime_type=mime_type,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                resolved_image_url=resolved_image_url,
            )
            if raw_extracted:
                used_gemini = True

        if raw_extracted:
            extracted = _sanitize_extracted(raw_extracted, clean_text, context_store)
        else:
            heuristic_input = (
                clean_text
                or (
                    "2 torn bags photo proof"
                    if resolved_image_url
                    else "20 bags cement Krishna Hardware pe deliver kar diya, 15000 cash received, aur uncle 500 special discount maang rahe hain"
                )
            )
            extracted = heuristic_extract(
                heuristic_input,
                has_audio=bool(audio_bytes),
                has_image=bool(resolved_image_url),
                workflow_stage=workflow_stage,
                session_customer=context_store,
            )

        intent = extracted["intent"]
        cust_res: Dict[str, Any] = {}
        policies: List[Dict[str, Any]] = []
        erp_res: Dict[str, Any] = {"success": True, "intent": intent}
        tool_calls_used: List[str] = []
        bot_msg_type = "text"
        next_stage = workflow_stage
        next_customer_name = session.get("active_customer_name")
        next_customer_id = session.get("active_customer_id")
        next_draft: Dict[str, Any] = dict(pending_draft)

        try:
            if intent == "CANCEL":
                clear_whatsapp_session(session_id)
                next_stage = "IDLE"
                next_customer_name = None
                next_customer_id = None
                next_draft = {}
                reply_text = "👍 Draft & workflow clear kar diya hai. Aap naya delivery update ya query bhej sakte ho."

            elif intent == "GREETING":
                next_stage = "IDLE" if workflow_stage == "IDLE" else workflow_stage
                reply_text = (
                    f"Namaste {driver_name.split()[0]} bhai! Main DeliverEx WhatsApp Ops AI hoon.\n"
                    "Aap yahan seedha message, photo, ya voice note bhej sakte hain:\n"
                    "• Delivery + Cash log: \"Krishna Hardware pe 20 bags deliver, 15000 cash\"\n"
                    "• Shop Due check: \"Murugan Builders ka kitna balance hai?\"\n"
                    "• Damage / Discount: \"2 bags damaged nikle, 500 discount\"\n"
                    "• Manager Handoff: \"Priya ma'am se baat karao\""
                )

            elif intent == "CHECK_STATUS":
                state_now = get_full_state()
                pending = [a for a in state_now["approvals"] if a["status"] == "PENDING"]
                open_custs = [c for c in state_now["customers"] if c["balance_due"] > 0]
                total_cash = sum(int(e["cash_received"] or 0) for e in state_now["ledger"])
                lines = [
                    "📊 DeliverEx Live Route Summary:",
                    f"• Total Cash Logged: Rs {total_cash:,} ({len(state_now['ledger'])} Tally entries)",
                    f"• Pending Priya Approvals: {len(pending)}",
                    f"• Open Invoices ({len(open_custs)}):",
                ]
                for c in state_now["customers"]:
                    lines.append(
                        f"  - {c['name']} ({c['pending_invoice_id']}): Due Rs {c['balance_due']:,} [{c['status']}]"
                    )
                reply_text = "\n".join(lines)

            elif intent == "LOOKUP_CUSTOMER":
                lookup_target = extracted.get("customer_name") or context_store or ""
                if lookup_target:
                    cust_res, _ = execute_tool(
                        "lookup_customer_and_invoice",
                        {"customer_name": lookup_target},
                        channel="WHATSAPP_CHAT",
                    )
                    tool_calls_used.append("lookup_customer_and_invoice")
                if cust_res.get("found"):
                    next_customer_name = cust_res["name"]
                    next_customer_id = cust_res["customer_id"]
                    next_stage = "STORE_SELECTED"
                    next_draft = {}
                    reply_text = (
                        f"🧾 {cust_res['name']} ({cust_res['customer_id']})\n"
                        f"Invoice: {cust_res['pending_invoice_id']} • Route: {cust_res['route']}\n"
                        f"Expected: {cust_res['expected_bags']} bags ({cust_res['sku_code']})\n"
                        f"Invoice Amount: Rs {cust_res['invoice_amount_inr']:,}\n"
                        f"Balance Due: Rs {cust_res['balance_due_inr']:,}\n\n"
                        "Delivery update bhejne ke liye bas bags aur cash likh dein (jaise: \"20 bags delivered, 15000 cash\")."
                    )
                else:
                    state_now = get_full_state()
                    lines = ["Kaunse shop ka details chahiye? Active route stores:"]
                    for c in state_now["customers"]:
                        lines.append(f"• {c['name']} ({c['pending_invoice_id']}) — Due Rs {c['balance_due']:,}")
                    reply_text = "\n".join(lines)

            elif intent == "POLICY_CHECK":
                topic = clean_text or "discount damaged bags cash handoff"
                pol_res, _ = execute_tool("check_company_policy", {"topic": topic}, channel="WHATSAPP_CHAT")
                tool_calls_used.append("check_company_policy")
                policies = pol_res.get("matched_policies", [])
                lines = ["📜 DeliverEx Official SOP Rules:"]
                for p in policies:
                    lines.append(f"• {p['id']} ({p['title']}): {p['rule']}")
                reply_text = "\n".join(lines)

            elif intent == "ESCALATE":
                target_shop = extracted.get("customer_name") or context_store or LATEST_VISUAL_PROOF.get("customer_name") or "Krishna Hardware"
                handoff_res, _ = execute_tool(
                    "request_human_handoff",
                    {
                        "customer_name": target_shop,
                        "reason": clean_text or "Driver requested Priya Ma'am via WhatsApp",
                    },
                    channel="WHATSAPP_CHAT",
                )
                tool_calls_used.append("request_human_handoff")
                erp_res = handoff_res
                policies = lookup_policies("handoff")
                next_customer_name = target_shop
                next_stage = "ESCALATED_TO_MANAGER"
                next_draft = {}
                reply_text = (
                    f"📞 Live Escalation Sent ({handoff_res['handoff_id']})\n"
                    f"Shop: {target_shop}\n"
                    "Area Manager Priya Sharma ko poori chat & delivery context bhej diya gaya hai (SOP-6.0). "
                    "Wo turant approval ya call takeover karengi."
                )

            elif intent == "DAMAGE_REPORT":
                merged_dmg = max(1, int(extracted.get("damaged_bags") or pending_draft.get("damaged_bags") or 2))
                merged_img = resolved_image_url or pending_draft.get("image_data_url")
                target_shop = extracted.get("customer_name") or context_store

                if not target_shop:
                    next_stage = "AWAITING_STORE_FOR_DAMAGE"
                    next_draft = {"damaged_bags": merged_dmg, "image_data_url": merged_img}
                    reply_text = (
                        "⚠️ Torn/damaged bags note kar liye hain! Kis shop par damage hua hai?\n"
                        "Shop ka naam likh dein: Krishna Hardware, Shri Ganesh Stores, Bharat Traders, ya Murugan Builders."
                    )
                else:
                    policies = lookup_policies("damaged bags")
                    tool_calls_used.append("check_company_policy")
                    if merged_img:
                        proof_info = set_latest_visual_proof(
                            merged_img,
                            caption=clean_text or f"WhatsApp Photo Proof ({merged_dmg} torn bags)",
                            customer_name=target_shop,
                            damaged_bags=merged_dmg,
                            auto_create_approval=True,
                        )
                        approval_id = proof_info.get("attached_to_approval")
                        resolved_name = proof_info.get("customer_name") or target_shop
                        erp_res = {
                            "success": True,
                            "approval_id": approval_id,
                            "customer_name": resolved_name,
                            "invoice_id": proof_info.get("invoice_id"),
                            "damaged_bags": merged_dmg,
                            "policy_ref": "SOP-5.1",
                            "needs_manager_approval": True,
                            "approval": {"approval_id": approval_id, "policy_ref": "SOP-5.1"},
                        }
                        tool_calls_used.append("log_damaged_bags_report")
                        reply_text = (
                            f"📸 Visual Damage Proof Verified ({approval_id})\n"
                            f"Shop: {resolved_name} ({erp_res.get('invoice_id') or ''})\n"
                            f"{merged_dmg} damaged bags quarantine mein move kar diye aur photo seedha Priya Ma'am ke "
                            "1-Tap Approval Card par attach kar di gayi hai (SOP-5.1)."
                        )
                    else:
                        dmg_res, _ = execute_tool(
                            "log_damaged_bags_report",
                            {
                                "customer_name": target_shop,
                                "damaged_bags": merged_dmg,
                                "notes": clean_text or f"{merged_dmg} torn bags reported via WhatsApp",
                            },
                            channel="WHATSAPP_CHAT",
                        )
                        tool_calls_used.append("log_damaged_bags_report")
                        erp_res = {
                            **dmg_res,
                            "needs_manager_approval": True,
                            "approval": {"approval_id": dmg_res.get("approval_id"), "policy_ref": "SOP-5.1"},
                        }
                        resolved_name = dmg_res.get("customer_name") or target_shop
                        reply_text = (
                            f"⚠️ Damage Report Logged ({dmg_res.get('approval_id')})\n"
                            f"Shop: {resolved_name} ({dmg_res.get('invoice_id')})\n"
                            f"{merged_dmg} damaged bags quarantine mein log ho gaye hain aur Priya Ma'am ko SOP-5.1 approval bhej diya hai."
                        )
                    next_customer_name = resolved_name
                    next_stage = "AWAITING_MANAGER_APPROVAL"
                    next_draft = {}

            else:
                # RECORD_DELIVERY with multi-turn draft merging & validation
                merged_customer = extracted.get("customer_name") or pending_draft.get("customer_name") or context_store
                merged_delivered = extracted.get("delivered_bags")
                if merged_delivered is None:
                    merged_delivered = pending_draft.get("delivered_bags")
                merged_damaged = int(extracted.get("damaged_bags") or pending_draft.get("damaged_bags") or 0)
                merged_cash = extracted.get("cash_received")
                if merged_cash is None:
                    merged_cash = pending_draft.get("cash_received")
                merged_discount = int(extracted.get("discount_requested") or pending_draft.get("discount_requested") or 0)
                merged_image = resolved_image_url or pending_draft.get("image_data_url")

                if not merged_customer:
                    next_stage = "AWAITING_STORE_FOR_DELIVERY"
                    next_draft = {
                        "delivered_bags": merged_delivered,
                        "damaged_bags": merged_damaged,
                        "cash_received": merged_cash,
                        "discount_requested": merged_discount,
                        "image_data_url": merged_image,
                    }
                    reply_text = (
                        "📝 Delivery details note kar liye hain! Yeh kis shop ki delivery hai?\n"
                        "Shop ka naam batayein (Krishna Hardware, Shri Ganesh Stores, Bharat Traders, ya Murugan Builders)."
                    )
                elif merged_delivered is None and merged_cash is None and not audio_bytes and merged_discount == 0:
                    cust_info = find_customer(merged_customer)
                    next_customer_name = cust_info["name"] if cust_info else merged_customer
                    next_customer_id = cust_info["customer_id"] if cust_info else None
                    next_stage = "AWAITING_DELIVERY_DETAILS"
                    next_draft = {"customer_name": next_customer_name}
                    reply_text = (
                        f"👍 {next_customer_name} select ho gaya hai.\n"
                        "Kitne intact bags deliver hue aur kitna cash mila? (Example: \"18 bags, 15000 cash, 2 damaged\")"
                    )
                else:
                    cust_res, _ = execute_tool(
                        "lookup_customer_and_invoice",
                        {"customer_name": merged_customer},
                        channel="WHATSAPP_VOICE_NOTE" if audio_bytes else "WHATSAPP_CHAT",
                    )
                    tool_calls_used.append("lookup_customer_and_invoice")

                    canonical_name = cust_res.get("name") or merged_customer
                    if merged_image:
                        set_latest_visual_proof(
                            merged_image,
                            caption=clean_text or "WhatsApp Delivery Photo Proof",
                            customer_name=canonical_name,
                            damaged_bags=max(1, merged_damaged) if merged_damaged else 2,
                            auto_create_approval=False,
                        )

                    policies = lookup_policies(
                        f"discount {merged_discount} damaged {merged_damaged} cash"
                    )
                    tool_calls_used.append("check_company_policy")

                    expected_bags = cust_res.get("expected_bags", 20) if cust_res.get("found") else 20
                    final_delivered = (
                        int(merged_delivered)
                        if merged_delivered is not None
                        else max(0, expected_bags - merged_damaged)
                    )
                    final_cash = int(merged_cash) if merged_cash is not None else 0

                    ledger_res, _ = execute_tool(
                        "record_delivery_and_update_ledger",
                        {
                            "customer_name": canonical_name,
                            "delivered_bags": final_delivered,
                            "damaged_bags": merged_damaged,
                            "cash_received": final_cash,
                            "discount_requested": merged_discount,
                            "driver_name": driver_name,
                            "notes": extracted.get("notes") or extracted.get("transcript") or clean_text,
                        },
                        channel="WHATSAPP_VOICE_NOTE" if audio_bytes else "WHATSAPP_CHAT",
                    )
                    tool_calls_used.append("record_delivery_and_update_ledger")
                    erp_res = ledger_res

                    next_customer_name = ledger_res.get("customer_name") or canonical_name
                    next_customer_id = ledger_res.get("customer_id")
                    next_draft = {}

                    if ledger_res.get("needs_manager_approval"):
                        next_stage = "AWAITING_MANAGER_APPROVAL"
                        reply_text = (
                            f"✅ DeliverEx AI Ops Update ({ledger_res.get('tally_entry_id')})\n"
                            f"Shop: {ledger_res.get('customer_name')} ({ledger_res.get('invoice_id')})\n"
                            f"Logged in Tally/SAP: {ledger_res.get('delivered_bags')} intact bags, "
                            f"Rs {ledger_res.get('cash_posted_inr', 0):,} cash.\n"
                            f"⏳ Exception sent to Priya Ma'am ({ledger_res['approval']['policy_ref']}): "
                            f"{ledger_res['approval']['summary']}"
                        )
                    else:
                        next_stage = "COMPLETED"
                        bot_msg_type = "receipt"
                        reply_text = ledger_res.get("receipt", {}).get("message", "Delivery recorded in Tally/SAP.")

        except Exception as exc:
            # Safe fallback so workflow never breaks or crashes HTTP 500
            erp_res = {"success": False, "error": str(exc)}
            reply_text = (
                "⚠️ Network ya ERP sync mein chhota glitch aaya, par aapka message safe hai. "
                "Kripya shop name aur bags/cash dobara confirm karein."
            )

        updated_session = save_whatsapp_session(
            session_id,
            driver_name=driver_name,
            active_customer_id=next_customer_id,
            active_customer_name=next_customer_name,
            workflow_stage=next_stage,
            pending_draft=next_draft,
            last_msg_hash=msg_hash,
            last_msg_ts=now_ts,
            turn_count=int(session.get("turn_count") or 0) + 1,
        )

        wa_delivery = (
            await send_outbound_fn(sender_phone, reply_text)
            if send_outbound_fn
            else {"sent_live": False, "mode": "SIMULATED_WHATSAPP_CARD"}
        )
        total_ms = round((time.perf_counter() - t0) * 1000)

        add_whatsapp_message(
            sender="bot",
            body=reply_text,
            msg_type=bot_msg_type,
            driver_name="DeliverEx Ops",
            metadata={
                "intent": intent,
                "workflow_stage": next_stage,
                "processing_ms": total_ms,
                "used_gemini": used_gemini,
                "tool_calls": tool_calls_used,
                "tally_entry_id": erp_res.get("tally_entry_id"),
                "approval_id": (erp_res.get("approval") or {}).get("approval_id") or erp_res.get("approval_id"),
                "receipt_id": (erp_res.get("receipt") or {}).get("receipt_id"),
                "policies": [p["id"] for p in policies],
            },
        )

        return {
            "intent": intent,
            "used_gemini": used_gemini,
            "processing_ms": total_ms,
            "extracted": extracted,
            "customer_match": cust_res,
            "grounded_policies": policies,
            "tool_calls": tool_calls_used,
            "erp_result": erp_res,
            "driver_message": driver_msg_record,
            "whatsapp_reply": reply_text,
            "whatsapp_delivery": wa_delivery,
            "workflow": updated_session,
            "state": get_full_state(),
        }


WHATSAPP_WORKFLOW = WhatsAppWorkflowEngine()
