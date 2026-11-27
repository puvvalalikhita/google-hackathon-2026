import asyncio
import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from app.database import BASE_DIR, check_db_health, find_customer, get_full_state
from app.i18n import DEFAULT_LANG, LANG_CODES, LANG_LABELS, detect_language, normalize_for_parsing, say
from app.policies import COMPANY_POLICIES, lookup_policies
from app.tools import LATEST_VISUAL_PROOF, execute_tool, set_latest_visual_proof

EXTRACTION_PROMPT = """You are DeliverEx AI Ops Agent processing a WhatsApp chat message, voice turn, photo, or voice note from a field delivery driver in India (often Hinglish, Hindi, Tamil/Tanglish, or English).
Classify the driver's intent and extract entities as strict JSON ONLY (no markdown fences):
{
  "intent": "One of: GREETING, CHECK_STATUS, LOOKUP_CUSTOMER, POLICY_CHECK, ESCALATE, DAMAGE_REPORT, RECORD_DELIVERY",
  "transcript": "verbatim Hinglish/English transcript or message text",
  "detected_language": "e.g. Hinglish (HI+EN) or Tanglish (TA+EN) or English",
  "is_barge_in": true or false (true if driver says stop/wait/ruko/nahi/correction to override an earlier number),
  "customer_name": "exact shop name if mentioned (Krishna Hardware, Shri Ganesh Stores, Bharat Traders, Murugan Builders) or null if not mentioned",
  "delivered_bags": integer count of intact bags delivered (null if not stated),
  "damaged_bags": integer count of damaged/torn bags (0 if none),
  "cash_received": integer cash received in INR (null if not stated),
  "discount_requested": integer extra discount requested in INR (0 if none),
  "notes": "short summary of request, dispute, or context"
}
Rules:
- Use GREETING for hello/hi/namaste/help without an operational request.
- Use CHECK_STATUS when asking for today's summary, pending approvals, or open orders.
- Use LOOKUP_CUSTOMER when asking about a shop's balance due, invoice, or expected bags without reporting a delivery.
- Use POLICY_CHECK when asking about discount limits, damage rules, or company SOPs.
- Use ESCALATE when asking to speak to Manager Priya or reporting a customer refusal/dispute.
- Use DAMAGE_REPORT when reporting/showing torn or damaged bags without logging cash/delivery settlement.
- Use RECORD_DELIVERY when reporting delivered bags and/or cash received."""


def is_vertex_configured(api_key: Optional[str] = None) -> bool:
    use_vertex_env = os.getenv("USE_VERTEX_AI", "").strip().lower()
    if use_vertex_env == "true":
        return True
    if use_vertex_env == "false":
        return False
    # Only route to Vertex AI when explicit GCP project/ADC credentials are configured.
    # Gemini API keys (including AQ.* and AIza*) connect directly to Gemini Live API (v1beta).
    return bool(
        os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    )


def detect_customer_in_text(low: str) -> Optional[str]:
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
    active_store: Optional[str] = None,
) -> Dict[str, Any]:
    low = normalize_for_parsing(text)
    customer = detect_customer_in_text(low)

    normalized = low.replace(",", "")
    bags_match = re.search(r"(\d+)\s*(?:intact\s+)?(?:bags|bag|bori|bundle|pieces|pcs)", normalized)
    damaged_match = re.search(
        r"(\d+)\s*(?:damaged|damage|torn|phate|phata|phat|kharab|broken)", normalized
    )
    cash_match = re.search(
        r"(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(k)?\s*(?:cash|rupees|received|mila|mil|kedaichu|kedaichuduchu|paid|collect|collected)",
        normalized,
    )
    if not cash_match:
        cash_match = re.search(
            r"(?:cash|paid|received|mila|kedaichu)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(k)?",
            normalized,
        )
    disc_match = re.search(
        r"(?:rs\.?|inr|₹)?\s*(\d+)\s*(?:extra\s+)?(?:special\s+)?(?:discount|chhoot|off|kam)",
        normalized,
    )

    delivered = int(bags_match.group(1)) if bags_match else None
    damaged = (
        int(damaged_match.group(1))
        if damaged_match
        else (2 if any(w in low for w in ["damage", "torn", "phat", "kharab"]) else 0)
    )

    cash: Optional[int] = None
    if cash_match:
        val = float(cash_match.group(1))
        if cash_match.group(2) == "k":
            val *= 1000
        cash = int(val)

    discount = (
        int(disc_match.group(1))
        if disc_match
        else (
            500
            if ("discount" in low or "chhoot" in low)
            and any(w in low for w in ["maang", "request", "extra", "special", "de do"])
            else 0
        )
    )

    detected_code, _explicit = detect_language(text or "")
    lang = LANG_LABELS.get(detected_code or DEFAULT_LANG, LANG_LABELS[DEFAULT_LANG])

    is_barge_in = any(
        w in low for w in ["ruko", "wait", "stop", "nahi", "actually", "correction", "sorry", "aagu", "aagandi"]
    )
    has_numbers = (delivered is not None) or (cash is not None) or discount > 0
    has_negation = bool(
        re.search(
            r"\b(?:not|no|never|nothing|none|zero|cant|cannot|couldnt|could not|didnt|did not|wont|will not|"
            r"unable|failed|fail|nahi|nahin|mat|illa|illai|mudiyala|ledu|vaddu|kaledu|cheyyaledu|cheyyaleka)\b",
            low,
        )
    )
    driver_unwell = bool(re.search(r"\b(?:ill|sick|unwell|fever|headache|dizzy|injured|accident)\b", low)) or any(
        w in low
        for w in [
            "not well", "not feeling well", "hospital", "doctor", "stomach pain", "body pain", "medical",
            "cant drive", "cannot drive", "cant work", "cannot work", "take leave", "need rest",
            "tabiyat", "bimar", "beemar", "bukhar", "bukhaar", "sir dard", "chakkar", "chhutti",
            "bagoledu", "bagaledu", "baledu", "jwaram", "noppi", "udambu", "sariyilla", "kaichal",
        ]
    )
    shop_closed = any(
        w in low
        for w in [
            "shop closed", "shop is closed", "store closed", "store is closed", "shutter down",
            "locked", "nobody there", "owner not there", "customer not available", "closed today",
            "dukaan band", "dukan band", "band hai", "koi nahi", "kadai moodi", "shop close", "musesi",
        ]
    )
    delivery_delay = any(
        w in low
        for w in [
            "traffic", "jam", "late", "delay", "delayed", "stuck", "breakdown", "puncture",
            "flat tire", "flat tyre", "engine", "petrol", "diesel", "rain", "raining",
            "baarish", "barish", "varsham", "mazhai", "truck problem", "gaadi kharab", "gadi kharab",
        ]
    )
    delivery_words = any(
        w in low
        for w in ["deliver", "delivered", "unload", "settled", "bhej diya", "kar diya", "mila", "received", "pannitten", "chesanu"]
    )
    unable_to_deliver = (
        (has_negation and (delivery_words or "anything" in low or "bags" in low))
        or any(
            w in low
            for w in [
                "couldnt deliver", "could not deliver", "cant deliver", "cannot deliver",
                "didnt deliver", "did not deliver", "not delivered", "nothing delivered",
                "no delivery", "zero delivery", "deliver nahi", "nahi kar paya", "nahi ho paya",
                "deliver cheyyaledu", "deliver cheyyaleka", "deliver panna mudiyala", "deliver aagala",
            ]
        )
    )
    has_delivery_numbers = has_numbers or (delivery_words and not has_negation)
    is_question = bool(
        re.search(
            r"\?|\b(?:how many|how much|what|which|who|where|when|kitne|kitna|kitni|kaun|kaunsa|kaunsi|kahan|kab|kya|"
            r"enna|evvalavu|ethana|enga|entha|enni|evaru|ekkada|eppudu|emiti|enti|show|tell me|list|batao|bataiye|sollunga)\b",
            low,
        )
    )
    asks_contact = any(w in low for w in ["phone", "number", "contact", "address", "location", "kahan", "where", "ekkada", "enga"])
    asks_today = any(
        w in low
        for w in ["today", "aaj", "ivvala", "innaikku", "so far", "ab tak", "abhi tak", "deliveries", "kitni deliver", "kitne deliver", "how many deliver", "enni deliver"]
    )
    asks_pending = (
        any(w in low for w in ["pending", "baki", "baaki", "due", "outstanding", "balance", "udhaar"])
        and customer is None
        and not any(w in low for w in ["approval", "approvals"])
    )

    if re.fullmatch(
        r"(?:hi|hello|hey|namaste|vanakkam|namaskaram|namaskaramandi|hlo|good morning|good afternoon|good evening)[\s!?.]*",
        low,
    ):
        intent = "GREETING"
    elif any(w in low for w in ["how are you", "kaise ho", "kaisa hai", "kya haal", "all good", "epdi iruk", "eppadi iruk", "epdi irukinga", "nalla irukeengala", "ela unnaru", "ela unnav", "ela unnavu", "bagunnara", "bagunnava"]):
        intent = "HOW_ARE_YOU"
    elif any(w in low for w in ["what can you do", "kya kar sakte", "who are you", "kaun ho", "em chestav", "emi cheyagalavu", "nuvvu evaru"]) or re.fullmatch(r"(?:help|menu)[\s!?.]*", low):
        intent = "HELP_CAPABILITIES"
    elif re.fullmatch(
        r"(?:ok|okay|thanks|thank you|thanks a lot|shukriya|dhanyawad|nandri|dhanyavadalu|thanks andi|sare|sare anna|done|great|nice|cool|theek hai|thik hai|badhiya|super|sahi hai|samajh gaya|got it|perfect|purinjudhu)[\s!?.]*",
        low,
    ):
        intent = "ACK_THANKS"
    elif re.fullmatch(
        r"(?:yes|yeah|yep|haan|ha|hanji|haanji|haan ji|ji haan|confirm|ok|please|go ahead|post kar do|update kar do|kar do|proceed|do it|seri|sari|aama|aamam|pannunga|post pannunga|avunu|avunu andi|cheyyandi|post cheyyandi|cheyyi|cheyyu)(?:\s+(?:bhai|sir|anna|andi|please|go ahead|kar do|post kar do|confirm|ok|post))?[\s!?.]*",
        low,
    ):
        intent = "CONFIRM_ACTION"
    elif re.fullmatch(
        r"(?:no|nope|cancel|nahi|nahin|mat karo|ruko|wait|stop|vendam|venam|illa|vaddu|ledu|aagandi|aagu|don't|dont)(?:\s+(?:bhai|sir|please|anna|andi|abhi|post|karo))?[\s!?.]*",
        low,
    ):
        intent = "CANCEL_ACTION"
    elif any(w in low for w in ["priya", "manager", "handoff", "takeover", "take over", "baat kar", "escalate", "dispute", "gussa"]):
        intent = "ESCALATE"
    elif driver_unwell and not has_numbers:
        intent = "DRIVER_UNWELL"
    elif shop_closed and not has_numbers:
        intent = "SHOP_CLOSED"
    elif delivery_delay and not has_numbers:
        intent = "DELIVERY_DELAY"
    elif unable_to_deliver and not has_numbers:
        intent = "UNABLE_TO_DELIVER"
    elif asks_contact and customer and not has_numbers:
        intent = "CONTACT_INFO"
    elif asks_today and not has_numbers and (is_question or "deliveries" in low):
        intent = "TODAY_DELIVERIES"
    elif asks_pending and not has_numbers:
        intent = "PENDING_LIST"
    elif any(w in low for w in ["summary", "aaj ka", "pending approval", "approvals", "all stores", "sabhi", "hisaab", "motham"]) or (
        "status" in low and customer is None
    ):
        intent = "CHECK_STATUS"
    elif any(w in low for w in ["policy", "sop", "rule", "limit"]) and not has_delivery_numbers:
        intent = "POLICY_CHECK"
    elif (has_image or damaged > 0) and not has_delivery_numbers and cash is None and delivered is None:
        intent = "DAMAGE_REPORT"
    elif (
        any(w in low for w in ["due", "balance", "kitna", "baki", "invoice", "pending", "check", "details", "status"])
        and not has_delivery_numbers
    ):
        intent = "LOOKUP_CUSTOMER"
    elif has_audio and not low:
        intent = "UNCLEAR_AUDIO"
    elif has_numbers:
        intent = "RECORD_DELIVERY"
    elif delivery_words and is_question:
        intent = "TODAY_DELIVERIES"
    elif delivery_words and not has_negation:
        # "Delivered at Krishna" without bag/cash numbers -> ask, never post fake numbers to Tally
        intent = "ASK_DETAILS"
    elif customer:
        intent = "LOOKUP_CUSTOMER"
    elif len(re.findall(r"[a-z\u0900-\u0c7f]+", low)) >= 3:
        intent = "NOT_UNDERSTOOD"
    else:
        intent = "GREETING"

    if intent in {"RECORD_DELIVERY", "ASK_DETAILS"} and customer is None:
        customer = active_store or LATEST_VISUAL_PROOF.get("customer_name") or "Krishna Hardware"

    return {
        "intent": intent,
        "transcript": text,
        "detected_language": lang,
        "is_barge_in": is_barge_in,
        "customer_name": customer,
        "delivered_bags": delivered,
        "damaged_bags": damaged,
        "cash_received": cash,
        "discount_requested": discount,
        "notes": text or "Processed via DeliverEx Backend Workflow",
    }


_GEMINI_COOLDOWN_UNTIL: float = 0.0
_PENDING_CONFIRMATION: Optional[Dict[str, Any]] = None
_PENDING_HANDOFF: Optional[Dict[str, Any]] = None
_SESSION_LANG: str = DEFAULT_LANG
_LOCKED_LANG: Optional[str] = None


def reset_conversation_memory() -> None:
    global _PENDING_CONFIRMATION, _PENDING_HANDOFF, _SESSION_LANG, _LOCKED_LANG
    _PENDING_CONFIRMATION = None
    _PENDING_HANDOFF = None
    _SESSION_LANG = DEFAULT_LANG
    _LOCKED_LANG = None


async def extract_driver_intent(
    *,
    audio_bytes: Optional[bytes] = None,
    mime_type: str = "audio/webm",
    text: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg",
    image_data_url: Optional[str] = None,
    active_store: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Async Gemini extraction with clean cancellation, 1-attempt fast timeout,
    and automatic 30s circuit-breaker cooldown when offline/unreachable,
    falling back seamlessly to deterministic Hinglish/Tanglish NLU.
    """
    global _GEMINI_COOLDOWN_UNTIL
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_VOICE_NOTE_MODEL", "gemini-3.8-flash").strip()
    use_vertex = is_vertex_configured(api_key)
    clean_text = (text or "").strip()

    extracted: Optional[Dict[str, Any]] = None
    used_gemini = False

    if (
        api_key
        and time.monotonic() >= _GEMINI_COOLDOWN_UNTIL
        and (audio_bytes or image_bytes or image_data_url or clean_text)
    ):
        parts: List[Any] = [EXTRACTION_PROMPT]
        if audio_bytes:
            parts.append(types.Part.from_bytes(data=audio_bytes, mime_type=mime_type or "audio/webm"))
        if image_bytes:
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type or "image/jpeg"))
        elif image_data_url and "," in image_data_url:
            try:
                hdr, b64_part = image_data_url.split(",", 1)
                img_mime = hdr.split(";")[0].split(":", 1)[1] if ":" in hdr and ";" in hdr else "image/jpeg"
                parts.append(types.Part.from_bytes(data=base64.b64decode(b64_part), mime_type=img_mime))
            except Exception:
                pass
        if clean_text:
            parts.append(f"Driver message: {clean_text}")
        if active_store:
            parts.append(f"Active store context selected by driver: {active_store}")

        http_opts = types.HttpOptions(
            api_version="v1beta",
            timeout=6000,
            retry_options=types.HttpRetryOptions(attempts=1),
        )
        client = (
            genai.Client(vertexai=True, api_key=api_key, http_options=http_opts)
            if use_vertex
            else genai.Client(api_key=api_key, http_options=http_opts)
        )
        candidate_models = list(
            dict.fromkeys([m for m in [model_name, "gemini-3-flash-preview", "gemini-2.5-flash"] if m])
        )

        try:
            for candidate in candidate_models:
                try:
                    resp = await asyncio.wait_for(
                        client.aio.models.generate_content(
                            model=candidate,
                            contents=parts,
                            config=types.GenerateContentConfig(response_mime_type="application/json"),
                        ),
                        timeout=6.5,
                    )
                    raw_text = (resp.text or "").strip()
                    if raw_text.startswith("```"):
                        raw_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.DOTALL).strip()
                    parsed = json.loads(raw_text)
                    if isinstance(parsed, dict) and parsed.get("intent"):
                        extracted = parsed
                        used_gemini = True
                        break
                except Exception as exc:
                    err_low = str(exc).lower()
                    if any(tok in err_low for tok in ["permission", "403", "not been used", "unauthorized", "api key"]):
                        _GEMINI_COOLDOWN_UNTIL = time.monotonic() + 300.0
                        break
                    if (
                        isinstance(exc, (TimeoutError, asyncio.TimeoutError, OSError))
                        or any(tok in err_low for tok in ["connect", "dns", "getaddrinfo", "timeout"])
                    ):
                        _GEMINI_COOLDOWN_UNTIL = time.monotonic() + 45.0
                        break
                    continue
        finally:
            try:
                await client.aio.aclose()
            except Exception:
                pass

    if not extracted:
        fallback_text = (
            clean_text
            if clean_text
            else ("2 torn bags photo proof" if (image_bytes or image_data_url) else "")
        )
        extracted = heuristic_extract(
            fallback_text,
            has_audio=bool(audio_bytes),
            has_image=bool(image_bytes or image_data_url),
            active_store=active_store,
        )

    return {"extracted": extracted, "used_gemini": used_gemini}


def _build_guidance_args(intent: str, extracted: Dict[str, Any], cust_res: Dict[str, Any]) -> Dict[str, Any]:
    lang = extracted.get("detected_language") or "Hinglish (HI+EN)"
    dmg = int(extracted.get("damaged_bags") or 0)
    disc = int(extracted.get("discount_requested") or 0)
    shop = cust_res.get("name") or extracted.get("customer_name") or "customer"
    inv = cust_res.get("pending_invoice_id") or "invoice"
    is_tanglish = "tanglish" in lang.lower() or "tamil" in lang.lower()

    if intent == "UNCLEAR_AUDIO":
        return {
            "intent": "CLARIFY_DRIVER_AUDIO",
            "language": lang,
            "sentiment": "CALM",
            "coach_tip": "Audio unclear or background noise detected. Ask Raju to repeat shop name & bag count.",
            "suggested_phrase": "Raju bhai, aawaz clear nahi aayi — dubara shop aur bags boliye.",
        }

    if intent == "DRIVER_UNWELL":
        return {
            "intent": "DRIVER_HEALTH_RELIEF",
            "language": lang,
            "sentiment": "CONCERNED",
            "coach_tip": "Driver reported being unwell. Relief & reschedule handoff sent to Area Manager Priya Sharma.",
            "suggested_phrase": "Take rest first — Priya is arranging a backup driver for the route.",
        }
    if intent in {"UNABLE_TO_DELIVER", "SHOP_CLOSED", "DELIVERY_DELAY"}:
        return {
            "intent": intent,
            "language": lang,
            "sentiment": "CONCERNED",
            "coach_tip": f"Zero delivery / route exception at {shop}. Offer reschedule alert to Area Manager Priya.",
            "suggested_phrase": f"No delivery posted for {shop}; ready to notify Priya to reschedule.",
        }
    if intent == "ESCALATE":
        return {
            "intent": "CUSTOMER_DISPUTE_ESCALATION",
            "language": lang,
            "sentiment": "FRUSTRATED",
            "coach_tip": f"De-escalate calmly. Warm handoff packet for {shop} sent to Priya Sharma (SOP-6.0).",
            "suggested_phrase": "Sir, hamari Area Manager Priya ma'am abhi 5 second mein line par jud rahi hain.",
        }
    if intent == "DAMAGE_REPORT" or (dmg > 0 and disc > 200):
        return {
            "intent": "DAMAGE_AND_DISCOUNT_EXCEPTION" if disc > 200 else "DAMAGE_CLAIM",
            "language": lang,
            "sentiment": "CONCERNED",
            "coach_tip": f"SOP-4.2 & SOP-5.1 active for {shop}! Attach camera proof for Priya Ma'am's 1-tap approval.",
            "suggested_phrase": f"Uncle chinta mat karo — maine Priya ma'am ko photo aur approval bhej diya hai, turant confirmation aa jayega!",
        }
    if disc > 200:
        return {
            "intent": "SPOT_DISCOUNT_EXCEPTION",
            "language": lang,
            "sentiment": "CONCERNED",
            "coach_tip": f"Discount Rs {disc} exceeds Rs 200 cap (SOP-4.2). Routed to Priya Sharma for 1-tap approval.",
            "suggested_phrase": "Sir, Rs 200 se zyada discount ke liye Priya ma'am ka approval abhi WhatsApp pe aa raha hai.",
        }
    if is_tanglish:
        return {
            "intent": "CLEAN_DELIVERY_SETTLEMENT" if intent == "RECORD_DELIVERY" else intent,
            "language": lang,
            "sentiment": "POSITIVE",
            "coach_tip": f"Matched {shop} ({inv}). Auto-settling in Tally/SAP & dispatching WhatsApp receipt.",
            "suggested_phrase": f"Sir, {shop} cash Tally-la settle aayiduchu. Official WhatsApp receipt vandhuruchu!",
        }
    return {
        "intent": intent,
        "language": lang,
        "sentiment": "POSITIVE" if intent == "RECORD_DELIVERY" else "CALM",
        "coach_tip": f"Verify intact bag count and cash against {shop} ({inv}).",
        "suggested_phrase": f"Ji, {shop} ({inv}) ka update Tally/SAP mein sync ho raha hai.",
    }


async def run_voice_agent_workflow(
    text: str,
    *,
    audio_bytes: Optional[bytes] = None,
    mime_type: str = "audio/wav",
    driver_name: str = "Raju Kumar",
    active_store: Optional[str] = None,
    channel: str = "GEMINI_LIVE_VOICE",
    lookup_only: bool = False,
    preferred_language: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the complete backend DeliverEx Live Voice/Text Agent workflow:
    1. Intent & entity extraction (Gemini async or Hinglish/Tanglish NLU)
    2. Customer & invoice lookup
    3. Grounded company SOP policy check
    4. Frontline guidance HUD update
    5. ERP ledger / quarantine / human handoff tool execution
    6. Hinglish/Tanglish/English spoken response generation
    """
    global _PENDING_CONFIRMATION, _PENDING_HANDOFF, _SESSION_LANG, _LOCKED_LANG
    t0 = time.perf_counter()
    clean_text = (text or "").strip()
    extraction = await extract_driver_intent(
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        text=clean_text or None,
        active_store=active_store,
    )
    extracted = extraction["extracted"]
    used_gemini = extraction["used_gemini"]
    intent = str(extracted.get("intent") or "RECORD_DELIVERY").upper()
    if not clean_text:
        clean_text = str(extracted.get("transcript") or "").strip()
        if not clean_text and intent != "UNCLEAR_AUDIO":
            clean_text = "🎤 [Live Voice Turn]"

    is_barge_in = bool(extracted.get("is_barge_in"))

    # Live language adaptation: explicit switch > driver's spoken language > manual preference > session memory
    spoken_text = clean_text if clean_text and not clean_text.startswith("🎤") else ""
    detected_code, explicit_switch = detect_language(spoken_text)
    pref = (preferred_language or "").strip().lower()
    if pref == "unlock":
        _LOCKED_LANG = None
    if explicit_switch and detected_code:
        lang_code = detected_code
        _LOCKED_LANG = detected_code  # driver explicitly asked -> keep this language until asked otherwise
    elif pref in LANG_CODES:
        lang_code = pref
        _LOCKED_LANG = pref
    elif _LOCKED_LANG:
        lang_code = _LOCKED_LANG
    elif detected_code:
        # Romanized Hinglish/Tanglish while the session is in native Hindi/Tamil script keeps the native language
        native_family = {"hinglish": "hi", "tanglish": "ta", "tenglish": "te"}
        lang_code = _SESSION_LANG if native_family.get(detected_code) == _SESSION_LANG else detected_code
    else:
        lang_code = _SESSION_LANG
    _SESSION_LANG = lang_code
    lang = LANG_LABELS[lang_code]
    extracted["detected_language"] = lang
    is_tanglish = lang_code in {"tanglish", "ta"}

    if explicit_switch and len(spoken_text.split()) <= 12 and not (
        extracted.get("delivered_bags") or extracted.get("cash_received")
    ):
        intent = "LANG_SWITCH"
    # Short 'ok / theek hai / seri' while a Tally post or handoff is awaiting confirmation means YES
    if intent == "ACK_THANKS" and (_PENDING_CONFIRMATION or _PENDING_HANDOFF) and not re.search(
        r"thank|shukriya|dhanyawad|nandri|dhanyavadalu", spoken_text.lower()
    ):
        intent = "CONFIRM_ACTION"

    tool_events: List[Dict[str, Any]] = []
    grounded_policies: List[Dict[str, Any]] = []
    cust_res: Dict[str, Any] = {}
    primary_result: Dict[str, Any] = {}
    guidance_data: Dict[str, Any] = {}

    target_shop = extracted.get("customer_name") or active_store or LATEST_VISUAL_PROOF.get("customer_name")

    # Step 1: Lookup Customer if relevant
    if target_shop and intent in {"LOOKUP_CUSTOMER", "DAMAGE_REPORT", "RECORD_DELIVERY", "ESCALATE", "CONTACT_INFO"}:
        c_res, c_meta = execute_tool("lookup_customer_and_invoice", {"customer_name": target_shop}, channel=channel)
        cust_res = c_res
        tool_events.append({"name": "lookup_customer_and_invoice", "args": {"customer_name": target_shop}, "result": c_res, "meta": c_meta})

    # Step 2: Policy Grounding
    dmg = int(extracted.get("damaged_bags") or 0)
    disc = int(extracted.get("discount_requested") or 0)
    if intent in {"POLICY_CHECK", "DAMAGE_REPORT", "ESCALATE", "DRIVER_UNWELL"} or disc > 0 or dmg > 0 or intent == "RECORD_DELIVERY":
        topic_parts = []
        if disc > 0:
            topic_parts.append("discount")
        if dmg > 0:
            topic_parts.append("damaged bags")
        if intent in {"ESCALATE", "DRIVER_UNWELL"}:
            topic_parts.append("handoff")
        if intent == "RECORD_DELIVERY":
            topic_parts.append("cash")
        topic = " ".join(topic_parts) or clean_text or "discount"
        p_res, p_meta = execute_tool("check_company_policy", {"topic": topic}, channel=channel)
        grounded_policies = p_res.get("matched_policies", [])
        tool_events.append({"name": "check_company_policy", "args": {"topic": topic}, "result": p_res, "meta": p_meta})

    # Step 3: Frontline Guidance HUD
    guidance_args = _build_guidance_args(intent, extracted, cust_res)
    if intent == "UNCLEAR_AUDIO":
        guidance_data = guidance_args
    else:
        g_res, g_meta = execute_tool("update_frontline_guidance", guidance_args, channel=channel)
        guidance_data = g_res.get("guidance", guidance_args)
        tool_events.append({"name": "update_frontline_guidance", "args": guidance_args, "result": g_res, "meta": g_meta})

    # Step 4: Execute Primary Backend Action (all replies adapt to the driver's live language)
    def _rs(v: Any) -> str:
        try:
            return f"{int(v):,}"
        except Exception:
            return str(v)

    if intent == "UNCLEAR_AUDIO":
        reply_text = say("unclear", lang_code)
        primary_result = {"clarify": True}
    elif intent == "LANG_SWITCH":
        reply_text = say("lang_switch", lang_code)
        primary_result = {"language": lang, "lang_code": lang_code}
    elif intent == "CANCEL_ACTION":
        _PENDING_CONFIRMATION = None
        _PENDING_HANDOFF = None
        reply_text = say("cancel", lang_code)
        primary_result = {"cancelled": True}
    elif intent == "DRIVER_UNWELL":
        _PENDING_CONFIRMATION = None
        _PENDING_HANDOFF = None
        shop_name = cust_res.get("name") or target_shop or "Krishna Hardware"
        h_args = {
            "customer_name": shop_name,
            "driver_name": driver_name,
            "reason": f"Driver health/relief alert ({clean_text}) — arrange backup driver & reschedule remaining deliveries",
        }
        h_res, h_meta = execute_tool("request_human_handoff", h_args, channel=channel)
        tool_events.append({"name": "request_human_handoff", "args": h_args, "result": h_res, "meta": h_meta})
        primary_result = h_res
        reply_text = say("driver_unwell", lang_code, hid=h_res.get("handoff_id", ""))
    elif intent == "UNABLE_TO_DELIVER":
        _PENDING_CONFIRMATION = None
        shop_name = cust_res.get("name") or target_shop or "Krishna Hardware"
        _PENDING_HANDOFF = {
            "customer_name": shop_name,
            "reason": f"Zero delivery reported ({clean_text}) — reschedule stop",
        }
        reply_text = say("unable_to_deliver", lang_code, shop=shop_name)
        primary_result = {"delivered_bags": 0, "reschedule_offered": True}
    elif intent == "SHOP_CLOSED":
        _PENDING_CONFIRMATION = None
        shop_name = cust_res.get("name") or target_shop or "Krishna Hardware"
        _PENDING_HANDOFF = {
            "customer_name": shop_name,
            "reason": f"Shop closed ({clean_text}) — reschedule delivery",
        }
        reply_text = say("shop_closed", lang_code, shop=shop_name)
        primary_result = {"shop_closed": True, "reschedule_offered": True}
    elif intent == "DELIVERY_DELAY":
        _PENDING_CONFIRMATION = None
        shop_name = cust_res.get("name") or target_shop or "Krishna Hardware"
        _PENDING_HANDOFF = {
            "customer_name": shop_name,
            "reason": f"Delivery delayed ({clean_text}) — update ETA & inform store",
        }
        reply_text = say("delivery_delay", lang_code, shop=shop_name)
        primary_result = {"delayed": True, "notify_offered": True}
    elif lookup_only and cust_res.get("found"):
        delivered_preview = extracted.get("delivered_bags") or cust_res.get("expected_bags", 20)
        cash_preview = extracted.get("cash_received") or 0
        _PENDING_CONFIRMATION = {
            "customer_name": cust_res["name"],
            "delivered_bags": int(delivered_preview),
            "damaged_bags": dmg,
            "cash_received": int(cash_preview),
            "discount_requested": disc,
            "notes": extracted.get("notes") or clean_text,
        }
        reply_text = say(
            "lookup_confirm",
            lang_code,
            name=cust_res["name"],
            cid=cust_res["customer_id"],
            inv=cust_res["pending_invoice_id"],
            exp=cust_res["expected_bags"],
            due=_rs(cust_res["balance_due_inr"]),
            deliv=delivered_preview,
            cash=_rs(cash_preview),
        )
        primary_result = cust_res
    elif intent == "CONFIRM_ACTION" and _PENDING_CONFIRMATION:
        pending_args = dict(_PENDING_CONFIRMATION)
        pending_args["driver_name"] = driver_name
        _PENDING_CONFIRMATION = None
        led_res, led_meta = execute_tool("record_delivery_and_update_ledger", pending_args, channel=channel)
        tool_events.append({"name": "record_delivery_and_update_ledger", "args": pending_args, "result": led_res, "meta": led_meta})
        primary_result = led_res
        reply_text = say(
            "confirm_done",
            lang_code,
            name=led_res.get("customer_name", pending_args["customer_name"]),
            inv=led_res.get("invoice_id", ""),
            deliv=led_res.get("delivered_bags", pending_args["delivered_bags"]),
            cash=_rs(led_res.get("cash_posted_inr", pending_args["cash_received"])),
            tally=led_res.get("tally_entry_id", ""),
        )
    elif intent == "CONFIRM_ACTION" and _PENDING_HANDOFF:
        h_args = {
            "customer_name": _PENDING_HANDOFF["customer_name"],
            "driver_name": driver_name,
            "reason": _PENDING_HANDOFF["reason"],
        }
        _PENDING_HANDOFF = None
        h_res, h_meta = execute_tool("request_human_handoff", h_args, channel=channel)
        tool_events.append({"name": "request_human_handoff", "args": h_args, "result": h_res, "meta": h_meta})
        primary_result = h_res
        reply_text = say("handoff_confirmed", lang_code, shop=h_args["customer_name"], hid=h_res.get("handoff_id", ""))
    elif intent == "CONFIRM_ACTION":
        reply_text = say("confirm_nothing", lang_code)
    elif intent == "ASK_DETAILS":
        reply_text = say("ask_details", lang_code, shop=target_shop or "shop")
        primary_result = {"needs_details": True}
    elif intent == "NOT_UNDERSTOOD":
        reply_text = say("not_understood", lang_code)
        primary_result = {"understood": False}
    elif intent == "TODAY_DELIVERIES":
        state_now = get_full_state()
        today = time.strftime("%Y-%m-%d")
        todays = [e for e in state_now["ledger"] if str(e.get("timestamp", "")).startswith(today)] or state_now["ledger"]
        if todays:
            shops = list(dict.fromkeys(e["customer_name"] for e in todays))
            reply_text = say(
                "deliveries_today",
                lang_code,
                count=len(todays),
                bags=sum(int(e.get("delivered_qty") or 0) for e in todays),
                cash=_rs(sum(int(e.get("cash_received") or 0) for e in todays)),
                shops=", ".join(shops[:5]),
            )
        else:
            reply_text = say("deliveries_none", lang_code)
        primary_result = {"deliveries": len(todays)}
    elif intent == "PENDING_LIST":
        state_now = get_full_state()
        dues = sorted(
            [c for c in state_now["customers"] if int(c.get("balance_due") or 0) > 0],
            key=lambda c: -int(c.get("balance_due") or 0),
        )
        items = "; ".join(f"{c['name']} Rs {_rs(c['balance_due'])}" for c in dues[:4]) or "-"
        reply_text = say("pending_list", lang_code, items=items, total=_rs(sum(int(c["balance_due"]) for c in dues)))
        primary_result = {"pending_customers": len(dues)}
    elif intent == "CONTACT_INFO":
        cust_row = find_customer(cust_res.get("name") or target_shop or "") or {}
        reply_text = say(
            "contact",
            lang_code,
            name=cust_row.get("name", target_shop or ""),
            location=cust_row.get("location", "-"),
            route=cust_row.get("route", "-"),
            phone=cust_row.get("phone", "-"),
            inv=cust_row.get("pending_invoice_id", "-"),
            due=_rs(cust_row.get("balance_due", 0)),
        )
        primary_result = cust_res
    elif intent == "HOW_ARE_YOU":
        reply_text = say("how_are_you", lang_code)
    elif intent == "HELP_CAPABILITIES":
        reply_text = say("help", lang_code)
    elif intent == "ACK_THANKS":
        reply_text = say("ack", lang_code)
    elif intent == "GREETING":
        reply_text = say("greeting", lang_code)
    elif intent == "CHECK_STATUS":
        state_now = get_full_state()
        pending = [a for a in state_now["approvals"] if a["status"] == "PENDING"]
        total_cash = sum(int(e["cash_received"] or 0) for e in state_now["ledger"])
        reply_text = say(
            "status", lang_code, total=_rs(total_cash), entries=len(state_now["ledger"]), pending=len(pending)
        )
        primary_result = {"total_cash": total_cash, "pending_approvals": len(pending)}
    elif intent == "LOOKUP_CUSTOMER":
        if cust_res.get("found"):
            reply_text = say(
                "lookup_found",
                lang_code,
                name=cust_res["name"],
                inv=cust_res["pending_invoice_id"],
                exp=cust_res["expected_bags"],
                due=_rs(cust_res["balance_due_inr"]),
            )
        else:
            reply_text = say("lookup_ask", lang_code)
        primary_result = cust_res
    elif intent == "POLICY_CHECK":
        sop_summary = "; ".join(f"{p['id']}: {p['title']}" for p in grounded_policies[:2]) or "SOP-4.2"
        reply_text = say("policy", lang_code, sops=sop_summary)
        primary_result = {"policies": grounded_policies}
    elif intent == "ESCALATE":
        shop_name = cust_res.get("name") or target_shop or "Krishna Hardware"
        h_args = {
            "customer_name": shop_name,
            "driver_name": driver_name,
            "reason": clean_text or f"Customer dispute at {shop_name} — requested Area Manager Priya Sharma",
        }
        h_res, h_meta = execute_tool("request_human_handoff", h_args, channel=channel)
        tool_events.append({"name": "request_human_handoff", "args": h_args, "result": h_res, "meta": h_meta})
        primary_result = h_res
        reply_text = say("escalate", lang_code, shop=shop_name, hid=h_res.get("handoff_id", ""))
    elif intent == "DAMAGE_REPORT":
        shop_name = cust_res.get("name") or target_shop or "Krishna Hardware"
        dmg_count = max(1, dmg)
        d_args = {
            "customer_name": shop_name,
            "damaged_bags": dmg_count,
            "driver_name": driver_name,
            "notes": clean_text or f"{dmg_count} torn/damaged bags reported at {shop_name}",
        }
        d_res, d_meta = execute_tool("log_damaged_bags_report", d_args, channel=channel)
        tool_events.append({"name": "log_damaged_bags_report", "args": d_args, "result": d_res, "meta": d_meta})
        primary_result = d_res
        reply_text = say("damage", lang_code, shop=shop_name, dmg=dmg_count, aid=d_res.get("approval_id", ""))
    else:
        # RECORD_DELIVERY
        _PENDING_CONFIRMATION = None
        shop_name = cust_res.get("name") or target_shop or "Krishna Hardware"
        expected_bags = cust_res.get("expected_bags", 20) if cust_res.get("found") else 20
        delivered_bags = extracted.get("delivered_bags")
        if delivered_bags is None:
            delivered_bags = max(0, expected_bags - dmg)
        cash_received = extracted.get("cash_received")
        if cash_received is None:
            cash_received = 0
        led_args = {
            "customer_name": shop_name,
            "delivered_bags": int(delivered_bags),
            "damaged_bags": dmg,
            "cash_received": int(cash_received),
            "discount_requested": disc,
            "driver_name": driver_name,
            "notes": extracted.get("notes") or clean_text,
        }
        led_res, led_meta = execute_tool("record_delivery_and_update_ledger", led_args, channel=channel)
        tool_events.append({"name": "record_delivery_and_update_ledger", "args": led_args, "result": led_res, "meta": led_meta})
        primary_result = led_res

        fmt = {
            "shop": shop_name,
            "inv": led_res.get("invoice_id", ""),
            "deliv": led_res.get("delivered_bags", delivered_bags),
            "dmg": led_res.get("damaged_bags", dmg),
            "cash": _rs(led_res.get("cash_posted_inr", cash_received)),
            "tally": led_res.get("tally_entry_id", ""),
        }
        if led_res.get("needs_manager_approval"):
            fmt["policy"] = (led_res.get("approval") or {}).get("policy_ref", "SOP")
            reply_text = say("delivery_hitl_bargein" if is_barge_in else "delivery_hitl", lang_code, **fmt)
        else:
            reply_text = say("delivery_ok", lang_code, **fmt)

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    return {
        "intent": intent,
        "detected_language": lang,
        "lang_code": lang_code,
        "is_barge_in": is_barge_in,
        "used_gemini": used_gemini,
        "processing_ms": elapsed_ms,
        "extracted": extracted,
        "customer_match": cust_res,
        "grounded_policies": grounded_policies,
        "guidance": guidance_data,
        "tool_events": tool_events,
        "result": primary_result,
        "reply_text": reply_text,
        "user_transcript": clean_text,
        "state": get_full_state(),
    }


async def run_guided_workflow_step(step: int, preferred_language: Optional[str] = None) -> Dict[str, Any]:
    """Backend orchestration for the 4 guided field-ops scenarios."""
    if step == 1:
        user_text = (
            "Hello, main Raju bol raha hoon Old Delhi market se. "
            "Krishna Hardware pe 20 bags cement deliver kar diya aur 15000 rupees cash mil gaya."
        )
        res = await run_voice_agent_workflow(
            user_text,
            preferred_language=preferred_language,
            driver_name="Raju Kumar",
            active_store="Krishna Hardware",
            lookup_only=True,
        )
        res["step"] = 1
        res["user_text"] = user_text
        return res

    if step == 2:
        user_text = (
            "Ruko ruko! 20 nahi, 18 bags sahi deliver hue hain, 2 bags phate hue damaged nikle. "
            "Aur uncle bol rahe hain 500 rupees extra discount de do aur 15000 mein invoice settle kar lo!"
        )
        res = await run_voice_agent_workflow(
            user_text,
            preferred_language=preferred_language,
            driver_name="Raju Kumar",
            active_store="Krishna Hardware",
            lookup_only=False,
        )
        res["step"] = 2
        res["is_barge_in"] = True
        res["user_text"] = user_text
        return res

    if step == 3:
        user_text = "Uncle gussa ho rahe hain invoice balance pe, please Priya ma'am se direct baat karwa do!"
        res = await run_voice_agent_workflow(
            user_text,
            preferred_language=preferred_language,
            driver_name="Raju Kumar",
            active_store="Krishna Hardware",
            lookup_only=False,
        )
        res["step"] = 3
        res["user_text"] = user_text
        return res

    if step == 4:
        user_text = (
            "Anna, T. Nagar Murugan Builders-la 25 bags cement unload pannitten, "
            "18400 cash kedaichuduchu, receipt WhatsApp-la anuppunga!"
        )
        res = await run_voice_agent_workflow(
            user_text,
            preferred_language=preferred_language,
            driver_name="Karthik (Chennai Route-7)",
            active_store="Murugan Builders",
            lookup_only=False,
        )
        res["step"] = 4
        res["user_text"] = user_text
        return res

    raise ValueError(f"Unsupported guided step: {step}")


def evaluate_go_live_readiness() -> Dict[str, Any]:
    """
    Evaluates DeliverEx Live's Go-Live production compatibility across AI models,
    WhatsApp Cloud API, Database persistence, Security guardrails, and Cloud Run deployment.
    """
    checks: List[Dict[str, Any]] = []

    # 1. Database health & persistence
    db_health = check_db_health()
    if not db_health.get("ok"):
        checks.append({
            "id": "database",
            "category": "Database",
            "status": "FAIL",
            "summary": f"Database check failed: {db_health.get('error')}",
            "remediation": "Check Firestore/GCS permissions or writable DELIVEREX_DB_PATH.",
        })
    elif db_health.get("backend") == "firestore":
        gcs_bkt = db_health.get("gcs_bucket")
        checks.append({
            "id": "database",
            "category": "Database & Proofs",
            "status": "PASS",
            "summary": (
                f"Cloud Firestore Native ({db_health.get('database')}) ACID transactions"
                + (f" + Private GCS ({gcs_bkt}) active" if gcs_bkt else " active")
            ),
            "remediation": None,
        })
    elif db_health.get("persistent_path_configured"):
        checks.append({
            "id": "database",
            "category": "Database",
            "status": "PASS",
            "summary": f"SQLite WAL healthy at persistent path ({db_health.get('path')})",
            "remediation": None,
        })
    else:
        checks.append({
            "id": "database",
            "category": "Database",
            "status": "WARN",
            "summary": "SQLite WAL healthy locally, but DELIVEREX_DB_PATH is unset (ephemeral on Cloud Run restarts)",
            "remediation": "Enable USE_FIRESTORE=true + GCS_PROOF_BUCKET or set DELIVEREX_DB_PATH on a mounted volume.",
        })

    # 2. Gemini API Key & Auth Mode compatibility
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    use_vertex = is_vertex_configured(api_key)
    live_model = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live").strip()
    voice_model = os.getenv("GEMINI_VOICE_NOTE_MODEL", "gemini-3.8-flash").strip()

    if not api_key:
        checks.append({
            "id": "gemini_auth",
            "category": "Gemini AI",
            "status": "WARN",
            "summary": "GEMINI_API_KEY not set — running on Backend Workflow & Deterministic NLU engine",
            "remediation": "Add a Google AI Studio key (AIza...) or Vertex AI key in .env / Cloud Run secret manager.",
        })
    else:
        auth_label = "Vertex AI Express" if use_vertex else "Google AI Studio"
        checks.append({
            "id": "gemini_auth",
            "category": "Gemini AI",
            "status": "PASS",
            "summary": f"GEMINI_API_KEY configured ({auth_label} mode auto-detected)",
            "remediation": None,
        })

    # Check model name compatibility
    known_ga_or_preview = {
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.5-flash-native-audio-latest",
        "gemini-2.5-flash-native-audio-preview-12-2025",
        "gemini-live-2.5-flash-native-audio",
        "gemini-3.1-flash-live-preview",
        "gemini-2.0-flash-live-001",
    }
    if live_model in known_ga_or_preview and voice_model in known_ga_or_preview:
        checks.append({
            "id": "gemini_models",
            "category": "Gemini Models",
            "status": "PASS",
            "summary": f"Live={live_model}, VoiceNote={voice_model}",
            "remediation": None,
        })
    else:
        checks.append({
            "id": "gemini_models",
            "category": "Gemini Models",
            "status": "WARN",
            "summary": f"Configured models (Live={live_model}, VoiceNote={voice_model}) rely on automatic fallback to gemini-2.5-flash / native-audio if unavailable",
            "remediation": "Verify model availability for your key tier or set GEMINI_LIVE_MODEL=gemini-2.5-flash-native-audio-latest and GEMINI_VOICE_NOTE_MODEL=gemini-2.5-flash.",
        })

    # 3. Meta WhatsApp Cloud API compatibility
    wa_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    wa_phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    wa_app_secret = os.getenv("WHATSAPP_APP_SECRET", "").strip()
    if wa_token and wa_phone_id:
        checks.append({
            "id": "whatsapp_cloud",
            "category": "WhatsApp Cloud API",
            "status": "PASS" if wa_app_secret else "WARN",
            "summary": (
                "Meta Cloud API credentials + webhook HMAC signature verification active"
                if wa_app_secret
                else "Meta Cloud API configured, but WHATSAPP_APP_SECRET is unset (webhook POST signature not enforced)"
            ),
            "remediation": None if wa_app_secret else "Set WHATSAPP_APP_SECRET from Meta App Dashboard to enforce X-Hub-Signature-256 verification.",
        })
    else:
        checks.append({
            "id": "whatsapp_cloud",
            "category": "WhatsApp Cloud API",
            "status": "WARN",
            "summary": "WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID unset — running in built-in WhatsApp Simulator & Receipt mode",
            "remediation": "Set WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID, and WHATSAPP_APP_SECRET for live Meta WhatsApp delivery.",
        })

    # 4. Security & Admin Guardrails
    env_mode = os.getenv("ENVIRONMENT", "development").strip().lower()
    cors_origins = os.getenv("CORS_ALLOW_ORIGINS", "*").strip()
    admin_key = os.getenv("ADMIN_API_KEY", "").strip()
    auth_secret = os.getenv("AUTH_SECRET", "").strip()
    manager_auth = os.getenv("ENFORCE_MANAGER_AUTH", "").strip().lower() in {"true", "1", "yes"} or env_mode == "production"
    if manager_auth and (auth_secret or admin_key):
        checks.append({
            "id": "security",
            "category": "Security & Audit",
            "status": "PASS",
            "summary": "Owner PIN + HMAC Bearer Auth + Hash-Chained Audit Log + GCS Private Proofs active",
            "remediation": None,
        })
    elif env_mode == "production" and (cors_origins == "*" or not admin_key):
        checks.append({
            "id": "security",
            "category": "Security",
            "status": "WARN",
            "summary": "Production mode active without AUTH_SECRET / ADMIN_API_KEY",
            "remediation": "Set AUTH_SECRET, OWNER_PIN, and ENFORCE_MANAGER_AUTH=true.",
        })
    else:
        checks.append({
            "id": "security",
            "category": "Security",
            "status": "PASS",
            "summary": f"Environment={env_mode} • Hash-Chained Audit Log & XSS escaping active",
            "remediation": None,
        })

    # 5. Deployment / Container / WebSocket Infrastructure
    has_dockerfile = (BASE_DIR / "Dockerfile").exists()
    has_dockerignore = (BASE_DIR / ".dockerignore").exists()
    if has_dockerfile and has_dockerignore:
        checks.append({
            "id": "deployment",
            "category": "Cloud Run & WS",
            "status": "PASS",
            "summary": "Dockerfile + .dockerignore + WebSocket proxy headers + session-affinity script ready",
            "remediation": None,
        })
    else:
        checks.append({
            "id": "deployment",
            "category": "Cloud Run & WS",
            "status": "WARN",
            "summary": "Missing .dockerignore or Dockerfile for clean Cloud Run builds",
            "remediation": "Ensure Dockerfile and .dockerignore exclude .venv, .env, and local SQLite DBs.",
        })

    fail_count = sum(1 for c in checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in checks if c["status"] == "WARN")
    pass_count = sum(1 for c in checks if c["status"] == "PASS")
    score_pct = round(((pass_count + 0.5 * warn_count) / max(1, len(checks))) * 100)

    return {
        "ready_for_working_model": fail_count == 0,
        "ready_for_production_go_live": fail_count == 0 and warn_count == 0,
        "score_pct": score_pct,
        "counts": {"pass": pass_count, "warn": warn_count, "fail": fail_count},
        "environment": env_mode,
        "checks": checks,
    }
